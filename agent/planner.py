# agent/planner.py

import datetime
import json
import logging
import os
import shutil
from pathlib import Path
from typing import Optional, List, Dict, Any

from agent.event_bus import (
    publish_event, publish_request, publish_response, start_listener_in_thread
)

try:
    from termcolor import cprint
except ImportError:
    def cprint(msg, color=None, **kwargs):
        print(msg)

try:
    import openai
except ImportError:
    openai = None

# --- Configuration ---
PLANNER_LOG_PATH = Path("logs/planner_activity.json")
BACKUP_ROOT = Path("logs/agent_backups/planner")
RETRIES = 3

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")


class Planner:
    """
    Superpowered Planner agent:
    - Modular, safe, explainable
    - Dashboard-ready with event-bus integration
    """

    def __init__(self, apps_base_dir: Optional[str] = None):
        # Base directory for all apps/bots
        self.apps_base_dir = Path(apps_base_dir) if apps_base_dir else (Path(__file__).parent.parent / "apps")
        self.apps_base_dir.mkdir(parents=True, exist_ok=True)
        BACKUP_ROOT.mkdir(parents=True, exist_ok=True)
        PLANNER_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

    def _log_action(self, action: str, details: Optional[Dict[str, Any]] = None) -> None:
        """
        Append action log entry to JSON planner activity log.
        """
        try:
            if PLANNER_LOG_PATH.exists():
                with open(PLANNER_LOG_PATH, encoding="utf-8") as f:
                    all_logs = json.load(f)
            else:
                all_logs = []

            entry = {
                "timestamp": datetime.datetime.now().isoformat(),
                "action": action,
                "details": details or {}
            }
            all_logs.append(entry)

            with open(PLANNER_LOG_PATH, "w", encoding="utf-8") as f:
                json.dump(all_logs, f, indent=2)
        except Exception as e:
            logging.error(f"Failed to log planner action '{action}': {e}")

    def list_apps(self) -> None:
        """
        List all available apps/bots.
        """
        try:
            if not self.apps_base_dir.exists():
                cprint(f"[FAIL] Apps directory not found: {self.apps_base_dir}", "red")
                return
            apps = [d.name for d in self.apps_base_dir.iterdir() if d.is_dir()]
            if not apps:
                cprint("No apps/bots found. Use create_app() to make one.", "yellow")
            else:
                cprint("Available Apps/Bots:", "cyan")
                for app in apps:
                    print(f" - {app}")
            self._log_action("list_apps", {"found": apps})
        except Exception as e:
            cprint(f"[FAIL] Error listing apps: {e}", "red")

    def create_app(self) -> None:
        """
        Prompt user for new app name and create directory structure with base files.
        """
        try:
            name = input("App/Bot name: ").strip()
            if not name:
                cprint("No name provided.", "red")
                return

            app_dir = self.apps_base_dir / name
            if app_dir.exists():
                cprint("App already exists.", "yellow")
                return

            # Create app structure
            app_dir.mkdir(parents=True, exist_ok=False)
            (app_dir / "logs").mkdir(exist_ok=True)
            (app_dir / "data").mkdir(exist_ok=True)

            # Create stub files
            (app_dir / "bot.py").write_text(f"# {name} main logic here\n", encoding="utf-8")
            (app_dir / "config.json").write_text(
                json.dumps({"name": name, "version": "0.1.0"}, indent=2), encoding="utf-8"
            )
            (app_dir / "goals.md").write_text(f"# {name} Goals\n", encoding="utf-8")
            (app_dir / "metrics.json").write_text(json.dumps({"total_signals_sent": 0}), encoding="utf-8")
            (app_dir / "memory.json").write_text("{}", encoding="utf-8")

            cprint(f"App '{name}' created successfully!", "green")
            self._log_action("create_app", {"app": name})
        except Exception as e:
            cprint(f"[FAIL] Error creating app: {e}", "red")
            logging.error(f"Error creating app: {e}")

    def backup_file(self, file_path: str) -> None:
        """
        Backup a file before modification to the backup directory with timestamp.
        """
        try:
            file_path_obj = Path(file_path)
            if file_path_obj.exists():
                BACKUP_ROOT.mkdir(parents=True, exist_ok=True)
                timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                backup_file = BACKUP_ROOT / f"{file_path_obj.stem}.bak_{timestamp}{file_path_obj.suffix}"
                shutil.copyfile(file_path_obj, backup_file)
                logging.info(f"Backup created: {backup_file}")
        except Exception as e:
            logging.error(f"Failed to backup file {file_path}: {e}")

    def decompose_goal(
        self,
        app_name: str,
        goal_text: Optional[str] = None,
        model: str = "gpt-4o",
        consensus_models: Optional[List[str]] = None
    ) -> Optional[str]:
        """
        Decompose a goal into requirements, subtasks, test cases, edge cases using LLM (OpenAI).
        Human-in-the-loop, logged, retryable, safe, actionable.
        """
        if openai is None:
            cprint("[FAIL] OpenAI SDK not available. Cannot decompose goals via LLM.", "red")
            return None

        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            cprint("[FAIL] OPENAI_API_KEY not set in environment.", "red")
            return None

        if not goal_text:
            cprint("Paste the main goal or requirement (plain English):", "cyan")
            goal_text = input("> ").strip()
            if not goal_text:
                cprint("[FAIL] No goal text provided.", "red")
                return None

        prompt = (
            "You are an AI planner for a world-class multi-agent team.\n"
            "Given the following app goal:\n"
            "---\n"
            f"{goal_text}\n"
            "---\n"
            "Decompose into:\n"
            "1. Requirements\n"
            "2. Subtasks\n"
            "3. Test Cases\n"
            "4. Edge Cases\n\n"
            "Each as a detailed numbered Markdown list. Be precise, actionable, and expert-level.\n"
            "If appropriate, add a mermaid diagram (in Markdown) to visualize architecture or workflow.\n"
            "Always ensure the plan is actionable, testable, robust, and understandable for both humans and LLMs."
        )

        cprint("Generating requirements and plan via LLM...", "magenta")

        plan_md = ""
        for attempt in range(1, RETRIES + 1):
            try:
                resp = openai.ChatCompletion.create(
                    model=model,
                    messages=[{"role": "system", "content": prompt}],
                    max_tokens=1500,
                    temperature=0.12,
                )
                plan_md = resp.choices[0].message.content
                # Basic validation: check presence of all expected sections
                if all(section in plan_md for section in ["Requirements", "Subtasks", "Test Cases", "Edge Cases"]):
                    break
                cprint(f"[WARN] LLM output missing some sections. Attempt {attempt}.", "yellow")
            except Exception as e:
                publish_event('error', {'agent': 'planner', 'error': str(e), 'timestamp': datetime.datetime.now().isoformat()})
                cprint(f"[FAIL] LLM call failed: {e} (attempt {attempt})", "red")

            if attempt == RETRIES:
                cprint("[ERROR] LLM failed to generate a valid plan after retries.", "red")
                return None

        # Human review/edit step
        print(plan_md)
        if input("Edit before save? (y/n): ").lower().startswith("y"):
            import subprocess
            from tempfile import NamedTemporaryFile

            with NamedTemporaryFile("w+", delete=False, suffix=".md") as tmp:
                tmp.write(plan_md)
                tmp.flush()
                editor = ["notepad"] if os.name == "nt" else ["nano"]
                subprocess.call(editor + [tmp.name])
                tmp.seek(0)
                plan_md = tmp.read()

        # Save plan to goals.md with backup
        goals_path = self.apps_base_dir / app_name / "goals.md"
        self.backup_file(str(goals_path))
        with open(goals_path, "a", encoding="utf-8") as f:
            f.write(f"\n\n# Plan ({datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}):\n")
            f.write(plan_md)

        # Save log for traceability
        logs_dir = self.apps_base_dir / app_name / "logs"
        logs_dir.mkdir(exist_ok=True)
        log_path = logs_dir / f"plan_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
        with open(log_path, "w", encoding="utf-8") as logf:
            logf.write(f"Prompt:\n{prompt}\n\nPlan:\n{plan_md}\n")

        self._log_action("decompose_goal", {"app": app_name, "goal": goal_text, "plan_excerpt": plan_md[:250]})

        cprint("Plan saved to goals.md and logged.", "green")
        return plan_md

    def show_goals(self, app_name: str) -> None:
        """
        Display the goals.md for the selected app in a human-friendly way.
        """
        goals_path = self.apps_base_dir / app_name / "goals.md"
        if goals_path.exists():
            cprint("\n--- GOALS ---\n", "cyan")
            print(goals_path.read_text(encoding="utf-8"))
            self._log_action("show_goals", {"app": app_name})
        else:
            cprint("[FAIL] goals.md not found.", "red")

    def export_plan_diagram(self, app_name: str) -> None:
        """
        Export mermaid or PlantUML diagrams from goals.md to the diagrams directory for dashboard integration.
        """
        try:
            goals_path = self.apps_base_dir / app_name / "goals.md"
            if not goals_path.exists():
                cprint("goals.md not found for this app.", "yellow")
                return

            content = goals_path.read_text(encoding="utf-8")

            import re
            mermaid_blocks = re.findall(r"```mermaid([\s\S]+?)```", content)
            plantuml_blocks = re.findall(r"```plantuml([\s\S]+?)```", content)

            if not mermaid_blocks and not plantuml_blocks:
                cprint("No Mermaid or PlantUML diagrams found in goals.md.", "yellow")
                return

            diagrams_dir = self.apps_base_dir / app_name / "diagrams"
            diagrams_dir.mkdir(exist_ok=True)

            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")

            if mermaid_blocks:
                mermaid_path = diagrams_dir / f"diagram_{timestamp}.mermaid.md"
                mermaid_path.write_text(f"```mermaid\n{mermaid_blocks[0].strip()}\n```", encoding="utf-8")
                cprint(f"Mermaid diagram exported to {mermaid_path}", "green")

            if plantuml_blocks:
                plantuml_path = diagrams_dir / f"diagram_{timestamp}.plantuml.md"
                plantuml_path.write_text(f"```plantuml\n{plantuml_blocks[0].strip()}\n```", encoding="utf-8")
                cprint(f"PlantUML diagram exported to {plantuml_path}", "green")

            self._log_action("export_plan_diagram", {"app": app_name, "files_dir": str(diagrams_dir)})

        except Exception as e:
            cprint(f"[FAIL] Error exporting plan diagrams: {e}", "red")
            logging.error(f"Error exporting plan diagrams: {e}")

    def suggest_cross_agent_improvements(self) -> None:
        """
        Stub: Planner can recommend cross-agent upgrades or notify others.
        Expand with event bus integration as system evolves.
        """
        cprint("[Planner] No critical cross-agent suggestions at this time.", "yellow")
        self._log_action("suggest_cross_agent_improvements")

# --- Event Bus Handler ---
def handle_plan_request(event: dict):
    """
    Event handler for 'plan_request' events.
    Use Planner to generate plan or respond with default.
    """
    print(f"[EventBus] Received plan_request: {event}")
    planner = Planner()
    # Placeholder example: respond with status
    result = {"status": "handled", "details": "plan_request handled by Planner agent."}
    publish_response("plan_result", result, correlation_id=event.get("correlation_id"))

# Start event listener thread for 'plan_request' events
start_listener_in_thread(handle_plan_request, event_types=["plan_request"])

if __name__ == "__main__":
    planner = Planner()
    planner.list_apps()
