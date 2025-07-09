# agent/utils.py

import os
import json
import logging
import datetime
from typing import Optional

def safe_import(module_name: str, fallback=None):
    try:
        mod = __import__(module_name)
        return mod
    except ImportError:
        return fallback

def notify_human(message: str):
    try:
        from termcolor import cprint
        cprint(f"[ALERT] {message}", "magenta")
    except ImportError:
        print(f"[ALERT] {message}")

def load_json_file(path: str, default=None):
    if default is None:
        default = {}
    try:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception as e:
        logging.error(f"Failed to load JSON from {path}: {e}")
    return default

def save_json_file(path: str, data):
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        logging.error(f"Failed to save JSON to {path}: {e}")

def backup_file(file_path: str, backup_root: str, max_backups: int = 5) -> Optional[str]:
    import shutil
    from pathlib import Path
    file_path = Path(file_path)
    if not file_path.exists():
        return None
    backup_dir = Path(backup_root) / file_path.stem
    backup_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_file = backup_dir / f"{file_path.name}_{timestamp}.bak"

    shutil.copyfile(file_path, backup_file)

    # Prune old backups, keep last max_backups
    backups = sorted(backup_dir.glob(f"{file_path.name}_*.bak"), reverse=True)
    for old_backup in backups[max_backups:]:
        old_backup.unlink()

    logging.info(f"Backup created for {file_path} at {backup_file}")
    return str(backup_file)

def llm_call(client, prompt: str, model: str = "gpt-4o", max_tokens: int = 1500, temperature: float = 0.1):
    try:
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=max_tokens,
            temperature=temperature,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        logging.error(f"LLM call failed: {e}")
        return None
