# llm_selector_utils.py

import os
import json
import time
from termcolor import cprint, colored

# ---- General Utilities ----

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
            cprint("Please enter a number.", "red")

def confirm(prompt):
    return input(colored(prompt + " (y/n): ", "cyan")).strip().lower().startswith("y")

def print_header(title):
    cprint("\n" + "="*60, "cyan", attrs=["bold"])
    cprint(title.center(60), "cyan", attrs=["bold"])
    cprint("="*60 + "\n", "cyan")

# ---- File IO ----

def save_selection(sel, file="llm_selection.json"):
    with open(file, "w") as f:
        json.dump(sel, f, indent=2)

def load_selection(file="llm_selection.json"):
    if os.path.exists(file):
        with open(file, "r") as f:
            return json.load(f)
    # Default structure (for most tiers)
    return {"global": {}, "per_app": {}, "ensemble_enabled": False}

# ---- Health Check and Ensemble (Simulated) ----

def health_check(model_key, LLM_CONFIG=None):
    # Can be extended with real API checks!
    if LLM_CONFIG and model_key in LLM_CONFIG:
        try:
            return LLM_CONFIG[model_key]["health_check"]()
        except Exception:
            return False
    return True

def run_ensemble(models, prompt, voting="majority_vote", LLM_CONFIG=None):
    outputs = {}
    for model in models:
        online = health_check(model, LLM_CONFIG)
        outputs[model] = (
            f"[Simulated output from {LLM_CONFIG[model]['display']}]" if LLM_CONFIG else f"[Simulated output from {model}]"
        ) if online else colored("[OFFLINE]", "red")
    # Voting: for now, pick first online as winner
    winner = None
    if voting == "majority_vote":
        for m in models:
            if health_check(m, LLM_CONFIG):
                winner = m
                break
    return outputs, winner

# ---- App List Helper ----

def get_app_list(app_dir="apps"):
    if not os.path.exists(app_dir):
        return []
    return [d for d in os.listdir(app_dir) if os.path.isdir(os.path.join(app_dir, d))]

