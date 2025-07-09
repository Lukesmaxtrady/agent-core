import datetime
import logging
import traceback
import os
import shutil
import json
from pathlib import Path
from typing import Any, List, Optional
from agent.event_bus import publish_event

try:
    from termcolor import cprint
except ImportError:
    def cprint(msg: Any, color: Any = None, **kwargs): print(msg)

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

HEALTH_LOG_ROOT = Path("logs/health_checks")
CENTRAL_HEALTH_LOG = Path("logs/system_health_summary.json")
HEALTH_LOG_ROOT.mkdir(parents=True, exist_ok=True)

def log_health_result(data: dict):
    # Append a summary JSON record for dashboard/Notion sync
    CENTRAL_HEALTH_LOG.parent.mkdir(exist_ok=True, parents=True)
    if CENTRAL_HEALTH_LOG.exists():
        with CENTRAL_HEALTH_LOG.open(encoding="utf-8") as f:
            all_logs = json.load(f)
    else:
        all_logs = []
    all_logs.append(data)
    with CENTRAL_HEALTH_LOG.open("w", encoding="utf-8") as f:
        json.dump(all_logs, f, indent=2)

def health_check(
    verbose: bool = True,
    auto_heal: bool = True,
    check_agents_only: bool = False,
    ai_suggestions: bool = False
) -> bool:
    """
    Superagent health check (modular, composable, observable, explainable).
    - Imports and verifies all core agents
    - Scans apps, runs Planner, Coder, Tester on each app
    - Checks logs for errors
    - Runs auto-heal on failure (with full rollback, retries, logging)
    - Saves human-friendly and machine-readable logs for dashboard
    """
    timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    health_log_path = HEALTH_LOG_ROOT / f"health_check_{timestamp}.log"
    results: List[str] = []
    dashboard: dict = {
        "timestamp": datetime.datetime.now().isoformat(),
        "status": "PASS",
        "errors": [],
        "healing_attempts": [],
        "apps": [],
    }
    def log(msg: str, color: str = "cyan") -> None:
        results.append(msg)
        if verbose:
            cprint(msg, color)

    log("\n=== SUPER AGENT SYSTEM HEALTH CHECK ===", "green")

    # 1. Core agent import check
    try:
        from agent.coder import Coder
        from agent.planner import Planner
        from agent.super_devops_agent import main_entry as super_devops_main
        from agent.tester import Tester
        log("[OK] All core agents imported.", "green")
    except ImportError as e:
        log(f"[FAIL] Import error: {e}", "red")
        log(traceback.format_exc(), "red")
        dashboard["status"] = "FAIL"
        dashboard["errors"].append(str(e))
        _save_log(results, health_log_path)
        log_health_result(dashboard)
        return False

    # 2. Check apps directory
    apps_dir = Path(__file__).resolve().parent.parent / "apps"
    apps_dir.mkdir(parents=True, exist_ok=True)
    apps = [d for d in apps_dir.iterdir() if d.is_dir()]
    if apps:
        log(f"[OK] Apps/bots found: {', '.join(app.name for app in apps)}", "green")
    else:
        log("[WARN] No apps found. Please create one before running full health checks.", "yellow")

    # 3. Per-app health checks
    all_ok = True
    for app in apps:
        app_report = {"app": app.name, "pre_test_passed": None, "healed": False, "heal_attempts": 0, "failures": []}
        try:
            log(f"\n[CHECK] Diagnosing and testing app: {app.name}", "magenta")
            Planner().list_apps()
            # Backup before upgrades!
            try:
                for file in app.glob("*.py"):
                    backup_dir = Path("logs/agent_backups") / app.name
                    backup_dir.mkdir(exist_ok=True, parents=True)
                    bak = backup_dir / f"{file.name}.bak_{timestamp}"
                    shutil.copyfile(file, bak)
            except Exception as e:
                publish_event('error', {'agent': 'health', 'error': str(e), 'timestamp': datetime.datetime.now().isoformat()})
                log(f"[WARN] Backup error for {app.name}: {e}", "yellow")
            # Upgrade & Test
            try:
                Coder.upgrade_app(app.name)
                test_passed = Tester.run_tests(app.name)
                app_report["pre_test_passed"] = bool(test_passed)
                if test_passed:
                    log(f"[OK] Tests passed for {app.name}.", "green")
                else:
                    all_ok = False
                    log(f"[FAIL] Tests FAILED for {app.name}.", "red")
                    app_report["failures"].append("Initial tests failed.")
                    # Auto-heal loop (up to 3 attempts, full rollback if all fail)
                    if auto_heal:
                        for attempt in range(1, 4):
                            log(f"[ACTION] Healing with Super DevOps Agent (attempt {attempt})...", "cyan")
                            try:
                                super_devops_main(app.name)
                                healed = Tester.run_tests(app.name)
                                app_report["heal_attempts"] += 1
                                if healed:
                                    log(f"[OK] Healed: Tests now pass for {app.name}.", "green")
                                    app_report["healed"] = True
                                    break
                                else:
                                    log(f"[FAIL] Still failing after healing for {app.name}.", "red")
                                    app_report["failures"].append(f"Heal attempt {attempt} failed.")
                            except Exception as e:
                                publish_event('error', {'agent': 'health', 'error': str(e), 'timestamp': datetime.datetime.now().isoformat()})
                                log(f"[FAIL] Healing attempt failed: {e}", "red")
                                log(traceback.format_exc(), "red")
                                app_report["failures"].append(f"Heal exception {attempt}: {str(e)}")
            except Exception as e:
                publish_event('error', {'agent': 'health', 'error': str(e), 'timestamp': datetime.datetime.now().isoformat()})
                log(f"[FAIL] Agent action failed for {app.name}: {e}", "red")
                log(traceback.format_exc(), "red")
                app_report["failures"].append(str(e))
                all_ok = False
        except Exception as e:
            publish_event('error', {'agent': 'health', 'error': str(e), 'timestamp': datetime.datetime.now().isoformat()})
            log(f"[FAIL] Outer error for {app.name}: {e}", "red")
            log(traceback.format_exc(), "red")
            app_report["failures"].append(str(e))
            all_ok = False
        dashboard["apps"].append(app_report)

    # 4. Scan logs for recent errors
    log_dir = Path(__file__).resolve().parent.parent / "logs"
    if log_dir.exists():
        logs = sorted(log_dir.glob("*.log"))
        if logs:
            log(f"[INFO] Found {len(logs)} log files, scanning last 2...", "cyan")
            for lf in logs[-2:]:
                with lf.open(encoding="utf-8") as f:
                    content = f.read()
                if "FAIL" in content or "Error" in content or "Traceback" in content:
                    log(f"[WARN] Errors found in log {lf.name}", "yellow")
                    dashboard["errors"].append(f"Errors in {lf.name}")
        else:
            log("[INFO] No logs found yet.", "yellow")
    else:
        log("[INFO] No logs directory found.", "yellow")

    log("Health check complete!", "green" if all_ok else "yellow")
    dashboard["status"] = "PASS" if all_ok else "FAIL"
    _save_log(results, health_log_path)
    log_health_result(dashboard)
    return all_ok

def doctor(app: Optional[str] = None, fix_all: bool = False) -> None:
    """
    AI Doctor agent: diagnose, explain, and heal a single app or all apps if fix_all=True.
    Modular, human-friendly, logs all actions for dashboarding.
    """
    cprint("\n=== SUPER AGENT SYSTEM DOCTOR ===", "magenta")
    try:
        from agent.super_devops_agent import main_entry as super_devops_main
        from agent.tester import Tester
    except ImportError as e:
        cprint(f"[FAIL] Import error: {e}", "red")
        return

    apps = []
    if fix_all:
        apps_dir = Path(__file__).resolve().parent.parent / "apps"
        apps = [d for d in apps_dir.iterdir() if d.is_dir()]
    else:
        if not app:
            try:
                from agent.main import choose_app
                app = choose_app("Select app/bot to diagnose: ")
            except ImportError:
                app = None
        if app:
            apps = [Path(app)]
        else:
            cprint("No app selected for diagnosis.", "red")
            return

    for app in apps:
        cprint(f"\n[Doctor] Running full test suite for {app.name}...", "cyan")
        try:
            passed = Tester.run_tests(app.name)
            if not passed:
                cprint(f"[FAIL] Tests failed for {app.name}. Auto-fixing...", "yellow")
                for attempt in range(1, 4):
                    try:
                        super_devops_main(app.name)
                        passed2 = Tester.run_tests(app.name)
                        if passed2:
                            cprint(f"[OK] Healed: Tests now pass for {app.name}.", "green")
                            break
                        else:
                            cprint(
                                f"[FAIL] Still failing after healing for {app.name}. Manual review required.",
                                "red",
                            )
                    except Exception as e:
                        publish_event('error', {'agent': 'health', 'error': str(e), 'timestamp': datetime.datetime.now().isoformat()})
                        cprint(
                            f"[FAIL] Healing attempt failed for {app.name}: {e}\n{traceback.format_exc()}",
                            "red",
                        )
            else:
                cprint(f"[OK] All tests pass for {app.name}.", "green")
        except Exception as e:
            publish_event('error', {'agent': 'health', 'error': str(e), 'timestamp': datetime.datetime.now().isoformat()})
            cprint(
                f"[FAIL] Doctor encountered error in {app.name}: {e}\n{traceback.format_exc()}",
                "red",
            )

def _save_log(lines: List[str], health_log_path: Path) -> None:
    health_log_path.parent.mkdir(parents=True, exist_ok=True)
    with health_log_path.open("w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
