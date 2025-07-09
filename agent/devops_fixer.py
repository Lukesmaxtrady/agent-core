# agent/devops_fixer.py

import os
import shutil
import subprocess
import logging
import re
from typing import Tuple, Dict, Optional
from pathlib import Path
import datetime
import json
from agent.event_bus import publish_event

try:
    from termcolor import cprint
except ImportError:
    def cprint(msg, color=None, **kwargs): print(msg)

FIXER_LOG = "logs/devops_fixer_activity.json"
BACKUP_ROOT = "logs/agent_backups/devops_fixer"
RETRIES = 3

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)

def _log_action(action: str, details: dict = None):
    os.makedirs(os.path.dirname(FIXER_LOG), exist_ok=True)
    if os.path.exists(FIXER_LOG):
        with open(FIXER_LOG, encoding="utf-8") as f:
            all_logs = json.load(f)
    else:
        all_logs = []
    entry = {
        "timestamp": datetime.datetime.now().isoformat(),
        "action": action,
        "details": details or {}
    }
    all_logs.append(entry)
    with open(FIXER_LOG, "w", encoding="utf-8") as f:
        json.dump(all_logs, f, indent=2)

def backup_file(file_path: Path) -> Optional[Path]:
    try:
        if file_path.exists():
            backup_dir = Path(BACKUP_ROOT)
            backup_dir.mkdir(parents=True, exist_ok=True)
            bak = backup_dir / f"{file_path.stem}.bak_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}{file_path.suffix}"
            shutil.copyfile(file_path, bak)
            logging.info(f"Backup created: {bak}")
            return bak
    except Exception as e:
        publish_event('error', {
            'agent': 'devops_fixer',
            'error': str(e),
            'timestamp': datetime.datetime.now().isoformat()
        })
        logging.error(f"Backup failed: {e}")
    return None

def run_command(cmd: list, cwd: Optional[Path] = None) -> Tuple[bool, str]:
    """Run shell command, return (success, output)."""
    try:
        result = subprocess.run(
            cmd, cwd=str(cwd) if cwd else None, capture_output=True, text=True, check=True
        )
        return True, result.stdout + result.stderr
    except subprocess.CalledProcessError as e:
        logging.error(f"Command failed: {e}")
        return False, (e.stdout or "") + (e.stderr or "")

def run_linters(agent_dir: Path) -> Dict[str, str]:
    """Run static code linters and collect their output."""
    linters = {
        "flake8": ["flake8", str(agent_dir)],
        "mypy": ["mypy", str(agent_dir)],
        "bandit": ["bandit", "-r", str(agent_dir)],
    }
    outputs = {}
    for name, cmd in linters.items():
        _, output = run_command(cmd, cwd=agent_dir)
        outputs[name] = output
    return outputs

def auto_fix_code(agent_dir: Path) -> None:
    """Auto-format code in a directory."""
    formatters = [
        ["black", "."],
        ["autoflake", "--remove-all-unused-imports", "--recursive", "--in-place", "."],
        ["isort", "."]
    ]
    for cmd in formatters:
        run_command(cmd, cwd=agent_dir)

def run_tests(agent_dir: Path) -> bool:
    """Run pytest for the agent directory."""
    ok, output = run_command(["pytest", str(agent_dir)])
    if ok:
        cprint("✅ All tests passed.", "green")
    else:
        cprint("❌ Tests failed. Check logs for details.", "red")
        logging.error(f"Tests failed:\n{output}")
    return ok

def ai_fix_code_with_llm(file_path: Path, error_message: str, model: str = "gpt-4o") -> None:
    """Ask OpenAI to fix code based on linter errors and overwrite file."""
    try:
        import openai
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            logging.error("OPENAI_API_KEY not found in environment.")
            return
        client = openai.OpenAI(api_key=api_key)
    except ImportError:
        logging.warning("OpenAI SDK not installed; skipping LLM code fix.")
        return
    except Exception as e:
        publish_event('error', {
            'agent': 'devops_fixer',
            'error': str(e),
            'timestamp': datetime.datetime.now().isoformat()
        })
        logging.error(f"OpenAI client error: {e}")
        return

    try:
        with file_path.open("r", encoding="utf-8") as f:
            code = f.read()
        prompt = (
            "You are a world-class Python fixer bot.\n"
            "Fix all bugs, style violations, type errors, and apply modern best practices.\n"
            "Only return valid updated code.\n\n"
            f"==== FILE START ====\n{code}\n==== FILE END ====\n"
            f"==== ERRORS ====\n{error_message}\n==== END ===="
        )
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
        )
        fixed_code = response.choices[0].message.content
        backup_file(file_path)
        with file_path.open("w", encoding="utf-8") as f:
            f.write(fixed_code)
        logging.info(f"LLM fixed code in {file_path}")
    except Exception as e:
        publish_event('error', {
            'agent': 'devops_fixer',
            'error': str(e),
            'timestamp': datetime.datetime.now().isoformat()
        })
        logging.error(f"LLM fix failed: {e}")

def fix_all_files_with_ai(agent_dir: Path, error_output: str, model: str = "gpt-4o") -> None:
    """Find all code files mentioned in linter output and fix them with LLM."""
    files = set()
    for match in re.finditer(r"(.+?):\d+:\d+:", error_output):
        raw_path = match.group(1).strip()
        file_path = Path(raw_path) if Path(raw_path).is_absolute() else agent_dir / raw_path
        if file_path.exists():
            files.add(file_path)

    for file in files:
        ai_fix_code_with_llm(file, error_output, model)

def commit_fixes(agent_dir: Path, commit_message: str = "Auto-fixed AI agent code hygiene issues") -> None:
    """Commit code hygiene fixes to git."""
    run_command(["git", "add", "."], cwd=agent_dir)
    run_command(["git", "commit", "-m", commit_message], cwd=agent_dir)

def auto_devops_fix(app_name: Optional[str] = None) -> None:
    """
    DevOps Quick Fix on AI agent system code (agent/ folder or specific app).
    Fully tested, rollback-ready, and explainable.
    """
    agent_dir = Path(__file__).resolve().parent if app_name is None else Path(__file__).resolve().parent / app_name
    _log_action("auto_devops_fix", {"dir": str(agent_dir)})
    if not agent_dir.is_dir():
        logging.error(f"Agent directory not found: {agent_dir}")
        return

    cprint(f"\n=== DevOps Quick Fix: AI Agent Hygiene Scan ===\n→ Path: {agent_dir}", "cyan")

    # Backup all .py files before action
    for file in agent_dir.glob("*.py"):
        backup_file(file)

    linter_outputs = run_linters(agent_dir)
    has_issues = any(output.strip() for output in linter_outputs.values())

    if not has_issues:
        cprint("✅ No code hygiene issues detected. All clean!", "green")
        return

    for name, output in linter_outputs.items():
        if output.strip():
            cprint(f"\n{name.upper()} Issues:\n{output}", "yellow")

    auto_fix_code(agent_dir)

    try:
        import openai
        api_key = os.environ.get("OPENAI_API_KEY")
        if api_key:
            if linter_outputs.get("flake8", "").strip() or linter_outputs.get("mypy", "").strip():
                fix_all_files_with_ai(
                    agent_dir, linter_outputs.get("flake8", "") + linter_outputs.get("mypy", ""), "gpt-4o"
                )
    except ImportError:
        pass
    except Exception as e:
        publish_event('error', {
            'agent': 'devops_fixer',
            'error': str(e),
            'timestamp': datetime.datetime.now().isoformat()
        })
        logging.error(f"Error in AI code fix: {e}")

    if run_tests(agent_dir):
        commit_fixes(agent_dir)
        cprint("✅ Fixes committed to Git.", "green")
    else:
        cprint("❌ Code updated, but some tests failed. Please review manually.", "red")

    _log_action("auto_devops_fix_complete", {"dir": str(agent_dir)})

def main_entry():
    """
    Entry point for DevOps Quick Fix from main.py menu.
    """
    auto_devops_fix()

if __name__ == "__main__":
    main_entry()
