import os
import sys
import json
import importlib
import subprocess
import time

try:
    from termcolor import cprint, colored
except ImportError:
    def cprint(msg, *a, **k): print(msg)
    def colored(msg, *a, **k): return msg

# --- Config ---
TIERS = [
    ("FREE", "Zero-cost: only open source/local/free APIs."),
    ("VALUE", "Best performance-per-dollar: mixes free & cheap paid APIs."),
    ("PERFORMANCE", "Best overall performance: Claude, GPT-4.1, open-source fallback."),
    ("PREMIUM_ENSEMBLE", "All premium models, voting/ensemble/fallback for max accuracy.")
]

SCRIPT_MAP = {
    "FREE": "llm_selector_free",
    "VALUE": "llm_selector_value",
    "PERFORMANCE": "llm_selector_performance",
    "PREMIUM_ENSEMBLE": "llm_selector_premium",
}

ACTIVE_TIER_FILE = "llm_tier.active"

def load_active_tier():
    if os.path.exists(ACTIVE_TIER_FILE):
        with open(ACTIVE_TIER_FILE, "r") as f:
            return f.read().strip().upper()
    return "FREE"

def save_active_tier(tier):
    with open(ACTIVE_TIER_FILE, "w") as f:
        f.write(tier.upper())

def reload_global_llm_config():
    # Add real reload logic here if needed
    cprint("[LLM config reloaded]", "yellow")

def print_current_tier():
    tier = load_active_tier()
    color = {
        "FREE": "green",
        "VALUE": "cyan",
        "PERFORMANCE": "yellow",
        "PREMIUM_ENSEMBLE": "magenta"
    }.get(tier, "white")
    cprint(f"\n[Active LLM Tier: {tier}]\n", color, attrs=["bold"])

def show_menu():
    os.system("cls" if os.name == "nt" else "clear")
    print_current_tier()
    cprint("="*62, "cyan")
    cprint("🧠  LLM Model Selector — SuperAgent Multi-Tier Launcher  🧠".center(62), "cyan", attrs=["bold"])
    cprint("="*62, "cyan")
    for idx, (key, desc) in enumerate(TIERS, 1):
        color = {"FREE": "green", "VALUE": "cyan", "PERFORMANCE": "yellow", "PREMIUM_ENSEMBLE": "magenta"}[key]
        cprint(f"{idx}. {key:20}  —  {desc}", color)
    print("0. Exit\n")

def run_selector_module(module_name, tier_key):
    try:
        selector = importlib.import_module(module_name)
        if hasattr(selector, "main"):
            selector.main()
            return True
        else:
            cprint(f"Module '{module_name}' missing main().", "red")
            return False
    except Exception as e:
        cprint(f"Module '{module_name}' import failed: {e}", "red")
        return False

def run_selector_script(script_filename):
    # Only fallback if import failed or not available as module
    if not script_filename.endswith(".py"):
        script_filename += ".py"
    if not os.path.exists(script_filename):
        cprint(f"Script '{script_filename}' not found.", "red")
        return
    cprint(f"\n[Launching fallback script: {script_filename}...]\n", "cyan")
    subprocess.call([sys.executable, script_filename])

def main():
    while True:
        show_menu()
        choice = input(colored("Select a tier (number): ", "yellow")).strip()
        if choice in ("0", "exit", "q", "quit"):
            cprint("Exiting LLM Selector.", "cyan")
            break
        try:
            idx = int(choice) - 1
            if 0 <= idx < len(TIERS):
                tier_key = TIERS[idx][0]
                module_name = SCRIPT_MAP[tier_key]
                save_active_tier(tier_key)
                cprint(f"\n[Switching to {tier_key} selector...]\n", "yellow")
                success = run_selector_module(module_name, tier_key)
                if not success:
                    # Try running as script as fallback
                    run_selector_script(module_name + ".py")
                reload_global_llm_config()
                cprint(f"\n[Returned from {tier_key} selector.]", "cyan")
                input(colored("Press Enter to continue...", "magenta"))
            else:
                cprint("Invalid option. Please select a tier by number.", "red")
                time.sleep(1)
        except Exception:
            cprint("Invalid input. Please enter a number.", "red")
            time.sleep(1)

if __name__ == "__main__":
    main()
