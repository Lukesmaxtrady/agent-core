import datetime
import json
import logging
import os
import shutil
from pathlib import Path
from typing import Optional, List, Dict, Any
from agent.event_bus import publish_event

try:
    from termcolor import cprint
except ImportError:
    def cprint(msg, color=None, **kwargs): print(msg)

try:
    import openai
except ImportError:
    openai = None

from agent.event_bus import publish_request, publish_response, start_listener_in_thread

# Configuration
FEEDBACK_LOG = "logs/feedback_activity.json"
BACKUP_ROOT = "logs/agent_backups/feedback"
RETRIES = 3

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)

class Feedback:
    """
    Feedback agent: collect, log, analyze, and summarize user/app feedback,
    plug-in ready for dashboards, safe backups, and future event-bus integration.
    """

    def __init__(self, apps_base_dir: Optional[str] = None):
        self.apps_base_dir = (
            Path(apps_base_dir)
            if apps_base_dir
            else Path(__file__).parent.parent / "apps"
        )

    def _log_action(self, action: str, details: Dict[str, Any] = None):
        os.makedirs(os.path.dirname(FEEDBACK_LOG), exist_ok=True)
        if os.path.exists(FEEDBACK_LOG):
            with open(FEEDBACK_LOG, encoding="utf-8") as f:
                all_logs = json.load(f)
        else:
            all_logs = []
        entry = {
            "timestamp": datetime.datetime.now().isoformat(),
            "action": action,
            "details": details or {}
        }
        all_logs.append(entry)
        with open(FEEDBACK_LOG, "w", encoding="utf-8") as f:
            json.dump(all_logs, f, indent=2)

    def backup_file(self, file_path: str) -> None:
        """Backup a file before modification to backup directory (not inline)."""
        file_path = Path(file_path)
        if file_path.exists():
            backup_dir = Path(BACKUP_ROOT)
            backup_dir.mkdir(parents=True, exist_ok=True)
            bak = backup_dir / f"{file_path.stem}.bak_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}{file_path.suffix}"
            shutil.copyfile(file_path, bak)
            logging.info(f"Backup created: {bak}")

    def collect_feedback(self, app_name: str) -> None:
        """
        Prompt user for feedback and save it to app's feedback.json.
        """
        feedback = input(f"Enter feedback for {app_name}: ").strip()
        if not feedback:
            cprint("No feedback provided.", "yellow")
            return

        fb_path = self.apps_base_dir / app_name / "feedback.json"
        self.backup_file(fb_path)
        now = datetime.datetime.now().isoformat()
        feedback_entry = {
            "timestamp": now,
            "feedback": feedback
        }
        try:
            if fb_path.exists():
                with open(fb_path, encoding="utf-8") as f:
                    fb_log = json.load(f)
            else:
                fb_log = []
            fb_log.append(feedback_entry)
            with open(fb_path, "w", encoding="utf-8") as f:
                json.dump(fb_log, f, indent=2)
            cprint("Feedback saved!", "green")
            self._log_action("collect_feedback", {"app": app_name, "feedback": feedback})
        except Exception as e:
            publish_event('error', {'agent': 'feedback', 'error': str(e), 'timestamp': datetime.datetime.now().isoformat()})  # [event_bus hook]
            cprint(f"[FAIL] Error saving feedback: {e}", "red")

    def run_loop(self, app_name: str) -> None:
        """
        Feedback improvement loop: analyze, summarize, and suggest actions.
        """
        fb_path = self.apps_base_dir / app_name / "feedback.json"
        if not fb_path.exists():
            cprint(f"No feedback found for {app_name}.", "yellow")
            return

        try:
            with open(fb_path, encoding="utf-8") as f:
                fb_log = json.load(f)
        except Exception as e:
            publish_event('error', {'agent': 'feedback', 'error': str(e), 'timestamp': datetime.datetime.now().isoformat()})  # [event_bus hook]
            cprint(f"[FAIL] Error reading feedback: {e}", "red")
            return

        all_feedback = "\n".join(fb["feedback"] for fb in fb_log)
        prompt = (
            f"Summarize the following feedback for app '{app_name}'. "
            f"Extract actionable improvements, praise, and issues. Output a numbered list of actions and one-paragraph summary:\n\n{all_feedback}"
        )

        summary = ""
        if openai and os.environ.get("OPENAI_API_KEY"):
            for attempt in range(1, RETRIES+1):
                try:
                    resp = openai.ChatCompletion.create(
                        model="gpt-4o",
                        messages=[{"role": "system", "content": prompt}],
                        max_tokens=600,
                        temperature=0.15,
                    )
                    summary = resp.choices[0].message.content
                    break
                except Exception as e:
                    publish_event('error', {'agent': 'feedback', 'error': str(e), 'timestamp': datetime.datetime.now().isoformat()})  # [event_bus hook]
                    cprint(f"[WARN] LLM error on attempt {attempt}: {e}", "yellow")
        else:
            summary = "[WARN] LLM not configured. Cannot summarize feedback."

        # Save to feedback_summary.md
        fb_sum_path = self.apps_base_dir / app_name / "feedback_summary.md"
        self.backup_file(fb_sum_path)
        with open(fb_sum_path, "a", encoding="utf-8") as f:
            f.write(
                f"\n# Feedback Summary ({datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}):\n"
            )
            f.write(summary)
        cprint("Feedback summary saved!", "green")
        self._log_action("run_loop", {"app": app_name, "summary": summary[:200]})

    def summarize_feedback(self, app_name: str) -> None:
        """
        Print human-friendly summary of feedback.
        """
        fb_sum_path = self.apps_base_dir / app_name / "feedback_summary.md"
        if fb_sum_path.exists():
            cprint(f"\n--- FEEDBACK SUMMARY for {app_name} ---\n", "cyan")
            print(fb_sum_path.read_text(encoding="utf-8"))
            self._log_action("summarize_feedback", {"app": app_name})
        else:
            cprint("No feedback summary found.", "yellow")

    # -- Ready for future: publish feedback to Notion/Slack, event bus, etc. --
    def publish_feedback_event(self, app_name: str) -> None:
        """
        Stub: publish feedback summary or improvement event to event bus or external system.
        """
        # TODO: Implement as system grows (e.g. Redis, HTTP POST, Slack/Notion sync, etc)
        cprint(f"[Feedback] Publish event for {app_name} - not yet implemented.", "yellow")
        self._log_action("publish_feedback_event", {"app": app_name})

# ========== EVENT BUS HANDLER ==========

def handle_feedback_request(event):
    """
    Auto-injected event handler for 'feedback_request' in this agent.
    """
    print(f"[EventBus] Received feedback_request: {event}")
    # TODO: Replace this with agent logic.
    result = {"status": "handled", "details": f"feedback_request handled by agent."}
    publish_response("feedback_result", result, correlation_id=event.get("correlation_id"))

start_listener_in_thread(handle_feedback_request, event_types=["feedback_request"])
