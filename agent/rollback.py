# agent/rollback.py

import os
import json
import datetime
import shutil
from pathlib import Path
import difflib

from agent.event_bus import publish_event
from agent import utils

# Optional: For LLM summaries/explanations (comment out if not used)
try:
    import openai
except ImportError:
    openai = None

def get_diff_summary(file_a: str, file_b: str) -> str:
    """Return a short diff summary (last 20 lines) between two files."""
    if not os.path.exists(file_a) or not os.path.exists(file_b):
        return ""
    with open(file_a, encoding="utf-8") as fa, open(file_b, encoding="utf-8") as fb:
        a_lines = fa.readlines()
        b_lines = fb.readlines()
    diff = list(difflib.unified_diff(a_lines, b_lines, fromfile="current", tofile="backup"))
    return "".join(diff[-20:]) if diff else "(No diff)"

def explain_rollback(file: str, diff_summary: str, client=None) -> str:
    """LLM-powered summary of what will change (requires OpenAI key)."""
    if not client:
        return f"Rollback for {file}: (Diff not shown; OpenAI not available)"
    prompt = (
        f"This is a rollback diff for agent file '{file}':\n{diff_summary}\n"
        "Summarize the most important changes."
    )
    try:
        return utils.llm_call(client, prompt, model="gpt-4o", max_tokens=120, temperature=0.1) or ""
    except Exception as e:
        return f"LLM summary failed: {e}"

def rollback_all_backups(agent_dir: str, dry_run: bool = False, client=None) -> bool:
    """
    Rolls back every .py file in the agent directory to its most recent backup.
    Publishes rollback events and summaries for system-wide audit.
    """
    backup_root = Path("logs/agent_backups")
    restored_count = 0
    errors = []
    rollback_summaries = []

    if not backup_root.exists():
        utils.notify_human(f"[Rollback] No backup directory found at {backup_root}.")
        return False

    for agent_folder in backup_root.iterdir():
        if not agent_folder.is_dir():
            continue
        agent_name = agent_folder.name
        bak_files = sorted(agent_folder.glob("*.bak*"), reverse=True)
        if not bak_files:
            continue
        # Rollback latest backup only per agent for safety
        latest_bak = bak_files[0]
        target = Path(agent_dir) / f"{agent_name}.py"
        if target.exists():
            diff_summary = get_diff_summary(str(target), str(latest_bak))
            explain = explain_rollback(str(target), diff_summary, client)
            rollback_summaries.append({"file": str(target), "diff": diff_summary, "explain": explain})
            if dry_run:
                utils.notify_human(f"[DRY RUN] Would roll back {target} from {latest_bak}\nDiff summary:\n{diff_summary}\nLLM: {explain}\n")
                continue
            try:
                shutil.copyfile(latest_bak, target)
                restored_count += 1
                utils.notify_human(f"[Rollback] Rolled back {target} from {latest_bak}")
                publish_event("rollback", {
                    "agent": agent_name,
                    "backup_file": str(latest_bak),
                    "restored_file": str(target),
                    "timestamp": datetime.datetime.now().isoformat()
                })
            except Exception as e:
                errors.append((str(target), str(e)))
        else:
            errors.append((str(target), "Target file does not exist."))

    # Post-rollback syntax check
    post_errors = []
    for agent_folder in backup_root.iterdir():
        agent_name = agent_folder.name
        py_file = Path(agent_dir) / f"{agent_name}.py"
        if py_file.exists():
            try:
                compile(open(py_file).read(), py_file.name, 'exec')
            except Exception as e:
                post_errors.append((str(py_file), str(e)))
                utils.notify_human(f"[Rollback] Syntax error after rollback in {py_file}: {e}")

    msg = f"Rollback complete: {restored_count} files restored."
    utils.notify_human(msg)
    if errors or post_errors:
        utils.notify_human("[Rollback] Some errors occurred:")
        for t, e in errors + post_errors:
            utils.notify_human(f"  - {t}: {e}")

    publish_event("rollback_summary", {
        "restored_count": restored_count,
        "errors": errors + post_errors,
        "summaries": rollback_summaries,
    })

    # Write rollback summary to a file for audit
    summary_data = {
        "time": datetime.datetime.now().isoformat(),
        "restored_count": restored_count,
        "errors": errors + post_errors,
        "summaries": rollback_summaries,
    }
    out_json = Path("logs/rollback_summary.json")
    utils.save_json_file(str(out_json), summary_data)
    utils.notify_human(f"[Rollback] Saved rollback summary to {out_json}")

    return restored_count > 0

def rollback_single_agent(agent_name: str, agent_dir: str, client=None) -> bool:
    """
    Rolls back a single agent's .py file from the most recent backup.
    """
    backup_dir = Path("logs/agent_backups") / agent_name
    py_file = Path(agent_dir) / f"{agent_name}.py"
    if not backup_dir.exists():
        utils.notify_human(f"[Rollback] No backup directory for {agent_name}.")
        return False
    bak_files = sorted(backup_dir.glob("*.bak*"), reverse=True)
    if not bak_files:
        utils.notify_human(f"[Rollback] No backup files found for {agent_name}.")
        return False
    latest_bak = bak_files[0]
    diff_summary = get_diff_summary(str(py_file), str(latest_bak))
    explain = explain_rollback(str(py_file), diff_summary, client)
    utils.notify_human(f"Rolling back {py_file} from {latest_bak}\nDiff summary:\n{diff_summary}\nLLM: {explain}")
    try:
        shutil.copyfile(latest_bak, py_file)
        utils.notify_human(f"[Rollback] {agent_name} restored from {latest_bak}")
        publish_event("rollback", {
            "agent": agent_name,
            "backup_file": str(latest_bak),
            "restored_file": str(py_file),
            "timestamp": datetime.datetime.now().isoformat()
        })
        return True
    except Exception as e:
        utils.notify_human(f"[Rollback] Error restoring {agent_name}: {e}")
        return False

def main_entry():
    """
    CLI entry point for full system rollback.
    Interactive: shows diffs, asks for confirmation, supports dry-run.
    """
    agent_dir = os.path.abspath(os.path.join(os.path.dirname(__file__)))
    dry_run = input("Show what would be rolled back (no files changed)? (y/N): ").strip().lower() in ("y", "yes")
    if not dry_run:
        confirm = input("Are you SURE you want to rollback ALL agent upgrades? This cannot be undone. (y/N): ").strip().lower()
        if confirm not in ("y", "yes"):
            utils.notify_human("Rollback cancelled.")
            return
    rollback_all_backups(agent_dir, dry_run=dry_run, client=None if openai is None else openai.OpenAI(api_key=os.environ.get("OPENAI_API_KEY")))

if __name__ == "__main__":
    main_entry()
