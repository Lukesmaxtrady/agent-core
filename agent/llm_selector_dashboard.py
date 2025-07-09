import os
import sys
import time
import json
from termcolor import cprint, colored

from agent.llm_router import LLM_CONFIG, DEFAULT_LLM_USE_CASE, llm_infer
from agent.event_bus import publish_event

SELECTION_FILE = "llm_selection.json"
STATS_FILE = "llm_stats.json"
LOCK_FILE = "llm_selector.lock"
APP_LIST = [d for d in os.listdir("apps") if os.path.isdir(os.path.join("apps", d))]

# ----- Helper Functions -----

def load_selection():
    if os.path.exists(SELECTION_FILE):
        with open(SELECTION_FILE, "r") as f:
            return json.load(f)
    return {"global": dict(DEFAULT_LLM_USE_CASE), "per_app": {}, "ensemble_enabled": False}

def save_selection(sel):
    with open(SELECTION_FILE, "w") as f:
        json.dump(sel, f, indent=2)

def load_stats():
    if os.path.exists(STATS_FILE):
        with open(STATS_FILE, "r") as f:
            return json.load(f)
    return {}

def save_stats(stats):
    with open(STATS_FILE, "w") as f:
        json.dump(stats, f, indent=2)

def record_stat(model, result, latency_ms):
    stats = load_stats()
    if model not in stats:
        stats[model] = {"success": 0, "fail": 0, "latency": [], "last_check": ""}
    if result == "success":
        stats[model]["success"] += 1
    else:
        stats[model]["fail"] += 1
    stats[model]["latency"].append(latency_ms)
    stats[model]["latency"] = stats[model]["latency"][-10:]
    stats[model]["last_check"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    save_stats(stats)

def is_locked():
    return os.path.exists(LOCK_FILE)

def lock_settings():
    with open(LOCK_FILE, "w") as f:
        f.write(str(time.time()))

def unlock_settings():
    if os.path.exists(LOCK_FILE):
        os.remove(LOCK_FILE)

def check_llm_health(model_name):
    try:
        import requests
        conf = LLM_CONFIG[model_name]
        t0 = time.time()
        provider = conf.get("provider") or conf.get("type", "unknown")
        if provider == "openai":
            import openai
            client = openai.OpenAI(api_key=conf["api_key"])
            client.models.list()
            latency = int((time.time() - t0) * 1000)
            record_stat(model_name, "success", latency)
            return colored(f"Online ({latency}ms)", "green")
        elif provider == "openrouter":
            url = "https://openrouter.ai/api/v1/models"
            headers = {"Authorization": f"Bearer {conf['api_key']}"}
            resp = requests.get(url, headers=headers, timeout=10)
            latency = int((time.time() - t0) * 1000)
            if resp.status_code == 200:
                record_stat(model_name, "success", latency)
                return colored(f"Online ({latency}ms)", "green")
            else:
                record_stat(model_name, "fail", latency)
                return colored("Offline", "red")
        elif provider == "anthropic":
            url = "https://api.anthropic.com/v1/models"
            headers = {"x-api-key": conf["api_key"], "anthropic-version": "2023-06-01"}
            resp = requests.get(url, headers=headers, timeout=10)
            latency = int((time.time() - t0) * 1000)
            if resp.status_code == 200:
                record_stat(model_name, "success", latency)
                return colored(f"Online ({latency}ms)", "green")
            else:
                record_stat(model_name, "fail", latency)
                return colored("Offline", "red")
        return colored("Unchecked", "yellow")
    except Exception:
        record_stat(model_name, "fail", 0)
        return colored("Offline", "red")

def get_stat_label(model):
    stats = load_stats().get(model, {})
    s = stats.get("success", 0)
    f = stats.get("fail", 0)
    latency = stats.get("latency", [])
    avg_lat = int(sum(latency)/len(latency)) if latency else "-"
    last = stats.get("last_check", "Never")
    return f"Success: {s} | Fail: {f} | Avg Latency: {avg_lat}ms | Last Checked: {last}"

def notify(msg, event_type="llm_selector_update", data=None):
    publish_event(event_type, data or {"msg": msg})

def print_header(title):
    cprint("\n" + "="*60, "cyan")
    cprint(title.center(60), "cyan", attrs=["bold"])
    cprint("="*60 + "\n", "cyan")

def pause():
    input(colored("Press Enter to continue...", "magenta"))

def choose_from_list(items, prompt):
    for i, item in enumerate(items):
        print(f"{colored(str(i+1), 'yellow')}. {item}")
    while True:
        choice = input(colored(prompt, "cyan"))
        try:
            idx = int(choice) - 1
            if 0 <= idx < len(items):
                return items[idx]
            else:
                cprint("Invalid selection. Try again.", "red")
        except ValueError:
            cprint("Please enter a number from the list.", "red")

def confirm(prompt):
    return input(colored(prompt + " (y/n): ", "cyan")).strip().lower().startswith("y")

def onboarding():
    print_header("Welcome to the SuperAgent LLM Selector CLI")
    cprint("This dashboard lets you choose, manage, and monitor all your AI models (LLMs) for every app and use-case.", "yellow")
    cprint("Everything is menu-driven, color-coded, and beginner-friendly.", "green")
    cprint("No technical experience needed! If you get stuck, type 'help' at any menu.", "magenta")
    pause()

def help_screen():
    print_header("HELP & QUICK GUIDE")
    cprint("What can I do here?", "cyan")
    print("- Set global and per-app AI models (LLMs) for every type of task.")
    print("- See which models are online/offline and their speed.")
    print("- Track model usage, failures, and average response time.")
    print("- Enable ensemble (voting/consensus) across models for maximum reliability.")
    print("- Test any model with a question or prompt and see its answer instantly.")
    print("- Admins can lock or unlock settings to prevent mistakes.")
    cprint("\nQuick Tips:", "yellow")
    print("- Menus are color-coded for clarity.")
    print("- If unsure, pick the recommended/default model.")
    print("- You can always save your settings to apply them for all agents.")
    print("- 'Exit' returns you to the main dashboard or closes the selector.")
    pause()

# ----- Main Dashboard -----

def main():
    onboarding()
    sel = load_selection()
    while True:
        print_header("SuperAgent LLM Selector - Terminal Dashboard")
        cprint("What would you like to do?", "yellow")
        options = [
            "View LLM settings (global and per-app)",
            "Set global LLM for a use-case",
            "Edit per-app LLM overrides",
            "View/check LLM health & status",
            "Show LLM stats and usage",
            "Configure ensemble (multi-model) settings",
            "Test a model (try a prompt)",
            "Lock or unlock settings (admin)",
            "Save LLM configuration",
            "Help & usage guide",
            "Exit"
        ]
        for i, opt in enumerate(options):
            print(f"{colored(str(i+1), 'yellow')}. {opt}")
        choice = input(colored("\nEnter your choice: ", "cyan")).strip()

        if choice == "1":
            print_header("LLM Settings")
            cprint("Global LLM by use-case:", "magenta")
            for use_case in DEFAULT_LLM_USE_CASE:
                model = sel["global"].get(use_case, DEFAULT_LLM_USE_CASE[use_case])
                print(f"  {colored(use_case, 'cyan')}: {colored(model, 'green')}")
            cprint("\nPer-app overrides:", "magenta")
            for app, overrides in sel.get("per_app", {}).items():
                print(colored(f"\nApp: {app}", "yellow"))
                for use_case, model in overrides.items():
                    print(f"  {use_case}: {colored(model, 'green')}")
            pause()

        elif choice == "2":
            print_header("Set Global LLM For Use-Case")
            use_case = choose_from_list(list(DEFAULT_LLM_USE_CASE.keys()), "Select use-case: ")
            model = choose_from_list(list(LLM_CONFIG.keys()), f"Choose LLM model for '{use_case}': ")
            sel["global"][use_case] = model
            cprint(f"Set {use_case} to {model}!", "green")
            notify(f"Set global {use_case} to {model}")

        elif choice == "3":
            print_header("Per-App LLM Overrides")
            app = choose_from_list(APP_LIST, "Select an app to configure: ")
            if "per_app" not in sel:
                sel["per_app"] = {}
            if app not in sel["per_app"]:
                sel["per_app"][app] = {}
            for use_case in DEFAULT_LLM_USE_CASE:
                print(f"\nOverride for {colored(use_case, 'cyan')}:")
                model = choose_from_list(list(LLM_CONFIG.keys()), f"Select LLM model for '{use_case}' in app '{app}': ")
                sel["per_app"][app][use_case] = model
                cprint(f"  {use_case} set to {model} for {app}", "green")
            notify(f"Updated per-app LLM settings for {app}")

        elif choice == "4":
            print_header("LLM Health & Status")
            for model in LLM_CONFIG:
                status = check_llm_health(model)
                print(f"{colored(model, 'cyan')}: {status}")
            pause()

        elif choice == "5":
            print_header("LLM Model Stats")
            stats = load_stats()
            for model, stat in stats.items():
                print(f"{colored(model, 'cyan')}: {get_stat_label(model)}")
            pause()

        elif choice == "6":
            print_header("Ensemble / Voting (Advanced)")
            val = sel.get("ensemble_enabled", False)
            new_val = confirm(f"Ensemble voting is currently {'ENABLED' if val else 'DISABLED'}. Toggle?")
            sel["ensemble_enabled"] = not val if new_val else val
            if sel["ensemble_enabled"]:
                models = []
                available_models = list(LLM_CONFIG.keys())
                print("Choose models for ensemble (multi-select, comma separated):")
                for i, m in enumerate(available_models):
                    print(f"{i+1}. {m}")
                chosen = input("Enter numbers (e.g. 1,3): ").replace(" ", "")
                try:
                    idxs = [int(x)-1 for x in chosen.split(",") if x]
                    models = [available_models[i] for i in idxs if 0 <= i < len(available_models)]
                except Exception:
                    cprint("Invalid selection, using default models.", "yellow")
                    models = list(DEFAULT_LLM_USE_CASE.values())
                sel["ensemble_models"] = models
                print("\nConsensus strategy:")
                strategies = ["majority_vote", "first_model", "merge_all"]
                strategy = choose_from_list(strategies, "Choose voting strategy: ")
                sel["ensemble_strategy"] = strategy
                cprint(f"Ensemble enabled with models {models} and strategy {strategy}.", "green")
                notify("Ensemble voting updated.")
            else:
                cprint("Ensemble is now disabled.", "yellow")
                notify("Ensemble voting disabled.")

        elif choice == "7":
            print_header("Test a Model")
            prompt = input(colored("Enter a prompt/question for the model: ", "cyan"))
            model = choose_from_list(list(LLM_CONFIG.keys()), "Choose a model to test: ")
            cprint(f"\nSending to {model}... please wait.", "yellow")
            try:
                output = llm_infer(prompt, model_name=model)
                cprint("\nModel Output:\n" + output, "green")
                record_stat(model, "success", 1)
                notify(f"Test prompt run on {model}")
            except Exception as e:
                cprint(f"Error: {e}", "red")
                record_stat(model, "fail", 0)
                notify(f"LLM {model} test prompt failed: {e}", event_type="llm_test_fail")
            pause()

        elif choice == "8":
            print_header("Admin: Lock/Unlock Settings")
            if is_locked():
                cprint("Settings are currently LOCKED.", "red")
                if confirm("Unlock settings? (Admin only)"):
                    unlock_settings()
                    cprint("Settings unlocked!", "green")
                    notify("LLM selector unlocked.")
            else:
                cprint("Settings are currently UNLOCKED.", "green")
                if confirm("Lock settings?"):
                    lock_settings()
                    cprint("Settings locked!", "yellow")
                    notify("LLM selector locked.")

        elif choice == "9":
            print_header("Save LLM Configuration")
            if is_locked():
                cprint("Settings are locked! Please unlock before saving changes.", "red")
            else:
                save_selection(sel)
                cprint("LLM settings saved successfully! Your agents will use these settings.", "green")
                notify("LLM selector config updated.")
            pause()

        elif choice == "10":
            help_screen()

        elif choice == "11" or choice.lower() in ("exit", "q"):
            cprint("\nExiting LLM Selector Dashboard. Goodbye!", "cyan")
            break

        else:
            cprint("Invalid choice. Please enter a number from the menu.", "red")

if __name__ == "__main__":
    main()
