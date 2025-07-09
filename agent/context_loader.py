import os
import json
from pathlib import Path
from dotenv import dotenv_values
from typing import Dict, Any, List, Optional
import logging
import datetime
from agent.event_bus import publish_event

# Config
CONTEXT_LOG = "logs/context_loader_activity.json"
MAX_LENGTH = 100_000
LOG_COUNT = 5
DATA_SAMPLE_MAX_LENGTH = 5000
SENSITIVE_KEYS = {"api_key", "token", "password", "secret", "key"}

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)

def _log_action(action: str, details: Optional[dict] = None):
    os.makedirs("logs", exist_ok=True)
    if Path(CONTEXT_LOG).exists():
        with open(CONTEXT_LOG, encoding="utf-8") as f:
            all_logs = json.load(f)
    else:
        all_logs = []
    entry = {
        "timestamp": datetime.datetime.now().isoformat(),
        "action": action,
        "details": details or {}
    }
    all_logs.append(entry)
    with open(CONTEXT_LOG, "w", encoding="utf-8") as f:
        json.dump(all_logs, f, indent=2)

def safe_read(path: Path, mode: str = "r", max_length: int = MAX_LENGTH) -> str:
    """
    Read file contents safely, handling encoding errors and large files.
    Tries multiple encodings and replaces invalid bytes.
    Truncates content with '[TRUNCATED]' if exceeding max_length.
    """
    encodings_to_try = ["utf-8", "latin-1", "cp1252"]
    for enc in encodings_to_try:
        try:
            with path.open(mode, encoding=enc, errors="replace") as f:
                data = f.read(max_length + 1)
                if len(data) > max_length:
                    return data[:max_length] + "\n...[TRUNCATED]"
                return data
        except (UnicodeDecodeError, FileNotFoundError, IOError):
            continue
    return f"[ERROR reading {path}: unable to decode with tried encodings]"

def load_env(env_path: Path) -> Dict[str, str]:
    """
    Parse .env file as a dict, masking sensitive keys like API keys, tokens, secrets.
    """
    env_data = dotenv_values(env_path)
    masked = {}
    for k, v in env_data.items():
        if k.lower() in SENSITIVE_KEYS:
            masked[k] = (v[:5] + "...") if v and len(v) > 5 else v
        else:
            masked[k] = v
    return masked

def load_files(
    base_dir: Path, patterns: List[str], context_key: str, context: Dict[str, Any], preview: bool = False, max_length: int = DATA_SAMPLE_MAX_LENGTH
) -> None:
    """
    Helper to load files matching patterns recursively into context dictionary.
    Uses safe_read with preview mode for large files.
    """
    for pattern in patterns:
        for path in base_dir.rglob(pattern):
            try:
                key = path.name
                content = safe_read(path, max_length=max_length if preview else MAX_LENGTH)
                context[context_key][key] = content
            except Exception as e:
                publish_event('error', {'agent': 'context_loader', 'error': str(e), 'timestamp': datetime.datetime.now().isoformat()})  # [event_bus hook]
                logging.error(f"Error loading file {path}: {e}")

def load_json_file(file_path: Path) -> Dict[str, Any]:
    try:
        with file_path.open(encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        publish_event('error', {'agent': 'context_loader', 'error': str(e), 'timestamp': datetime.datetime.now().isoformat()})  # [event_bus hook]
        logging.error(f"Error loading JSON file {file_path}: {e}")
        return {}

def load_app_context(app_name: str) -> Dict[str, Any]:
    """
    Load the full app context for a given app_name:
    - code files (.py, test_*.py)
    - config files (.json, .yaml, .yml, .ini, .env)
    - last 5 logs
    - goals.md content
    - metrics.json as dict
    - docs (.md, .txt)
    - persistent memory (memory.json)
    - test previews (test_*.py, truncated)
    - sample data files (first 2 files, truncated)
    """
    base_dir = Path(__file__).resolve().parent.parent / "apps" / app_name
    context = {
        "code_files": {},  # .py files
        "configs": {},     # .json, .yaml, .env, .ini
        "logs": [],        # last 5 logs as dicts with filename and content
        "goals": "",       # goals.md full text
        "metrics": {},     # metrics.json dict
        "docs": {},        # markdown, txt files
        "memory": {},      # persistent memory from memory.json
        "tests": {},       # test_*.py preview
        "data_samples": {},# sample data files truncated
    }

    _log_action("load_app_context_start", {"app_name": app_name})

    # Load code files
    load_files(base_dir, ["*.py", "test_*.py"], "code_files", context)

    # Load config files including .env (mask secrets)
    load_files(base_dir, ["*.json", "*.yaml", "*.yml", "*.ini"], "configs", context)
    env_path = base_dir / ".env"
    if env_path.exists():
        context["configs"][".env"] = load_env(env_path)

    # Load last 5 log files (any extension) from logs/
    logs_dir = base_dir / "logs"
    if logs_dir.exists():
        log_files = sorted(logs_dir.glob("*"))[-LOG_COUNT:]
        for log_file in log_files:
            context["logs"].append(
                {"file": log_file.name, "content": safe_read(log_file)}
            )

    # Load goals.md content if exists
    goals_path = base_dir / "goals.md"
    if goals_path.exists():
        context["goals"] = safe_read(goals_path)

    # Load metrics.json as dict, handle JSON errors gracefully
    metrics_path = base_dir / "metrics.json"
    if metrics_path.exists():
        context["metrics"] = load_json_file(metrics_path)

    # Load documentation files
    load_files(base_dir, ["*.md", "*.txt"], "docs", context)

    # Load persistent agent memory
    memory_path = base_dir / "memory.json"
    if memory_path.exists():
        context["memory"] = load_json_file(memory_path)

    # Load truncated test files previews only
    load_files(base_dir, ["test_*.py"], "tests", context, preview=True)

    # Load first two data sample files (truncate to DATA_SAMPLE_MAX_LENGTH)
    data_dir = base_dir / "data"
    if data_dir.exists():
        data_files = sorted(data_dir.glob("*"))[:2]
        for dfile in data_files:
            key = dfile.name
            context["data_samples"][key] = safe_read(dfile, max_length=DATA_SAMPLE_MAX_LENGTH)

    _log_action("load_app_context_complete", {"app_name": app_name})
    return context
