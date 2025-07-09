# llm_selector_value.py
import os
import sys
import json
import time
from termcolor import cprint, colored

try:
    from llm_selector_utils import (
        pause, choose_from_list, confirm, print_header, 
        health_check, run_ensemble, save_selection, load_selection
    )
    from llm_config import LLM_CONFIG, TIERS, VALUE_LLM_USE_CASE, APP_LIST, ENSEMBLE_MODES
except ImportError:
    # Fallback minimal versions (customize as needed if not using utils/config module)
    def pause(): input(colored("Press Enter to continue...", "magenta"))
    def choose_from_list(items, prompt): 
        for i, item in enumerate(items):
            print(f"{colored(str(i+1), 'yellow')}. {item}")
        while True:
            choice = input(colored(prompt, "cyan"))
            try:
                idx = int(choice) - 1
                if 0 <= idx < len(items):
                    return items[idx]
                cprint("Invalid selection. Try again.", "red")
            except ValueError:
                cprint("Please enter a number.", "red")
    def confirm(prompt):
        return input(colored(prompt + " (y/n): ", "cyan")).strip().lower().startswith("y")
    def print_header(title):
        cprint("\n" + "="*60, "cyan")
        cprint(title.center(60), "cyan", attrs=["bold"])
        cprint("="*60 + "\n", "cyan")
    def health_check(model_key): return True
    def run_ensemble(models, prompt, voting="majority_vote"):
        outputs = {m: f"[Simulated output from {m}]" for m in models}
        winner = models[0] if models else None
        return outputs, winner
    SELECTION_FILE = "llm_selection.json"
    def save_selection(sel):
        with open(SELECTION_FILE, "w") as f: json.dump(sel, f, indent=2)
    def load_selection():
        if os.path.exists(SELECTION_FILE):
            with open(SELECTION_FILE, "r") as f: return json.load(f)
        return {"global": {}, "per_app": {}, "ensemble_enabled": False}

# ---------------- Model/Tier Setup ---------------

ASCII_ARCH = """
 ┌──────────────┐
 │  Dify Front  │◄────────┐
 └────┬─────────┘         │
      ▼                  │
 ┌─────────────┐    ┌────┴─────┐
 │  Flowise AI │    │ Replit   │
 └─────────────┘    └────┬─────┘
      ▼                 ▼
 ┌─────────────────────────────┐
 │ Claude Haiku / GPT-4.1      │
 │ DeepSeekCoder (OpenRouter)  │
 └─────────────────────────────┘
        ▲                   ▲
 ┌──────┴───────┐   ┌───────┴─────┐
 │ LangChain    │   │ SuperAgent  │
 │ CrewAI/Ollama│   │   (agents)  │
 └──────────────┘   └─────────────┘
"""
TIPS = """
Best Value Stack:
- Claude Haiku: Coding/Chat (affordable)
- GPT-4.1: Verification (OpenRouter)
- Flowise: Logic/app flows
- SuperAgent: Agent orchestration
- DeepSeekCoder: Local/dev code
- CrewAI: Offline/dev fallback

Integration:
- Use Dify as UI, Flowise for agent logic.
- Route code tasks to Claude Haiku (OpenRouter), fallback to DeepSeek.
- Always keep API keys in env vars.
"""

# These would be imported from llm_config.py ideally:
if 'LLM_CONFIG' not in locals():
    LLM_CONFIG = {
        "claude-haiku": {
            "display": "Claude 3 Haiku",
            "type": "anthropic",
            "api_key": os.environ.get("ANTHROPIC_API_KEY"),
            "group": "VALUE",
            "health_check": lambda: bool(os.environ.get("ANTHROPIC_API_KEY"))
        },
        "gpt-4.1": {
            "display": "GPT-4.1 (OpenAI/OpenRouter)",
            "type": "openai",
            "api_key": os.environ.get("OPENAI_API_KEY"),
            "group": "VALUE",
            "health_check": lambda: bool(os.environ.get("OPENAI_API_KEY"))
        },
        "deepseek-coder": {
            "display": "DeepSeek Coder (Ollama)",
            "type": "local",
            "api_key": None,
            "group": "VALUE",
            "health_check": lambda: True
        },
        "flowiseai": {
            "display": "FlowiseAI",
            "type": "api",
            "api_key": os.environ.get("FLOWISEAI_API_KEY"),
            "group": "VALUE",
            "health_check": lambda: True
        }
    }
    VALUE_LLM_USE_CASE = {
        "code": "claude-haiku",
        "chat": "claude-haiku",
        "agent": "flowiseai",
        "app": "flowiseai",
        "bot": "deepseek-coder",
        "verify": "gpt-4.1"
    }
    TIERS = {"VALUE": list(VALUE_LLM_USE_CASE.values())}
    ENSEMBLE_MODES = {
        "default": ["claude-haiku", "deepseek-coder"],
        "pro": ["claude-haiku", "deepseek-coder", "gpt-4.1"]
    }
    APP_LIST = ["sample_app"] # Put real app list here

# --------- CLI Main ---------

def show_diagram_and_tips():
    cprint(ASCII_ARCH, "cyan")
    cprint(TIPS, "yellow")

def main():
    sel = load_selection()
    print_header("Best Value LLM Selector (Performance vs Cost)")
    show_diagram_and_tips()
    while True:
        print(colored("\nMenu:", "cyan"))
        options = [
            "View current LLM settings",
            "Set global LLM for a use-case",
            "Edit per-app LLM overrides",
            "View/check LLM health & status",
            "Configure ensemble/voting (multi-model)",
            "Test a model",
            "Run ensemble/voting mode",
            "Show stack architecture/tips",
            "Save config and exit",
            "Exit without saving"
        ]
        for i, opt in enumerate(options, 1):
            print(f"{colored(str(i), 'yellow')}. {opt}")
        choice = input(colored("\nEnter your choice: ", "cyan")).strip()

        if choice == "1":
            print_header("LLM Settings")
            print(colored("Global LLM by use-case:", "magenta"))
            for use_case in VALUE_LLM_USE_CASE:
                model = sel["global"].get(use_case, VALUE_LLM_USE_CASE[use_case])
                print(f"  {colored(use_case, 'cyan')}: {colored(LLM_CONFIG[model]['display'], 'green')}")
            print(colored("\nPer-app overrides:", "magenta"))
            for app, overrides in sel.get("per_app", {}).items():
                print(colored(f"\nApp: {app}", "yellow"))
                for use_case, model in overrides.items():
                    print(f"  {use_case}: {colored(LLM_CONFIG[model]['display'], 'green')}")
            pause()
        elif choice == "2":
            print_header("Set Global LLM For Use-Case")
            use_case = choose_from_list(list(VALUE_LLM_USE_CASE.keys()), "Select use-case: ")
            models = list(LLM_CONFIG)
            model = choose_from_list([LLM_CONFIG[k]['display'] for k in models], f"Choose LLM model for '{use_case}': ")
            sel["global"][use_case] = models[[LLM_CONFIG[k]['display'] for k in models].index(model)]
            cprint(f"Set {use_case} to {model}!", "green")
        elif choice == "3":
            print_header("Per-App LLM Overrides")
            app = choose_from_list(APP_LIST, "Select an app to configure: ")
            if "per_app" not in sel:
                sel["per_app"] = {}
            if app not in sel["per_app"]:
                sel["per_app"][app] = {}
            for use_case in VALUE_LLM_USE_CASE:
                print(f"\nOverride for {colored(use_case, 'cyan')}:")
                models = list(LLM_CONFIG)
                model = choose_from_list([LLM_CONFIG[k]['display'] for k in models], f"Select LLM model for '{use_case}' in app '{app}': ")
                sel["per_app"][app][use_case] = models[[LLM_CONFIG[k]['display'] for k in models].index(model)]
                cprint(f"  {use_case} set to {model} for {app}", "green")
        elif choice == "4":
            print_header("LLM Health & Status")
            for model in LLM_CONFIG:
                status = health_check(model)
                color = "green" if status else "red"
                print(f"{colored(LLM_CONFIG[model]['display'], color)}: {'ONLINE' if status else 'OFFLINE'}")
            pause()
        elif choice == "5":
            print_header("Configure Ensemble/Voting")
            enabled = sel.get("ensemble_enabled", False)
            sel["ensemble_enabled"] = confirm(f"Ensemble/voting is currently {'ENABLED' if enabled else 'DISABLED'}. Toggle?")
            if sel["ensemble_enabled"]:
                all_models = list(LLM_CONFIG)
                chosen = input(colored(f"Enter numbers for models (comma separated):\n{', '.join([f'{i+1}:{LLM_CONFIG[k]['display']}' for i,k in enumerate(all_models)])}\n> ", "yellow")).replace(" ", "")
                try:
                    idxs = [int(x)-1 for x in chosen.split(",") if x]
                    sel["ensemble_models"] = [all_models[i] for i in idxs if 0 <= i < len(all_models)]
                except Exception:
                    cprint("Invalid selection, using default models.", "yellow")
                    sel["ensemble_models"] = ENSEMBLE_MODES["default"]
                strategies = ["majority_vote", "first_model", "merge_all"]
                sel["ensemble_strategy"] = choose_from_list(strategies, "Choose voting strategy: ")
                cprint(f"Ensemble enabled with models {[LLM_CONFIG[m]['display'] for m in sel['ensemble_models']]} and strategy {sel['ensemble_strategy']}.", "green")
            else:
                cprint("Ensemble is now disabled.", "yellow")
        elif choice == "6":
            print_header("Test a Model")
            prompt = input(colored("Enter a prompt/question for the model: ", "cyan"))
            models = list(LLM_CONFIG)
            model = choose_from_list([LLM_CONFIG[k]['display'] for k in models], "Choose a model to test: ")
            chosen_key = models[[LLM_CONFIG[k]['display'] for k in models].index(model)]
            cprint(f"\nSending to {model}... (simulated)", "yellow")
            if health_check(chosen_key):
                cprint(f"\nModel Output: [Simulated output for '{prompt}' from {model}]", "green")
            else:
                cprint(f"Error: {model} is OFFLINE.", "red")
            pause()
        elif choice == "7":
            print_header("Ensemble/Voting Mode (Advanced)")
            prompt = input(colored("Enter prompt for ensemble: ", "yellow"))
            models = sel.get("ensemble_models", ENSEMBLE_MODES["default"])
            outputs, winner = run_ensemble(models, prompt)
            print("\nResults:")
            for m, o in outputs.items():
                cprint(f"{LLM_CONFIG[m]['display']}: {o}", "cyan" if m != winner else "green")
            print(f"\nWinner (by voting): {LLM_CONFIG[winner]['display'] if winner else 'None'}")
            pause()
        elif choice == "8":
            print_header("Architecture & Tips")
            show_diagram_and_tips()
            pause()
        elif choice == "9":
            save_selection(sel)
            cprint("LLM settings saved. Goodbye!", "green")
            break
        elif choice == "10":
            cprint("Exiting without saving changes.", "yellow")
            break
        else:
            cprint("Invalid choice. Please enter a number from the menu.", "red")

if __name__ == "__main__":
    main()
