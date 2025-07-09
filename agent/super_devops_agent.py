# agent/super_devops_agent.py

import datetime
import json
import logging
import os
import subprocess
import shutil
from typing import Any, Dict, List, Optional

from agent.event_bus import publish_event
from agent import devops_fixer  # Basic fixer agent as worker
from agent import utils
from agent.config_loader import ConfigLoader

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)

# Load centralized config
config = ConfigLoader.load_config()

# Extract config values for easy use
OPENAI_API_KEY = config.get("openai_api_key")
BACKUP_ROOT = config.get("paths", {}).get("backups_dir", "logs/agent_backups")
SUMMARY_FILE = "logs/upgrade_summaries.json"
RETRIES = config.get("llm", {}).get("retries", 3)
LLM_MODELS = config.get("llm", {}).get("swarm_models", ["gpt-4o", "gpt-4", "gpt-3.5-turbo"])

# Initialize OpenAI client if available
try:
    import openai
except ImportError:
    openai = None

client = openai.OpenAI(api_key=OPENAI_API_KEY) if openai and OPENAI_API_KEY else None

SUPER_AGENT_MEMORY = os.getenv("SUPER_AGENT_MEMORY", "logs/super_agent_memory.json")


def backup_agent(app_name: str, app_dir: str):
    """Backup all .py files in the app_dir using utils.backup_file."""
    backups = []
    py_files = [f for f in os.listdir(app_dir) if f.endswith(".py")]
    for fname in py_files:
        src = os.path.join(app_dir, fname)
        bak = utils.backup_file(src, BACKUP_ROOT, max_backups=config.get("backup", {}).get("retention_count", 5))
        if bak:
            backups.append(bak)
    utils.notify_human(f"Backup for {app_name} saved to {BACKUP_ROOT}/{app_name}")
    return backups


def show_diff(old: str, new: str, fname: str):
    import difflib

    diff = difflib.unified_diff(
        old.splitlines(),
        new.splitlines(),
        fromfile=f"{fname} (old)",
        tofile=f"{fname} (new)",
        lineterm="",
    )
    print("\n".join(diff))


def run_agent_tests(app_dir: str) -> bool:
    try:
        proc = subprocess.run(
            ["pytest", "--maxfail=3", "--disable-warnings", "--tb=short"],
            cwd=app_dir,
            capture_output=True,
            text=True,
            timeout=config.get("testing", {}).get("pytest_timeout_seconds", 120),
        )
        if proc.returncode == 0:
            utils.notify_human("[OK] All tests passed.")
            return True
        else:
            utils.notify_human(f"[FAIL] Tests failed:\n{proc.stdout + proc.stderr}")
            return False
    except Exception as e:
        publish_event(
            "error",
            {"agent": "super_devops_agent", "error": str(e), "timestamp": datetime.datetime.now().isoformat()},
        )
        utils.notify_human(f"[Test runner error] {e}")
        return False


def explain_upgrade(app_name: str, summary: str):
    if not client:
        return f"Upgrade summary for {app_name}: {summary[:200]}..."

    prompt = (
        f"This is an upgrade summary for agent '{app_name}':\n{summary}\n"
        f"Summarize in 2 sentences for a manager. If technical issues, mention next actions."
    )
    resp = utils.llm_call(client, prompt, model=config.get("llm", {}).get("default_model", "gpt-4o"), max_tokens=250, temperature=0.1)
    return resp if resp else summary[:200]


def load_memory() -> Dict:
    try:
        return utils.load_json_file(SUPER_AGENT_MEMORY)
    except Exception as e:
        publish_event(
            "error",
            {"agent": "super_devops_agent", "error": str(e), "timestamp": datetime.datetime.now().isoformat()},
        )
        logging.error(f"Failed to load memory: {e}")
        return {}


def save_memory(mem: Dict) -> None:
    try:
        utils.save_json_file(SUPER_AGENT_MEMORY, mem)
    except Exception as e:
        publish_event(
            "error",
            {"agent": "super_devops_agent", "error": str(e), "timestamp": datetime.datetime.now().isoformat()},
        )
        logging.error(f"Failed to save memory: {e}")


def notify(message: str) -> None:
    utils.notify_human(message)
    # TODO: Integrate Telegram/Discord/email notifications here


def git_branch_workflow(app_dir: str, branch: str = "agent-autofix") -> None:
    def run(cmd: str) -> None:
        try:
            subprocess.run(cmd.split(), cwd=app_dir, capture_output=True, text=True, check=True)
        except subprocess.CalledProcessError as e:
            logging.error(f"Command '{cmd}' failed with error: {e}")

    run("git stash")
    run(f"git checkout -B {branch}")
    run("git stash pop")


def agent_explain(app_dir: str) -> str:
    if not client:
        return "[EXPLAIN] OpenAI SDK not installed"

    prompt = f"Summarize in plain English what was fixed in {app_dir} and why."
    resp = utils.llm_call(client, prompt, model=config.get("llm", {}).get("default_model", "gpt-4o"), max_tokens=1024, temperature=0.1)
    return resp if resp else "[No explanation available]"


def agent_audit(app_dir: str) -> str:
    if not client:
        return "[AUDIT] OpenAI SDK not installed"

    prompt = (
        f"Review this codebase at {app_dir} for security, performance, and best-practices risks. "
        f"Summarize and suggest any further actions."
    )
    resp = utils.llm_call(client, prompt, model=config.get("llm", {}).get("default_model", "gpt-4o"), max_tokens=1024, temperature=0.1)
    return resp if resp else "[No audit available]"


def save_suggestion(app_name: str, model: str, suggestion: List[Dict[str, Any]]) -> None:
    llm_suggestions_dir = config.get("paths", {}).get("llm_suggestions_dir", "logs/llm_suggestions")
    os.makedirs(llm_suggestions_dir, exist_ok=True)
    fname = os.path.join(llm_suggestions_dir, f"{app_name}_{model}_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
    try:
        with open(fname, "w", encoding="utf-8") as f:
            json.dump(suggestion, f, indent=2)
    except Exception as e:
        publish_event(
            "error",
            {"agent": "super_devops_agent", "error": str(e), "timestamp": datetime.datetime.now().isoformat()},
        )
        logging.error(f"Failed to save suggestion: {e}")


def apply_llm_fix(app_dir: str, fixes: List[Dict[str, Any]]) -> None:
    if not isinstance(fixes, list):
        utils.notify_human("[ERROR] LLM fix data invalid.")
        return
    for fix in fixes:
        file = fix.get("file")
        fixed_code = fix.get("full_fixed_code")
        if file and fixed_code:
            target = os.path.join(app_dir, file)
            try:
                with open(target, "w", encoding="utf-8") as f:
                    f.write(fixed_code)
                utils.notify_human(f"[SuperAgent] LLM applied fix to {file}")
            except Exception as e:
                publish_event(
                    "error",
                    {"agent": "super_devops_agent", "error": str(e), "timestamp": datetime.datetime.now().isoformat()},
                )
                logging.error(f"Failed to apply fix to {file}: {e}")


def llm_code_suggest(app_dir: str, error_report: str, model: str = "gpt-4o") -> List[Dict[str, Any]]:
    if not client:
        return []

    prompt = (
        f"As a world-class AI DevOps engineer, review this Python codebase at {app_dir}.\n"
        f"Error report:\n{error_report}\n"
        f"Suggest the minimum, best changes to fix *all* these errors. "
        f"Output a JSON array of (file, fix_description, full_fixed_code)."
    )
    try:
        content = utils.llm_call(client, prompt, model=model, max_tokens=4096, temperature=0)
        fixes = json.loads(content)
    except Exception as e:
        publish_event(
            "error",
            {"agent": "super_devops_agent", "error": str(e), "timestamp": datetime.datetime.now().isoformat()},
        )
        logging.error(f"LLM fix suggestion failed: {e}")
        fixes = [{"model": model, "raw": content if "content" in locals() else ""}]
    return fixes


def auto_commit_and_pr(app_dir: str) -> None:
    git_branch_workflow(app_dir)
    try:
        subprocess.run(["git", "add", "."], cwd=app_dir, check=True)
        subprocess.run(
            ["git", "commit", "-m", "SuperAgent: Auto-fixed and audited code hygiene"], cwd=app_dir, check=True
        )
        # TODO: Add GitHub CLI or API for PR if desired
    except subprocess.CalledProcessError as e:
        logging.error(f"Git operation failed: {e}")


def save_upgrade_summary(app_name: str, summary: str, result: str):
    os.makedirs(os.path.dirname(SUMMARY_FILE), exist_ok=True)
    all_logs = utils.load_json_file(SUMMARY_FILE, default=[])
    all_logs.append(
        {
            "agent": app_name,
            "summary": summary,
            "result": result,
            "timestamp": datetime.datetime.now().isoformat(),
        }
    )
    utils.save_json_file(SUMMARY_FILE, all_logs)


def run_agentic_devops(app_name: str) -> None:
    app_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "apps", app_name))
    utils.notify_human(f"\n===== SUPER DEVOPS AGENT for {app_name} =====")
    memory = load_memory()

    # --- 1. Backup before any action ---
    backup_agent(app_name, app_dir)

    # --- 2. Spawn basic fixer agent for first pass ---
    devops_fixer.auto_devops_fix(app_name)

    # --- 3. Run LLM "swarm" reasoning on remaining issues, with retries and rollback ---
    flake8_out, mypy_out, bandit_out = devops_fixer.run_linters(app_dir)
    errors = flake8_out + mypy_out + bandit_out
    upgrade_success = False
    upgrade_summary = ""

    for attempt in range(1, RETRIES + 1):
        if errors.strip():
            utils.notify_human(f"\n[SuperAgent] Static issues remain, spawning LLM swarm (attempt {attempt})...")
            swarm_votes = {}
            for model in LLM_MODELS:
                if client:
                    suggestion = llm_code_suggest(app_dir, errors, model)
                    swarm_votes[model] = suggestion
                    save_suggestion(app_name, model, suggestion)
            # Swarm "vote": pick most common fix or fallback to first
            best_fix = (
                max(swarm_votes.values(), key=lambda s: list(swarm_votes.values()).count(s))
                if swarm_votes
                else None
            )
            if best_fix:
                apply_llm_fix(app_dir, best_fix)
                utils.notify_human(f"[SuperAgent] Swarm applied fix from model.")
            else:
                utils.notify_human("[SuperAgent] No fix generated by LLM swarm.")
        else:
            utils.notify_human("[SuperAgent] All issues auto-fixed!")
            upgrade_success = True
            upgrade_summary = "All static issues auto-fixed."
            break

        # --- 4. Run tests, rollback if needed ---
        if run_agent_tests(app_dir):
            notify(f"SuperAgent: All tests passed. Auto-commit/PR ready for {app_name}.")
            auto_commit_and_pr(app_dir)
            upgrade_success = True
            upgrade_summary = agent_explain(app_dir)
            break
        else:
            notify(f"SuperAgent: Tests failed after fixes (attempt {attempt}). Rolling back to backup.")
            # Rollback all .py files from backup
            backup_dir = os.path.join(BACKUP_ROOT, app_name)
            backup_files = [f for f in os.listdir(backup_dir) if f.endswith(".bak")]
            latest = max(backup_files) if backup_files else None
            if latest:
                bak_path = os.path.join(backup_dir, latest)
                # Copy back over all .py files (if multi-file backup desired, loop here)
                for fname in os.listdir(app_dir):
                    if fname.endswith(".py"):
                        shutil.copyfile(bak_path, os.path.join(app_dir, fname))
                utils.notify_human(f"[ROLLBACK] Rolled back {app_name} to backup.")
            if attempt == RETRIES:
                upgrade_success = False
                upgrade_summary = "Upgrade failed after 3 attempts."

    # --- 5. Self-reflection loop (auto-explain and audit) ---
    explain = agent_explain(app_dir)
    audit = agent_audit(app_dir)
    memory.update(
        {
            "last_explain": explain,
            "last_audit": audit,
            "last_run": str(datetime.datetime.now()),
        }
    )
    save_memory(memory)
    save_upgrade_summary(app_name, explain, "Success" if upgrade_success else "Failed")

    # --- 6. Log all actions and summaries ---
    log_filename = f"logs/{app_name}_autofix_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
    try:
        os.makedirs(os.path.dirname(log_filename), exist_ok=True)
        with open(log_filename, "w", encoding="utf-8") as logf:
            logf.write(f"EXPLAIN:\n{explain}\n\nAUDIT:\n{audit}\n\n")
    except Exception as e:
        publish_event(
            "error",
            {"agent": "super_devops_agent", "error": str(e), "timestamp": datetime.datetime.now().isoformat()},
        )
        logging.error(f"Failed to write log: {e}")

    # --- 7. Summary output for user ---
    summary_txt = explain_upgrade(app_name, upgrade_summary)
    utils.notify_human(f"\n[SUMMARY] {app_name}: {summary_txt}")


# --- Menu entry point ---
def main_entry(app: Optional[str] = None) -> None:
    if not app:
        from agent.main import choose_app

        app = choose_app()
    if app:
        run_agentic_devops(app)


if __name__ == "__main__":
    main_entry()
