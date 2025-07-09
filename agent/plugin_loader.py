# agent/plugin_loader.py

import os
import sys
import importlib.util
import datetime
import logging
import traceback
import subprocess
from pathlib import Path
from agent.event_bus import publish_event
from agent import utils

PLUGINS_DIR = Path("plugins")
LOGS_DIR = Path("logs/plugin_loader")
LOGS_DIR.mkdir(exist_ok=True)
BACKUP_ROOT = "logs/plugin_backups"

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)

def discover_plugins():
    """Find all .py files in plugins directory."""
    PLUGINS_DIR.mkdir(exist_ok=True)
    plugins = [f for f in PLUGINS_DIR.glob("*.py") if not f.name.startswith("__")]
    return plugins

def scan_metadata(plugin_path: Path):
    """Extract metadata from top-level docstring or `metadata` dict if present."""
    meta = {"file": plugin_path.name}
    try:
        with open(plugin_path, encoding="utf-8") as f:
            src = f.read(2048)
        if 'metadata' in src:
            import ast
            tree = ast.parse(src)
            for node in ast.walk(tree):
                if isinstance(node, ast.Assign):
                    for target in node.targets:
                        if isinstance(target, ast.Name) and target.id == "metadata":
                            meta.update(ast.literal_eval(node.value))
        # Top-level docstring
        if src.strip().startswith('"""'):
            doc = src.split('"""')[1]
            meta['doc'] = doc.strip().split("\n")[0]
    except Exception as e:
        meta["error"] = str(e)
    return meta

def check_requirements():
    """Auto-install requirements.txt if present in /plugins."""
    req_file = PLUGINS_DIR / "requirements.txt"
    if req_file.exists():
        resp = input("requirements.txt detected in /plugins. Install now? (y/n): ")
        if resp.lower().startswith("y"):
            subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", str(req_file)])

def import_plugin(plugin_path: Path):
    """Dynamically import a plugin module by path."""
    try:
        spec = importlib.util.spec_from_file_location(plugin_path.stem, plugin_path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod
    except Exception as e:
        logging.error(f"Failed to import plugin {plugin_path}: {e}")
        utils.notify_human(f"Failed to import plugin {plugin_path.name}: {e}")
        return None

def run_static_analysis(plugin_path: Path):
    """Optionally run bandit/flake8 for security/lint check."""
    try:
        bandit = subprocess.run(["bandit", "-r", str(plugin_path)], capture_output=True, text=True)
        if bandit.returncode != 0:
            return f"Bandit issues:\n{bandit.stdout}"
    except Exception:
        pass
    return "OK"

def run_self_test(mod):
    """Run self_test() if present in plugin."""
    try:
        if hasattr(mod, "self_test"):
            return mod.self_test()
        return None
    except Exception as e:
        return f"[self_test failed] {e}"

def register_plugin(mod, plugin_path):
    """Call register() if present, otherwise log."""
    try:
        if hasattr(mod, "register"):
            mod.register()
            return True
        return False
    except Exception as e:
        logging.error(f"register() failed in {plugin_path}: {e}")
        utils.notify_human(f"register() failed in {plugin_path.name}: {e}")
        return False

def main():
    utils.notify_human("[Plugin Loader] Scanning for new plugins in /plugins ...")
    check_requirements()
    plugins = discover_plugins()
    for plugin_path in plugins:
        print(f"Found plugin: {plugin_path.name}")
        meta = scan_metadata(plugin_path)
        # Backup using utils.backup_file with pruning (keep last 5 backups)
        backup_path = utils.backup_file(str(plugin_path), BACKUP_ROOT, max_backups=5)
        if backup_path:
            logging.info(f"Backup created for {plugin_path.name} at {backup_path}")
        else:
            logging.warning(f"Backup failed or skipped for {plugin_path.name}")

        # Static analysis
        sa_report = run_static_analysis(plugin_path)
        if sa_report != "OK":
            print(f"Static analysis failed for {plugin_path.name}:")
            print(sa_report)
            publish_event("plugin_static_analysis_failed", {
                "plugin": plugin_path.name,
                "report": sa_report,
                "timestamp": datetime.datetime.now().timestamp(),
            })
            utils.notify_human(f"Static analysis failed for {plugin_path.name}")
            continue

        mod = import_plugin(plugin_path)
        if not mod:
            logging.error(f"Import failed for {plugin_path.name}")
            publish_event("plugin_failed", {
                "plugin": plugin_path.name,
                "stage": "import",
                "timestamp": datetime.datetime.now().timestamp(),
            })
            continue

        # Lifecycle: on_load()
        if hasattr(mod, "on_load"):
            try:
                mod.on_load()
            except Exception as e:
                logging.error(f"on_load failed for {plugin_path.name}: {e}")
                utils.notify_human(f"on_load failed for {plugin_path.name}: {e}")

        # Self-test
        test_result = run_self_test(mod)
        if test_result is False or (isinstance(test_result, str) and "fail" in str(test_result).lower()):
            logging.error(f"Self-test failed for {plugin_path.name}: {test_result}")
            publish_event("plugin_failed", {
                "plugin": plugin_path.name,
                "stage": "self_test",
                "result": str(test_result),
                "timestamp": datetime.datetime.now().timestamp(),
            })
            utils.notify_human(f"Self-test failed for {plugin_path.name}")
            continue
        else:
            logging.info(f"Self-test passed for {plugin_path.name}: {test_result}")

        # Register
        registered = register_plugin(mod, plugin_path)

        # Lifecycle: on_register()
        if hasattr(mod, "on_register"):
            try:
                mod.on_register()
            except Exception as e:
                logging.error(f"on_register failed for {plugin_path.name}: {e}")
                utils.notify_human(f"on_register failed for {plugin_path.name}: {e}")

        publish_event("plugin_loaded", {
            "plugin": plugin_path.name,
            "metadata": meta,
            "registered": registered,
            "self_test_result": str(test_result),
            "timestamp": datetime.datetime.now().timestamp(),
        })

        print(f"[OK] Plugin {plugin_path.name} loaded and registered. Metadata: {meta}")

    print("Plugin scan complete.")

if __name__ == "__main__":
    main()
