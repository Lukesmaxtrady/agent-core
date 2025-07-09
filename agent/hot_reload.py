# agent/hot_reload.py

import threading
import time
import os
from pathlib import Path
from agent.plugin_hot_reload_daemon import start_plugin_hot_reload_daemon
from agent.event_bus import publish_event

PLUGIN_DIR = Path("plugins")
STATUS_FILE = Path("logs/hot_reload_status.json")

def main_entry():
    """
    Entry point for Live Agent Hot-Reload from main.py menu.
    Starts hot-reload daemon in the background, guards against double-start,
    publishes events, and gives clear feedback.
    """
    # Guard: prevent multiple daemon instances
    if getattr(main_entry, "_daemon_started", False):
        print("🔄 [HotReload] Daemon is already running.")
        return

    # Check plugin directory exists, give help if not
    if not PLUGIN_DIR.exists():
        print(f"⚠️  [HotReload] Plugin folder '{PLUGIN_DIR}' not found. Creating it for you.")
        PLUGIN_DIR.mkdir(parents=True, exist_ok=True)
        print(f"ℹ️  Drop your plugin .py files into '{PLUGIN_DIR}/' and rerun this menu option.")

    def daemon_runner():
        try:
            print("🔄 [HotReload] Starting plugin hot-reload daemon...")
            publish_event("hot_reload_started", {"timestamp": time.time()})
            start_plugin_hot_reload_daemon()
            publish_event("hot_reload_stopped", {"timestamp": time.time()})
        except Exception as e:
            msg = f"🔥 [HotReload] Daemon crashed: {e}"
            print(msg)
            publish_event("hot_reload_failed", {"error": str(e), "timestamp": time.time()})
            # Optionally: write error to status file
            with open(STATUS_FILE, "w", encoding="utf-8") as f:
                f.write(f'{{"status": "error", "error": "{str(e)}"}}')

    thread = threading.Thread(target=daemon_runner, daemon=True)
    thread.start()
    time.sleep(0.7)  # Let daemon initialize
    print("✅ [HotReload] Daemon started. Watching 'plugins/' for live changes…")
    publish_event("hot_reload_status", {"status": "running", "timestamp": time.time()})
    setattr(main_entry, "_daemon_started", True)
    # Optionally, write a status file for diagnostics
    with open(STATUS_FILE, "w", encoding="utf-8") as f:
        f.write('{"status": "running"}')

if __name__ == "__main__":
    main_entry()
