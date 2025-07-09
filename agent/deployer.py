import datetime
import json
import logging
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Callable, List, Optional, Dict, Any
from agent.event_bus import publish_event, publish_response, start_listener_in_thread

import requests  # Ensure requests library is installed

try:
    from termcolor import cprint
except ImportError:
    def cprint(msg, color=None, **kwargs): print(msg)

# Configuration
DEPLOYER_LOG = "logs/deployer_activity.json"
BACKUP_ROOT = "logs/agent_backups/deployer"
RETRIES = 3

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)

def _log_action(action: str, details: dict = None):
    os.makedirs(os.path.dirname(DEPLOYER_LOG), exist_ok=True)
    if os.path.exists(DEPLOYER_LOG):
        with open(DEPLOYER_LOG, encoding="utf-8") as f:
            all_logs = json.load(f)
    else:
        all_logs = []
    entry = {
        "timestamp": datetime.datetime.now().isoformat(),
        "action": action,
        "details": details or {}
    }
    all_logs.append(entry)
    with open(DEPLOYER_LOG, "w", encoding="utf-8") as f:
        json.dump(all_logs, f, indent=2)

class Deployer:
    @staticmethod
    def backup_folder(src: str, backup_dir: str) -> str:
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        base_name = f"{Path(src).name}_bak_{timestamp}"
        bak_path = Path(backup_dir) / base_name
        shutil.make_archive(str(bak_path), "zip", src)
        return str(bak_path) + ".zip"

    @staticmethod
    def backup_all_py_files(app_dir: Path) -> List[str]:
        backup_dir = Path(BACKUP_ROOT) / app_dir.name
        backup_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        backups = []
        for file in app_dir.glob("*.py"):
            bak = backup_dir / f"{file.stem}_{timestamp}{file.suffix}"
            shutil.copyfile(file, bak)
            backups.append(str(bak))
        logging.info(f"Backed up all .py files for {app_dir.name} to {backup_dir}")
        return backups

    @staticmethod
    def health_check(app_name: str, custom_checks: Optional[List[Callable[[], bool]]] = None) -> bool:
        results = []
        # 1. HTTP check (simple)
        try:
            resp = requests.get("http://localhost:8000/status", timeout=3)
            results.append(resp.status_code == 200)
        except Exception as e:
            publish_event('error', {'agent': 'deployer', 'error': str(e), 'timestamp': datetime.datetime.now().isoformat()})  # [event_bus hook]
            logging.error(f"HTTP check failed: {e}")
            results.append(False)

        # 2. Process check: look for running python bot.py process
        app_dir = Path(__file__).resolve().parent.parent / "apps" / app_name
        main_file = str(app_dir / "bot.py")
        try:
            if sys.platform == "win32":
                output = subprocess.check_output(
                    ["tasklist", "/FI", "IMAGENAME eq python.exe", "/V"], text=True
                )
                results.append("bot.py" in output)
            else:
                output = subprocess.check_output(["ps", "aux"], text=True)
                results.append(main_file in output)
        except Exception as e:
            publish_event('error', {'agent': 'deployer', 'error': str(e), 'timestamp': datetime.datetime.now().isoformat()})  # [event_bus hook]
            logging.error(f"Process check failed: {e}")
            results.append(False)

        # 3. Custom additional checks if provided
        if custom_checks:
            for fn in custom_checks:
                try:
                    results.append(fn())
                except Exception as e:
                    publish_event('error', {'agent': 'deployer', 'error': str(e), 'timestamp': datetime.datetime.now().isoformat()})  # [event_bus hook]
                    logging.error(f"Custom check failed: {e}")
                    results.append(False)

        return all(results)

    @staticmethod
    def kill_process(app_dir: str, main_file: str) -> None:
        try:
            if sys.platform == "win32":
                subprocess.call(
                    ["taskkill", "/F", "/FI", f"WINDOWTITLE eq {Path(main_file).name}"],
                    shell=True,
                )
            else:
                subprocess.call(["pkill", "-f", main_file], shell=True)
        except Exception as e:
            publish_event('error', {'agent': 'deployer', 'error': str(e), 'timestamp': datetime.datetime.now().isoformat()})  # [event_bus hook]
            logging.error(f"Failed to kill process: {e}")

    @staticmethod
    def start_process(app_dir: str, main_file: str) -> None:
        try:
            if sys.platform == "win32":
                subprocess.Popen(
                    ["python", main_file],
                    cwd=app_dir,
                    creationflags=subprocess.DETACHED_PROCESS
                    | subprocess.CREATE_NEW_PROCESS_GROUP,
                )
            else:
                subprocess.Popen(
                    ["nohup", "python", main_file],
                    cwd=app_dir,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    preexec_fn=os.setpgrp,  # Detach process group on Unix
                )
        except Exception as e:
            publish_event('error', {'agent': 'deployer', 'error': str(e), 'timestamp': datetime.datetime.now().isoformat()})  # [event_bus hook]
            logging.error(f"Failed to start process: {e}")

    @staticmethod
    def deploy_app(app_name: str) -> None:
        from agent.tester import Tester

        app_dir = Path(__file__).resolve().parent.parent / "apps" / app_name
        logs_dir = app_dir / "logs"
        logs_dir.mkdir(exist_ok=True)

        if not (app_dir / "bot.py").exists():
            logging.error(f"Deployment failed: bot.py not found in {app_dir}")
            return

        # --- Backup
        logging.info("Running pre-deploy tests...")
        Tester.run_tests(app_name, auto_generate=False)
        logging.info("Backing up all .py files and app folder...")
        backup_paths = Deployer.backup_all_py_files(app_dir)
        backup_zip = Deployer.backup_folder(str(app_dir), backup_dir=str(logs_dir))
        logging.info(f"Backups created: {backup_paths} and {backup_zip}")

        # --- Git update if .git exists
        git_updated = False
        if (app_dir / ".git").exists():
            logging.info("Pulling latest changes from git repo...")
            try:
                subprocess.run(["git", "pull"], cwd=app_dir, check=True)
                git_updated = True
            except Exception as e:
                publish_event('error', {'agent': 'deployer', 'error': str(e), 'timestamp': datetime.datetime.now().isoformat()})  # [event_bus hook]
                logging.error(f"Git pull failed: {e}")
                return

        main_file = app_dir / "bot.py"

        # --- Restart app process
        logging.info("Stopping previous app process (if any)...")
        Deployer.kill_process(str(app_dir), str(main_file))
        logging.info("Starting app process...")
        Deployer.start_process(str(app_dir), str(main_file))
        time.sleep(5)  # Give app time to start

        # --- Post-deploy tests and health check
        logging.info("Running post-deploy tests and health check...")
        Tester.run_tests(app_name, auto_generate=False)
        healthy = Deployer.health_check(app_name)
        logging.info(f"Health check {'passed' if healthy else 'failed'}.")

        # --- Rollback on failure
        if not healthy:
            logging.error("Health check failed. Rolling back deployment...")
            try:
                shutil.unpack_archive(backup_zip, app_dir, "zip")
                Deployer.kill_process(str(app_dir), str(main_file))
                logging.info("Rollback complete. Please investigate and fix issues before redeploy.")
            except Exception as e:
                publish_event('error', {'agent': 'deployer', 'error': str(e), 'timestamp': datetime.datetime.now().isoformat()})  # [event_bus hook]
                logging.error(f"Rollback failed: {e}")
            _log_action("deploy_app", {
                "app": app_name,
                "status": "rollback",
                "backup_zip": backup_zip,
                "timestamp": datetime.datetime.now().isoformat()
            })
            return

        logging.info("Deployment succeeded and is healthy!")
        publish_event('test', {'agent': 'deployer', 'result': 'pass', 'timestamp': datetime.datetime.now().isoformat()})  # [event_bus hook]

        # --- Log deployment details (for dashboard/CI/CD)
        deploy_info = {
            "deployed_at": datetime.datetime.now().isoformat(),
            "health": healthy,
            "backup_zip": backup_zip,
            "git_updated": git_updated,
            "app_dir": str(app_dir),
        }
        log_path = logs_dir / f"deploy_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
        with open(log_path, "w", encoding="utf-8") as logf:
            json.dump(deploy_info, logf, indent=2)
        _log_action("deploy_app", deploy_info)

        # --- Append deployment record to memory.json
        mem_path = app_dir / "memory.json"
        try:
            mem = {}
            if mem_path.exists():
                with open(mem_path, encoding="utf-8") as mf:
                    mem = json.load(mf)
            mem.setdefault("deployments", []).append(deploy_info)
            with open(mem_path, "w", encoding="utf-8") as mf:
                json.dump(mem, mf, indent=2)
        except Exception as e:
            publish_event('error', {'agent': 'deployer', 'error': str(e), 'timestamp': datetime.datetime.now().isoformat()})  # [event_bus hook]
            logging.error(f"Failed to update memory.json: {e}")

    @staticmethod
    def explain_last_deploy(app_name: str) -> None:
        app_dir = Path(__file__).resolve().parent.parent / "apps" / app_name
        logs_dir = app_dir / "logs"
        if not logs_dir.exists():
            logging.info("No logs directory found for this app.")
            return
        logs = sorted([f for f in logs_dir.iterdir() if f.name.startswith("deploy_")])
        if logs:
            log_path = logs[-1]
            with open(log_path, encoding="utf-8") as f:
                cprint(f"\n--- LAST DEPLOY LOG for {app_name} ---\n{f.read()}", "cyan")
        else:
            logging.info("No deployment logs found.")

    # Ready for further upgrades: event hooks, Notion sync, dashboard POST, CI/CD, etc.

# ========== EVENT BUS HANDLER ==========

def handle_deploy_request(event):
    """
    Auto-injected event handler for 'deploy_request' in this agent.
    """
    print(f"[EventBus] Received deploy_request: {event}")
    # TODO: Replace this with agent logic.
    result = {"status": "handled", "details": f"deploy_request handled by agent."}
    publish_response("deploy_result", result, correlation_id=event.get("correlation_id"))

start_listener_in_thread(handle_deploy_request, event_types=["deploy_request"])
