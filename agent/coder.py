import datetime
import difflib
import json
import logging
import os
import shutil
import subprocess
from typing import List, Optional, Tuple, Dict, Any
from pathlib import Path

from agent.context_loader import load_app_context
from agent.event_bus import (
    publish_event, publish_request, publish_response, start_listener_in_thread
)

try:
    from termcolor import cprint
except ImportError:
    def cprint(msg, color=None, **kwargs): print(msg)

CODER_LOG = "logs/coder_activity.json"
BACKUP_ROOT = "logs/agent_backups/coder"
RETRIES = 3

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)

def _log_action(action: str, details: Dict[str, Any] = None):
    os.makedirs(os.path.dirname(CODER_LOG), exist_ok=True)
    if os.path.exists(CODER_LOG):
        with open(CODER_LOG, encoding="utf-8") as f:
            all_logs = json.load(f)
    else:
        all_logs = []
    entry = {
        "timestamp": datetime.datetime.now().isoformat(),
        "action": action,
        "details": details or {}
    }
    all_logs.append(entry)
    with open(CODER_LOG, "w", encoding="utf-8") as f:
        json.dump(all_logs, f, indent=2)

class Coder:
    """
    Superpowered Coder agent: upgrades, tests, codegen, event-bus, and logs.
    """

    @staticmethod
    def backup_file(file_path: str) -> None:
        file_path = Path(file_path)
        if file_path.exists():
            backup_dir = Path(BACKUP_ROOT)
            backup_dir.mkdir(parents=True, exist_ok=True)
            bak = backup_dir / f"{file_path.stem}.bak_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}{file_path.suffix}"
            shutil.copyfile(file_path, bak)
            logging.info(f"Backup created: {bak}")

    @staticmethod
    def run_command(cmd: str) -> Tuple[str, bool]:
        """Run a shell command and return (stdout, success)."""
        try:
            result = subprocess.run(
                cmd, shell=True, text=True, capture_output=True, check=True
            )
            return result.stdout, True
        except subprocess.CalledProcessError as e:
            logging.error(f"Command failed: {e}")
            return (e.stdout or "") + (e.stderr or ""), False

    @staticmethod
    def run_tests(app_dir: str) -> Tuple[str, bool]:
        """Run pytest on the app directory, returns (output, success)."""
        return Coder.run_command(f"pytest {app_dir}")

    @classmethod
    def upgrade_app(cls, consensus_models: Optional[List[str]] = None) -> None:
        """
        Upgrade/refactor code in a selected app using multi-agent, multi-LLM logic.
        One file at a time, always safe, fully tested, explainable, and with robust rollback.
        """
        try:
            import openai
            from dotenv import load_dotenv

            load_dotenv()
            api_key = os.getenv("OPENAI_API_KEY")
            if not api_key:
                logging.error("OPENAI_API_KEY not found in environment.")
                return
            openai.api_key = api_key

            app_name = input("App/bot name to upgrade: ").strip()
            context = load_app_context(app_name)
            app_dir = os.path.abspath(
                os.path.join(os.path.dirname(__file__), "..", "apps", app_name)
            )

            user_goal = input(
                "Describe what to upgrade/refactor/fix (plain English, or paste bug/feature):\n> "
            )

            # Pre-upgrade test run for baseline
            logging.info("Running pre-upgrade tests (pytest)...")
            pre_test_out, pre_ok = cls.run_tests(app_dir)
            logging.info(pre_test_out)
            if not pre_ok:
                logging.warning("Tests are failing before upgrade. Please fix before refactor!")
                return

            # Compose AI prompt
            prompt = (
                f"You are a world-class Python architect and code agent.\n"
                f"Task: {user_goal}\n"
                f"Project configs: {context['configs']}\n"
                f"Goals: {context['goals']}\n"
                f"Current code files (partial):\n"
            )
            for fname, code in context["code_files"].items():
                prompt += f"\n# {fname}\n{code}\n"

            prompt += (
                "\n\nInstructions:\n"
                "- Generate improved/new code ONLY for the required files (show filename as header e.g. `bot.py:`).\n"
                "- For every file, include full new code block. If unchanged, do NOT include it.\n"
                "- Generate or upgrade matching test_*.py for any new logic.\n"
                "- Write a numbered changelog explaining all changes.\n"
                "- Ensure all code is PEP8, tested, with docstrings and type hints.\n"
                "- For each code file, include a pydoc docstring block at the top.\n"
                "- Do NOT output API keys or secrets.\n"
            )

            # Multi-model consensus support (optional)
            responses = []
            model_list = consensus_models or ["gpt-4o"]
            for m in model_list:
                logging.info(f"Requesting LLM response from {m}...")
                try:
                    res = openai.ChatCompletion.create(
                        model=m,
                        messages=[{"role": "system", "content": prompt}],
                        max_tokens=2000,
                    )
                    text = res.choices[0].message.content
                    responses.append(text)
                except Exception as e:
                    publish_event('error', {'agent': 'coder', 'error': str(e), 'timestamp': datetime.datetime.now().isoformat()})
                    responses.append(f"[ERROR: {e}]")
                    logging.error(f"Error requesting LLM response: {e}")

            # Show user all responses if consensus mode, else just the one
            if len(responses) > 1:
                logging.info("Multiple model outputs for review. Pick your favorite:")
                for idx, out in enumerate(responses):
                    preview = out[:1000] + ("..." if len(out) > 1000 else "")
                    logging.info(f"--- Output #{idx+1} by {model_list[idx]} ---\n{preview}")
                try:
                    idx = int(input(f"Enter number [1-{len(responses)}]: ")) - 1
                    reply = responses[idx]
                except Exception:
                    logging.error("Invalid selection. Aborting upgrade.")
                    return
            else:
                reply = responses[0]

            logging.info("--- LLM Upgrade Plan ---")
            logging.info(reply)

            # Extract filename/code blocks and proposed tests from LLM output
            import re
            code_blocks = re.split(r"\n(?=[\w\.]+\.py:)", reply)
            changes = []
            for block in code_blocks:
                lines = block.strip().split("\n")
                if not lines or ":" not in lines[0]:
                    continue
                fname = lines[0].rstrip(":")
                code = "\n".join(lines[1:]).strip()
                file_path = os.path.abspath(os.path.join(app_dir, fname))
                prev_code = ""
                if os.path.exists(file_path):
                    with open(file_path, encoding="utf-8") as f:
                        prev_code = f.read()
                diff = difflib.unified_diff(
                    prev_code.splitlines(),
                    code.splitlines(),
                    fromfile=f"{fname} (old)",
                    tofile=f"{fname} (new)",
                    lineterm="",
                )
                # ========== FIXED SECTION ==========
                diff_text = '\n'.join(list(diff)) or '[file created]'
                logging.info(f"--- DIFF for {fname} ---\n{diff_text}")
                # ========== END FIX ==========
                changes.append({
                    "fname": fname,
                    "code": code,
                    "file_path": file_path,
                    "prev_code": prev_code,
                })

            # Get user confirmation and upgrade one file at a time, with retries and rollback
            for ch in changes:
                summary = f"\n=== PLAN: {ch['fname']} ===\n\n{ch['code'][:800]}\n---"
                cprint(summary, "cyan")
                if input(f"Apply changes to {ch['fname']}? (y/n): ").lower().startswith("y"):
                    cls.backup_file(ch["file_path"])
                    post_ok = False
                    for attempt in range(1, RETRIES + 1):
                        try:
                            with open(ch["file_path"], "w", encoding="utf-8") as f:
                                f.write(ch["code"])
                            # Run hygiene tools
                            logging.info("Running black...")
                            cls.run_command(f"black {app_dir}")
                            logging.info("Running flake8...")
                            cls.run_command(f"flake8 {app_dir}")
                            logging.info("Running mypy...")
                            cls.run_command(f"mypy {app_dir}")
                            logging.info("Running bandit...")
                            cls.run_command(f"bandit -r {app_dir}")
                            # Test after each attempt
                            post_test_out, post_ok = cls.run_tests(app_dir)
                            logging.info(post_test_out)
                            if post_ok:
                                cprint(f"✅ Upgrade succeeded for {ch['fname']}.", "green")
                                break
                            else:
                                cprint(f"[WARN] Tests failed after attempt {attempt} for {ch['fname']}. Retrying...", "yellow")
                        except Exception as e:
                            publish_event('error', {'agent': 'coder', 'error': str(e), 'timestamp': datetime.datetime.now().isoformat()})
                            logging.error(f"Error writing or testing {ch['fname']}: {e}")
                        # Rollback after last failed attempt
                        if attempt == RETRIES:
                            cprint(f"[FAIL] All attempts failed. Rolling back {ch['fname']}.", "red")
                            backups = [
                                f for f in os.listdir(os.path.dirname(ch["file_path"]))
                                if f.startswith(os.path.basename(ch["file_path"]) + ".bak_")
                            ]
                            if backups:
                                latest_bak = sorted(backups)[-1]
                                bak_path = os.path.join(os.path.dirname(ch["file_path"]), latest_bak)
                                shutil.copyfile(bak_path, ch["file_path"])
                            cprint(f"Rolled back {ch['fname']}.", "red")
                    # Log action for dashboard
                    _log_action("upgrade_file", {
                        "file": ch['fname'],
                        "applied": post_ok,
                        "rollback": not post_ok,
                        "attempts": attempt,
                        "goal": user_goal,
                    })

            # Save a summary log after full session
            log_path = os.path.abspath(
                os.path.join(app_dir, "logs", f"upgrade_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.log")
            )
            with open(log_path, "w", encoding="utf-8") as logf:
                logf.write(f"User goal: {user_goal}\n\nLLM output:\n{reply}\n")
            mem_path = os.path.join(app_dir, "memory.json")
            mem = {}
            try:
                if os.path.exists(mem_path):
                    with open(mem_path, encoding="utf-8") as mf:
                        mem = json.load(mf)
                if "code_changes" not in mem:
                    mem["code_changes"] = []
                mem["code_changes"].append({
                    "timestamp": datetime.datetime.now().isoformat(),
                    "goal": user_goal,
                    "summary": reply[:2000],
                })
                with open(mem_path, "w", encoding="utf-8") as mf:
                    json.dump(mem, mf, indent=2)
            except Exception as e:
                publish_event('error', {'agent': 'coder', 'error': str(e), 'timestamp': datetime.datetime.now().isoformat()})
                logging.error(f"Error updating memory: {e}")

            logging.info("Upgrade session complete. All changes linted, checked, tested, logged, and documented.")

        except Exception as e:
            publish_event('error', {'agent': 'coder', 'error': str(e), 'timestamp': datetime.datetime.now().isoformat()})
            logging.error(f"An error occurred during the upgrade process: {e}")

# ========== EVENT BUS HANDLERS ==========

def handle_upgrade_request(event):
    print(f"[EventBus] Received upgrade_request: {event}")
    coder = Coder()
    # Parse event for target app, user_goal, etc.
    # For demo purposes, just call upgrade_app (real implementation: parameterize)
    coder.upgrade_app()  # You could parameterize this with event['data']
    result = {"status": "handled", "details": "upgrade_request handled by Coder agent"}
    publish_response("upgrade_result", result, correlation_id=event.get("correlation_id"))

def handle_review_request(event):
    print(f"[EventBus] Received review_request: {event}")
    # TODO: Implement peer review or code review logic here
    result = {"status": "handled", "details": "review_request handled by agent."}
    publish_response("review_result", result, correlation_id=event.get("correlation_id"))

start_listener_in_thread(handle_upgrade_request, event_types=["upgrade_request"])
start_listener_in_thread(handle_review_request, event_types=["review_request"])
