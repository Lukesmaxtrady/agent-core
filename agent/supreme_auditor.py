# agent/supreme_auditor.py

import datetime
import difflib
import json
import os
import shutil
import subprocess
from typing import Any, Dict, List, Optional

from agent.event_bus import publish_event
from agent import utils

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
LOG_FILE = "logs/upgrade_history.json"
SUMMARY_FILE = "logs/upgrade_summaries.json"
BACKUP_ROOT = "logs/agent_backups"
POLICY_FILE = "logs/upgrade_policy.json"
RETRIES = 3
TELEGRAM_NOTIFY = True  # Set to False to disable notifications

# OpenAI client setup
client = None
if openai:
    api_key = os.environ.get("OPENAI_API_KEY")
    if api_key:
        try:
            client = openai.OpenAI(api_key=api_key)
        except Exception as e:
            client = None
            publish_event('error', {
                'agent': 'supreme_auditor',
                'error': f"OpenAI init failed: {e}",
                'timestamp': datetime.datetime.now().isoformat()
            })

def notify_telegram(msg: str) -> None:
    try:
        import requests
        TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
        CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
        if TOKEN and CHAT_ID:
            url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
            data = {"chat_id": CHAT_ID, "text": msg[:4096]}
            requests.post(url, data=data)
    except Exception:
        pass  # Silent fail

def load_policy() -> dict:
    if os.path.exists(POLICY_FILE):
        with open(POLICY_FILE, "r", encoding="utf-8") as f:
            try:
                return json.load(f)
            except Exception:
                return {}
    return {"mode": "approval"}

def save_log(history: list) -> None:
    os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
    with open(LOG_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, indent=2)

def backup_agent(name: str, code: str) -> str:
    """Use utils.backup_file for consistent backup with pruning."""
    # Write code to temp file first
    temp_path = os.path.join(os.path.dirname(__file__), f"{name}.py")
    with open(temp_path, "w", encoding="utf-8") as f:
        f.write(code)
    backup_path = utils.backup_file(temp_path, BACKUP_ROOT)
    return backup_path

def show_diff(old: str, new: str, name: str) -> None:
    diff = difflib.unified_diff(
        old.splitlines(),
        new.splitlines(),
        fromfile=f"{name}.py (old)",
        tofile=f"{name}.py (new)",
        lineterm="",
    )
    cprint("\n".join(diff), "blue")

def explain_upgrade(agent_name: str, summary: str) -> str:
    if not client:
        return f"Upgrade summary for {agent_name}: {summary[:200]}..."
    prompt = (
        f"This is an upgrade summary for agent '{agent_name}':\n{summary}\n"
        f"Summarize in 2 sentences for a manager. If technical issues, mention next actions."
    )
    resp = utils.llm_call(client, prompt, model="gpt-4o", max_tokens=250, temperature=0.1)
    return resp if resp else summary[:200]

def run_tests(name: str, agent_dir: str) -> tuple[bool, str]:
    test_dir = os.path.join(agent_dir, name + "_tests")
    if os.path.exists(test_dir):
        try:
            proc = subprocess.run(
                ["pytest", "--maxfail=3", "--disable-warnings", "--tb=short"],
                cwd=test_dir,
                capture_output=True,
                text=True,
                timeout=90,
            )
            return proc.returncode == 0, proc.stdout
        except Exception as t_ex:
            return False, str(t_ex)
    return True, "[INFO] No tests directory found for this agent."

def llm_upgrade_scan(name: str, code: str) -> tuple[str, str, str, str]:
    if not client:
        return "[INFO] OpenAI not configured.", "", "", ""
    try:
        prompt = (
            "You are a world-class Python agent code reviewer and refactorer.\n"
            "Analyze this Python agent. List all flaws, risks, outdated patterns, and potential upgrades or improvements. "
            "Then output improved code (if possible), and a short self-critique and confidence rating (0-10) with explanation.\n"
            "---\nCODE:\n" + code + "\n"
        )
        response = utils.llm_call(client, prompt, model="gpt-4o", max_tokens=2500, temperature=0.15)
        improved_code = ""
        critique = ""
        conf = ""
        if "```python" in response:
            improved_code = response.split("```python")[1].split("```")[0].strip()
        if "Self-critique:" in response:
            critique = response.split("Self-critique:")[1].split("\n")[0].strip()
        if "Confidence:" in response:
            conf = response.split("Confidence:")[1].split("\n")[0].strip()
        return response, improved_code, critique, conf
    except Exception as e:
        publish_event('error', {
            'agent': 'supreme_auditor',
            'error': str(e),
            'timestamp': datetime.datetime.now().isoformat()
        })
        return f"[INFO] LLM scan failed for {name}: {e}", "", "", ""

def save_upgrade_summary(agent_name: str, summary: str, result: str) -> None:
    os.makedirs(os.path.dirname(SUMMARY_FILE), exist_ok=True)
    all_logs = utils.load_json_file(SUMMARY_FILE, default=[])
    all_logs.append({
        "agent": agent_name,
        "summary": summary,
        "result": result,
        "timestamp": datetime.datetime.now().isoformat()
    })
    utils.save_json_file(SUMMARY_FILE, all_logs)

def ask_user(prompt: str) -> str:
    """Prompt the user with [y/n/all/skip] and return their lowercase response."""
    try:
        from termcolor import cprint
    except ImportError:
        def cprint(msg, *args, **kwargs):
            print(msg)
    cprint(f"\n{prompt} [y/n/all/skip]: ", "yellow", end="")
    return input().strip().lower()

def supreme_audit_and_heal(verbose: bool = True, use_llm: bool = True, allow_auto: bool = False) -> None:
    policy = load_policy()
    auto_mode = allow_auto or (policy.get("mode") == "auto")
    agent_dir = os.path.abspath(os.path.dirname(__file__))
    agent_files = [
        f for f in os.listdir(agent_dir)
        if f.endswith(".py")
        and f not in ("__init__.py", "auto_upgrade_agent.py", "supreme_auditor.py")
    ]

    history = []
    for file in agent_files:
        name = file[:-3]
        code_path = os.path.join(agent_dir, file)
        with open(code_path, encoding="utf-8") as f:
            old_code = f.read()

        cprint(f"\n=== Auditing agent: {name} ===", "cyan", attrs=["bold"])
        backup_path = backup_agent(name, old_code)
        upgrade_success = False
        upgrade_summary = ""
        last_error = ""

        for attempt in range(1, RETRIES + 1):
            suggestions, improved_code, critique, conf = llm_upgrade_scan(name, old_code)

            if improved_code and improved_code != old_code:
                show_diff(old_code, improved_code, name)
                cprint(f"\n=== UPGRADE SUGGESTIONS for {name} ===", "cyan")
                cprint(suggestions, "magenta")
                cprint(f"\nSelf-critique: {critique}\nConfidence: {conf}\n", "yellow")

                pre_ok, pre_out = run_tests(name, agent_dir)
                if not pre_ok:
                    cprint(f"[WARN] Pre-upgrade tests failed: {pre_out}", "yellow")

                resp = "all" if auto_mode else ask_user(f"Apply these upgrades to agent '{name}'?")
                if resp not in ("y", "yes", "all"):
                    cprint(f"[SKIP] Upgrade skipped for {name}.", "yellow")
                    upgrade_summary = "Upgrade skipped by user."
                    break

                with open(code_path, "w", encoding="utf-8") as f:
                    f.write(improved_code)

                post_ok, post_out = run_tests(name, agent_dir)
                if post_ok:
                    cprint(f"[OK] Upgrade applied and passed tests for {name}.", "green")
                    upgrade_success = True
                    upgrade_summary = f"Upgrade successful. Critique: {critique} Confidence: {conf}"
                    break
                else:
                    cprint(f"[FAIL] Upgrade broke tests for {name}! Rolling back. Attempt {attempt}", "red")
                    shutil.copyfile(backup_path, code_path)
                    last_error = post_out
                    if attempt == RETRIES:
                        cprint(f"[FAIL] Upgrade failed for {name} after {RETRIES} attempts.", "red")
                        upgrade_summary = f"Upgrade failed after retries. Last error: {last_error}"
            else:
                cprint(f"[INFO] No substantive code improvement for {name}.", "yellow")
                upgrade_success = True
                upgrade_summary = "Already optimal or no changes needed."
                break

        summary_text = explain_upgrade(name, upgrade_summary)
        cprint(f"\n[SUMMARY] {name}: {summary_text}", "magenta")
        save_upgrade_summary(name, summary_text, "Success" if upgrade_success else "Failed")

        history.append({
            "name": name,
            "success": upgrade_success,
            "summary": summary_text,
            "timestamp": datetime.datetime.now().isoformat()
        })

        cont = input("\nPress Enter for next agent or type 'exit' to stop: ").strip().lower()
        if cont == "exit":
            break

    save_log(history)
    cprint("\n======= SUPREME AUDIT SUMMARY =======", "cyan")
    for up in history:
        cprint(
            f"{up['name']}: {'Upgraded' if up['success'] else 'Skipped/Rolled Back'}",
            "green" if up["success"] else "yellow",
        )
    cprint("\nSupreme audit run complete!", "green")

    if TELEGRAM_NOTIFY:
        notify_telegram("Supreme audit run complete. See logs for summary.")

def main_entry():
    """Entry point for Supreme Auditor from menu/CLI."""
    supreme_audit_and_heal()

if __name__ == "__main__":
    main_entry()
