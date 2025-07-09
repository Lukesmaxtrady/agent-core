import os
import sys
import json
import time
from termcolor import cprint, colored

# ==== MODEL CONFIGURATION: Free-Only ====
LLM_CONFIG = {
    "deepseek_coder": {
        "type": "local",
        "display": "DeepSeek Coder (Ollama)",
        "api_key": None,
        "env_var": None,
    },
    "codewhisperer": {
        "type": "aws",
        "display": "AWS CodeWhisperer (Free API)",
        "api_key": os.environ.get("CODEWHISPERER_API_KEY"),
        "env_var": "CODEWHISPERER_API_KEY",
    },
    "flowiseai": {
        "type": "api",
        "display": "FlowiseAI (Free API)",
        "api_key": os.environ.get("FLOWISEAI_API_KEY"),
        "env_var": "FLOWISEAI_API_KEY",
    },
    # Add more if you want, but keep this 100% free-tier
}

TIERS = {
    "FREE": list(LLM_CONFIG.keys()),
}

DEFAULT_USE_CASE = {
    "code": "deepseek_coder",
    "chat": "codewhisperer",
    "agent": "flowiseai"
}

SELECTION_FILE = "llm_selection_free.json"

ASCII_ARCH = r"""
┌───────────────────────┐
│    Free LLM System    │
└─────────┬─────────────┘
          ▼
┌─────────────────────────────────┐
│ DeepSeek Coder | CodeWhisperer  │
│ FlowiseAI (logic prototyping)   │
└─────────────────────────────────┘
      (All local or free APIs)
Orchestrated by: LangGraph / SuperAgent
"""

INTEGRATION_TIPS = """
Tips:
- Use DeepSeek Coder for code generation and review.
- CodeWhisperer is your backup for code and chat (good VS Code plugin).
- FlowiseAI can visually build agent logic chains.
- All tools are free and can run locally or with free-tier cloud APIs.
- If an API key is missing, you'll see a warning below.
"""

def print_ascii_architecture():
    cprint(ASCII_ARCH, "cyan")
    cprint(INTEGRATION_TIPS, "yellow")

def get_available_models():
    """Return all free models with usable API keys or that are local."""
    avail = []
    for k, conf in LLM_CONFIG.items():
        if conf["type"] == "local":
            avail.append(k)
        elif conf.get("api_key") or not conf.get("env_var"):
            avail.append(k)
    return avail

def print_health_check():
    cprint("\nLLM Health Check:", "magenta")
    for k, conf in LLM_CONFIG.items():
        status = "ONLINE"
        if conf["type"] != "local" and conf.get("env_var") and not conf.get("api_key"):
            status = colored("MISSING KEY", "red")
        color = "green" if status == "ONLINE" else "red"
        cprint(f"- {conf['display']}: {status}", color)

def print_settings(sel):
    cprint("\nCurrent Free Tier LLM Settings:", "cyan")
    for use_case, model in sel["global"].items():
        disp = LLM_CONFIG.get(model, {}).get("display", model)
        print(f"  {colored(use_case, 'yellow')}: {colored(disp, 'green')}")

def save_selection(sel):
    with open(SELECTION_FILE, "w") as f:
        json.dump(sel, f, indent=2)

def load_selection():
    if os.path.exists(SELECTION_FILE):
        with open(SELECTION_FILE, "r") as f:
            return json.load(f)
    return {"global": dict(DEFAULT_USE_CASE)}

def main():
    sel = load_selection()
    while True:
        os.system("cls" if os.name == "nt" else "clear")
        print_ascii_architecture()
        print_health_check()
        print_settings(sel)
        cprint("\nWhat do you want to do?", "yellow")
        menu = [
            "Set global LLM for a use-case",
            "Test a model (prompt any model now)",
            "View LLM architecture & integration tips",
            "Save and Exit"
        ]
        for i, item in enumerate(menu, 1):
            print(f"{colored(str(i), 'cyan')}. {item}")
        choice = input(colored("\nEnter choice: ", "magenta")).strip()
        if choice == "1":
            uc_list = list(DEFAULT_USE_CASE.keys())
            for i, uc in enumerate(uc_list, 1):
                print(f"{i}. {uc}")
            idx = input(colored("Select use-case: ", "yellow")).strip()
            try:
                idx = int(idx) - 1
                if 0 <= idx < len(uc_list):
                    use_case = uc_list[idx]
                else:
                    raise Exception
            except Exception:
                cprint("Invalid use-case.", "red")
                continue
            models = get_available_models()
            for i, m in enumerate(models, 1):
                print(f"{i}. {LLM_CONFIG[m]['display']}")
            midx = input(colored("Select LLM: ", "yellow")).strip()
            try:
                midx = int(midx) - 1
                if 0 <= midx < len(models):
                    model = models[midx]
                else:
                    raise Exception
            except Exception:
                cprint("Invalid model.", "red")
                continue
            sel["global"][use_case] = model
            cprint(f"Set {use_case} to {LLM_CONFIG[model]['display']}!", "green")
            time.sleep(1)

        elif choice == "2":
            prompt = input(colored("Enter your prompt/question: ", "cyan"))
            models = get_available_models()
            for i, m in enumerate(models, 1):
                print(f"{i}. {LLM_CONFIG[m]['display']}")
            midx = input(colored("Select model: ", "yellow")).strip()
            try:
                midx = int(midx) - 1
                if 0 <= midx < len(models):
                    model = models[midx]
                else:
                    raise Exception
            except Exception:
                cprint("Invalid model.", "red")
                continue
            # Simulate response
            cprint(f"\n[Simulated {LLM_CONFIG[model]['display']} output]: '{prompt[::-1]}'", "green")
            input(colored("Press Enter to continue...", "magenta"))

        elif choice == "3":
            print_ascii_architecture()
            input(colored("Press Enter to return to menu...", "magenta"))

        elif choice == "4" or choice.lower() in ("exit", "q"):
            save_selection(sel)
            cprint("LLM Free Tier selection saved. Goodbye!", "cyan")
            break
        else:
            cprint("Invalid input. Please pick a number.", "red")
            time.sleep(1)

if __name__ == "__main__":
    main()
