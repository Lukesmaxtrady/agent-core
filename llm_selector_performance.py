# llm_selector_performance.py

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
    from llm_config import LLM_CONFIG, PERFORMANCE_LLM_USE_CASE, TIERS, APP_LIST, ENSEMBLE_MODES
except ImportError:
    # Minimal fallback versions
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

# --------- Model/Tier Setup -----------
ASCII_ARCH = """
  ┌──────────────────────┐
  │ Claude 3 Haiku (80%) │◄────┐
  └─────────┬────────────┘     │
            │                  │
            ▼                  │
    ┌───────────────────────┐  │
    │ GPT-4.1 (Critical/QA) │  │
    └─────────┬─────────────┘  │
              │                │
              ▼                │
      ┌──────────────────┐     │
      │  Mistral/DeepSeek│◄────┘ (Fallback/Bulk)
      └──────────────────┘

 Orchestrated by: LangChain/LangGraph
 Memory/Logs: MongoDB (or SQLite for dev)
 API Layer: FastAPI
"""
TIPS = """
Goldilocks (Best-Overall) Stack:
- Most tasks run on Claude Haiku (cheap/fast)
- Heavy/critical tasks: GPT-4.1
- Bulk/fallback: Mistral/DeepSeek
- All API keys auto-detected—only show available!
- Change model priority/order in menu.

Integration:
- LangChain/LangGraph handles agent routing, memory, tools.
- Use FastAPI as API glue for endpoints and jobs.
- Easy to extend with more models/tools.
"""

if 'LLM_CONFIG' not in locals():
    LLM_CONFIG = {
        "claude_haiku": {
            "display": "Claude 3 Haiku",
            "type": "anthropic",
            "api_key": os.environ.get("ANTHROPIC_API_KEY"),
            "group": "PERFORMANCE",
            "health_check": lambda: bool(os.environ.get("ANTHROPIC_API_KEY"))
        },
        "gpt-4.1": {
            "display": "GPT-4.1 (OpenAI/OpenRouter)",
            "type": "openai",
            "api_key": os.environ.get("OPENAI_API_KEY"),
            "group": "PERFORMANCE",
            "health_check": lambda: bool(os.environ.get("OPENAI_API_KEY"))
        },
        "mistral_7b": {
            "display": "Mistral 7B (Open Source)",
            "type": "mistral",
            "api_key": os.environ.get("MISTRAL_API_KEY"),
            "group": "PERFORMANCE",
            "health_check": lambda: bool(os.environ.get("MISTRAL_API_KEY"))
        },
        "deepseek_coder": {
            "display": "DeepSeekCoder (Open Source)",
            "type": "deepseek",
            "api_key": None,
            "group": "PERFORMANCE",
            "health_check": lambda: True
        }
    }
    PERFORMANCE_LLM_USE_CASE = {
        "code": "claude_haiku",
        "chat": "claude_haiku",
        "agent": "gpt-4.1",
        "app": "claude_haiku",
        "bot": "deepseek_coder",
        "verify": "gpt-4.1"
    }
    TIERS = {"PERFORMANCE": list(PERFORMANCE_LLM_USE_CASE.values())}
    ENSEMBLE_MODES = {
        "default": ["claude_haiku", "deepseek_coder"],
        "pro": ["claude_haiku", "deepseek_coder", "gpt-4.1"]
    }
    APP_LIST = ["sample_app"]

def show_diagram_and_tips():
    cprint(ASCII_ARCH, "cyan")
    cprint(TIPS, "yellow")

def main():
    sel = load_selection()
    print_header("Best Overall Performance LLM Selector")
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
            "Change model priority/order",
            "Save config and exit",
            "Exit without saving"
        ]
        for i, opt in enumerate(options, 1):
            print(f"{colored(str(i), 'yellow')}. {opt}")
        choice = input(colored("\nEnter your choice: ", "cyan")).strip()

        if choice == "1":
            print_header("LLM Settings")
            print(colored("Global LLM by use-case:", "magenta"))
            for use_case in PERFORMANCE_LLM_USE_CASE:
                model = sel["global"].get(use_case, PERFORMANCE_LLM_USE_CASE[use_case])
                print(f"  {colored(use_case, 'cyan')}: {colored(LLM_CONFIG[model]['display'], 'green')}")
            print(colored("\nPer-app overrides:", "magenta"))
            for app, overrides in sel.get("per_app", {}).items():
                print(colored(f"\nApp: {app}", "yellow"))
                for use_case, model in overrides.items():
                    print(f"  {use_case}: {colored(LLM_CONFIG[model]['display'], 'green')}")
            pause()
        elif choice == "2":
            print_header("Set Global LLM For Use-Case")
            use_case = choose_from_list(list(PERFORMANCE_LLM_USE_CASE.keys()), "Select use-case: ")
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
            for use_case in PERFORMANCE_LLM_USE_CASE:
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
            print_header("Change Priority/Order of Models")
            current_order = list(LLM_CONFIG)
            for i, k in enumerate(current_order):
                cprint(f"  {i+1}. {LLM_CONFIG[k]['display']}", "cyan")
            new_order = input(colored("Enter new order by numbers (comma, e.g. 2,1,4,3): ", "cyan")).split(",")
            try:
                idxs = [int(i.strip())-1 for i in new_order]
                LLMS = list(LLM_CONFIG)
                if len(idxs) == len(LLMS):
                    # re-ordered (simulate)
                    LLMS = [LLMS[i] for i in idxs]
                    cprint("Order changed (simulated, not persisted).", "green")
                else:
                    cprint("Invalid order; unchanged.", "red")
            except Exception:
                cprint("Parse error; unchanged.", "red")
            pause()
        elif choice == "10":
            save_selection(sel)
            cprint("LLM settings saved. Goodbye!", "green")
            break
        elif choice == "11":
            cprint("Exiting without saving changes.", "yellow")
            break
        else:
            cprint("Invalid choice. Please enter a number from the menu.", "red")

if __name__ == "__main__":
    main()
