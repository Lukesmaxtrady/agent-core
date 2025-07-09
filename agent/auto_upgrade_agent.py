import datetime
import difflib
import json
import os
import shutil
import sys
from typing import Any, Dict, List, Tuple
from agent.event_bus import publish_event

try:
    import openai
except ImportError:
    openai = None

try:
    from termcolor import cprint
except ImportError:
    def cprint(msg, color=None, **kwargs): print(msg)

LOG_FILE = "logs/upgrade_history.json"
BACKUP_ROOT = "logs/agent_backups"
SUMMARY_FILE = "logs/upgrade_summaries.json"
RETRIES = 3

def backup_agent(agent_name: str, code: str):
    backup_dir = os.path.join(BACKUP_ROOT, agent_name)
    os.makedirs(backup_dir, exist_ok=True)
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = os.path.join(backup_dir, f"{agent_name}_{timestamp}.bak.py")
    with open(backup_path, "w", encoding="utf-8") as f:
        f.write(code)
    cprint(f"[INFO] Backup for {agent_name} saved to {backup_path}", "yellow")
    return backup_path

def explain_upgrade(agent_name: str, changes: str, summary: str = None) -> str:
    # Short, simple summary for the agent upgrade. Uses LLM if available.
    if not openai or not os.environ.get("OPENAI_API_KEY"):
        return f"Upgraded {agent_name}: {changes[:200]}..."
    prompt = (
        f"Here are the code changes for an AI agent '{agent_name}':\n"
        f"{changes}\n"
        f"Give a short, simple summary anyone can understand. "
        f"If more details wanted, say 'Ask for more details.'"
    )
    try:
        resp = openai.ChatCompletion.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=350,
            temperature=0.1,
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        publish_event('error', {'agent': 'auto_upgrade_agent', 'error': str(e), 'timestamp': datetime.datetime.now().isoformat()})
        return f"Upgraded {agent_name}: {changes[:200]}... (LLM summary failed)"

def show_diff(old: str, new: str, name: str):
    diff = difflib.unified_diff(
        old.splitlines(),
        new.splitlines(),
        fromfile=f"{name}.py (old)",
        tofile=f"{name}.py (new)",
        lineterm="",
    )
    cprint("\n".join(diff), "blue")

def run_agent_tests(agent_path: str) -> Tuple[bool, str]:
    import subprocess
    try:
        proc = subprocess.run(
            [sys.executable, "-m", "pytest", agent_path],
            capture_output=True,
            text=True,
            timeout=120,
        )
        return proc.returncode == 0, proc.stdout + proc.stderr
    except Exception as e:
        publish_event('error', {'agent': 'auto_upgrade_agent', 'error': str(e), 'timestamp': datetime.datetime.now().isoformat()})
        return False, f"[Test runner error] {e}"

def ask(prompt: str) -> str:
    cprint(f"{prompt} (Press Enter to continue or type 'more' for details): ", "yellow", end="")
    return input().strip().lower()

def auto_upgrade_all_agents_superpowered():
    agent_dir = os.path.abspath(os.path.dirname(__file__))
    agent_files = [
        f for f in os.listdir(agent_dir)
        if f.endswith(".py") and f not in ("__init__.py", os.path.basename(__file__))
    ]
    summaries = []
    for file in agent_files:
        agent_name = file[:-3]
        code_path = os.path.join(agent_dir, file)
        with open(code_path, encoding="utf-8") as f:
            orig_code = f.read()

        cprint(f"\n=== Upgrading agent: {agent_name} ===", "cyan", attrs=["bold"])
        backup_path = backup_agent(agent_name, orig_code)
        upgrade_success = False
        upgrade_summary = ""
        last_error = ""
        for attempt in range(1, RETRIES+1):
            # Step 1: Request LLM to propose upgrade/refactor
            if not openai:
                cprint("[ERROR] OpenAI SDK not available. Skipping upgrade.", "red")
                break

            prompt = (
                f"Upgrade/refactor this AI agent for superhuman reliability, "
                f"explainability, speed, and safety. Make all improvements possible for a god-tier AI agent.\n"
                f"Code:\n{orig_code[:8000]}\n"
                f"Output only improved code in a python code block. "
                f"After code, write a brief (2-3 sentences) summary of what was improved and why."
            )
            try:
                resp = openai.ChatCompletion.create(
                    model="gpt-4o",
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=3500,
                    temperature=0.1,
                )
                full_response = resp.choices[0].message.content
                # Extract improved code and summary
                improved_code = ""
                summary = ""
                if "```python" in full_response:
                    improved_code = full_response.split("```python")[1].split("```")[0].strip()
                if "Summary:" in full_response:
                    summary = full_response.split("Summary:")[1].split("\n")[0].strip()
                elif "Improved:" in full_response:
                    summary = full_response.split("Improved:")[1].split("\n")[0].strip()
                else:
                    summary = "Upgrade details not parsed."

                if improved_code and improved_code != orig_code:
                    show_diff(orig_code, improved_code, agent_name)
                    # Write improved code
                    with open(code_path, "w", encoding="utf-8") as f:
                        f.write(improved_code)
                    # Test it
                    ok, test_log = run_agent_tests(agent_dir)
                    if ok:
                        upgrade_success = True
                        upgrade_summary = summary
                        cprint(f"[OK] Upgrade applied and passed tests for {agent_name}.", "green")
                        break
                    else:
                        last_error = f"[Attempt {attempt}] Tests failed:\n{test_log}"
                        cprint(last_error, "red")
                        # Roll back to backup
                        shutil.copyfile(backup_path, code_path)
                        cprint(f"[ROLLBACK] Reverted {agent_name} to backup after failed test.", "yellow")
                        orig_code = open(backup_path, encoding="utf-8").read()
                        if attempt == RETRIES:
                            cprint(f"[FAIL] Upgrade failed for {agent_name} after {RETRIES} attempts.", "red")
                            upgrade_summary = f"Upgrade failed: {last_error}"
                else:
                    cprint(f"[INFO] No substantive code improvement for {agent_name}.", "yellow")
                    upgrade_success = True
                    upgrade_summary = "Already optimal."
                    break
            except Exception as e:
                publish_event('error', {'agent': 'auto_upgrade_agent', 'error': str(e), 'timestamp': datetime.datetime.now().isoformat()})
                last_error = f"[Exception {attempt}] {e}"
                cprint(last_error, "red")
                shutil.copyfile(backup_path, code_path)
                if attempt == RETRIES:
                    cprint(f"[FAIL] Upgrade failed for {agent_name} after {RETRIES} attempts.", "red")
                    upgrade_summary = f"Upgrade failed: {last_error}"

        # Explanation step
        summary_text = explain_upgrade(agent_name, upgrade_summary)
        cprint(f"\n[SUMMARY] {agent_name}: {summary_text}", "magenta")
        summaries.append({
            "agent": agent_name,
            "summary": summary_text,
            "success": upgrade_success
        })

        # Offer deeper explanation
        if ask("Next agent, or type 'more' for details?") == "more":
            cprint(f"\n--- FULL UPGRADE LOG FOR {agent_name} ---\n{upgrade_summary}\n", "blue")
            input("Press Enter to continue...")

    # Save all summaries
    os.makedirs(os.path.dirname(SUMMARY_FILE), exist_ok=True)
    with open(SUMMARY_FILE, "w", encoding="utf-8") as f:
        json.dump(summaries, f, indent=2)

    cprint("\nAll agent upgrades complete!", "green", attrs=["bold"])

# ALIAS for main.py compatibility
auto_upgrade_all_agents = auto_upgrade_all_agents_superpowered

if __name__ == "__main__":
    auto_upgrade_all_agents_superpowered()
