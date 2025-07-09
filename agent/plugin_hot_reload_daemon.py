# agent/plugin_hot_reload_daemon.py

import importlib
import sys
import time
import threading
import traceback
from pathlib import Path

from agent.event_bus import publish_event
from agent import utils  # new import

PLUGINS_DIR = Path("plugins")
PLUGINS_DIR.mkdir(exist_ok=True)
POLL_INTERVAL = 2.0

class PluginHotReloader:
    def __init__(self, plugins_dir=PLUGINS_DIR, poll_interval=POLL_INTERVAL):
        self.plugins_dir = Path(plugins_dir)
        self.poll_interval = poll_interval
        self.loaded_plugins = {}  # name: (mod, last_mod_time)
        self.failed_plugins = set()
        self.failure_counts = {}

    def scan_plugins(self):
        plugin_files = {f for f in self.plugins_dir.glob("*.py") if not f.name.startswith("__")}
        current_names = {f.stem for f in plugin_files}
        loaded_names = set(self.loaded_plugins.keys())
        # Detect removed plugins
        removed = loaded_names - current_names
        for name in removed:
            self.unload_plugin(name)
        # Detect new/modified plugins
        for f in plugin_files:
            mod_time = f.stat().st_mtime
            if (f.stem not in self.loaded_plugins) or (self.loaded_plugins[f.stem][1] < mod_time):
                self.load_or_reload_plugin(f, mod_time)

    def load_or_reload_plugin(self, file: Path, mod_time: float):
        name = file.stem
        try:
            if name in sys.modules:
                importlib.reload(sys.modules[name])
                mod = sys.modules[name]
                event_type = "plugin_reloaded"
            else:
                spec = importlib.util.spec_from_file_location(name, file)
                mod = importlib.util.module_from_spec(spec)
                sys.modules[name] = mod
                spec.loader.exec_module(mod)
                event_type = "plugin_loaded"

            self.loaded_plugins[name] = (mod, mod_time)
            self.failed_plugins.discard(name)
            self.failure_counts[name] = 0
            publish_event(event_type, {"plugin": name, "file": str(file)})
            utils.notify_human(f"[PLUGIN] {event_type.upper()}: {name}")

            # Run optional self_test/healthcheck
            if hasattr(mod, "self_test"):
                try:
                    result = mod.self_test()
                    if not result:
                        raise Exception("Self-test failed.")
                except Exception as e:
                    utils.notify_human(f"[PLUGIN] {name} self-test failed: {e}")
                    self.failure_counts[name] = self.failure_counts.get(name, 0) + 1
                    if self.failure_counts[name] >= 3:
                        self.failed_plugins.add(name)
                        self.unload_plugin(name, failure=True)
                        publish_event("plugin_static_analysis_failed", {"plugin": name, "error": str(e)})
                    return
        except Exception as e:
            utils.notify_human(f"[PLUGIN] FAILED to load/reload {name}: {e}")
            traceback.print_exc()
            self.failed_plugins.add(name)
            self.failure_counts[name] = self.failure_counts.get(name, 0) + 1
            publish_event("plugin_failed", {"plugin": name, "error": str(e)})

    def unload_plugin(self, name: str, failure=False):
        if name in sys.modules:
            del sys.modules[name]
        if name in self.loaded_plugins:
            del self.loaded_plugins[name]
        event_type = "plugin_unloaded" if not failure else "plugin_failed"
        publish_event(event_type, {"plugin": name})
        utils.notify_human(f"[PLUGIN] UNLOADED: {name}")

    def run(self):
        utils.notify_human("[HotReloadDaemon] Monitoring plugins for changes...")
        while True:
            self.scan_plugins()
            time.sleep(self.poll_interval)

def start_plugin_hot_reload_daemon():
    reloader = PluginHotReloader()
    t = threading.Thread(target=reloader.run, daemon=True)
    t.start()
    return t

if __name__ == "__main__":
    start_plugin_hot_reload_daemon()
    while True:
        time.sleep(10)
