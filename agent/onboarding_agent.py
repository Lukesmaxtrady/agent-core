# agent/onboarding_agent.py

import os
import json
import time
from termcolor import cprint, colored

USER_STATE_FILE = "user_state.json"

# ==== User State Utilities ====
def get_user_name():
    try:
        with open(USER_STATE_FILE, "r") as f:
            return json.load(f).get("name", None)
    except Exception:
        return None

def set_user_name(name):
    try:
        with open(USER_STATE_FILE, "w") as f:
            json.dump({"name": name}, f)
    except Exception:
        pass

# ==== Dynamic/Context Onboarding & Pro Mode ====
def onboarding(force=False):
    name = get_user_name()
    if not name or force:
        cprint("\n👋 Welcome! What's your name?", "cyan", attrs=["bold"])
        name = input(colored("Enter your name (or nickname): ", "yellow")).strip()
        if name:
            set_user_name(name)
        else:
            name = "friend"
    cprint(f"\n👋 Hello, {name}! Welcome to the SuperAgent System.", "cyan", attrs=["bold"])
    cprint("This tool helps you build and manage amazing A.I. bots and apps, step by step.", "yellow")
    cprint("\nWhat would you like to do?", "green")
    cprint("  1. Guided Tour (see how everything works, step-by-step)", "yellow")
    cprint("  2. Quick Demo (see an example in action)", "yellow")
    cprint("  3. Skip to Main Menu", "yellow")
    choice = input(colored("Choose 1, 2, or 3: ", "magenta")).strip()
    if choice == "1":
        guided_tour()
    elif choice == "2":
        quick_demo()
    else:
        return

def guided_tour():
    cprint("\n=== Guided Tour ===", "cyan", attrs=["bold"])
    cprint("• This dashboard lets you:\n"
           "  - Create your own bots (apps)\n"
           "  - Pick and test AI brains (LLMs)\n"
           "  - Check if everything is working\n"
           "  - Upgrade and fix your system\n", "yellow")
    cprint("Press Enter to continue through each step, or type 'skip' to go faster.\n", "yellow")
    steps = [
        ("Creating your first app", "Type 'create app' and follow the instructions."),
        ("Choosing an AI model", "Select a 'brain' for your app—don't worry, you can change this later."),
        ("Testing your app", "Run health checks to make sure everything is working."),
        ("Getting help", "Type 'help' at any time to see more instructions or get unstuck."),
        ("Pro Mode", "Advanced users can type 'pro mode' to unlock hidden features and fast shortcuts."),
        ("Multi-Agent Projects", "You can collaborate or assign multiple AI agents to any project!"),
        ("Auto-Deploy", "Your projects can be deployed to the cloud, Docker, K8s, or Replit with a menu click."),
    ]
    for i, (title, desc) in enumerate(steps, 1):
        cprint(f"\nStep {i}: {title}", "green", attrs=["bold"])
        cprint(desc, "yellow")
        cont = input("Press Enter to continue or type 'skip' to finish tour: ")
        if cont.strip().lower() == "skip":
            break
    cprint("\nThat’s it for the guided tour! You’re ready to go. Type 'menu' to start using the dashboard.", "cyan")

def quick_demo():
    cprint("\n=== Quick Demo ===", "cyan", attrs=["bold"])
    cprint("Let’s watch the system create an app, pick an AI model, and run a test.", "yellow")
    time.sleep(1.2)
    cprint("• Creating a new app: 'MyFirstBot' ...", "green")
    time.sleep(0.8)
    cprint("• Selecting the default AI brain: 'gpt-4o' ...", "green")
    time.sleep(0.8)
    cprint("• Running a quick test... Success! Your bot is ready.", "green")
    cprint("\nYou can do all this and more from the main menu. Type 'menu' to get started.", "cyan")

def show_help(context="main"):
    if context == "main":
        cprint("\n=== HELP MENU ===", "cyan", attrs=["bold"])
        cprint("You can type any of the following at any prompt:", "yellow")
        cprint("- 'help' : See this help screen.", "green")
        cprint("- 'menu' : Return to the main dashboard.", "green")
        cprint("- 'create app' : Start a new app or bot.", "green")
        cprint("- 'test app' : Check if your app is working.", "green")
        cprint("- 'set model' : Change the AI brain for your app.", "green")
        cprint("- 'pro mode' : Toggle advanced/expert features.", "green")
        cprint("- 'deploy' : Instantly deploy your project to cloud/Docker/K8s.", "green")
        cprint("- 'exit' : Quit the program safely.", "green")
        cprint("\nNeed more detailed help or stuck? Visit our docs or contact support!", "yellow")
    elif context == "project":
        cprint("\n=== PROJECT HELP ===", "cyan", attrs=["bold"])
        cprint("You are inside the project creation wizard.", "yellow")
        cprint("- Answer each prompt clearly. If unsure, press Enter for the default.", "green")
        cprint("- Type 'skip' at any step to jump ahead.", "green")
        cprint("- After finishing, you can add features, test, or deploy anytime.", "green")
        cprint("- Type 'help' for live hints or troubleshooting.", "green")
    # Add more context help sections as you expand features!

def smart_coach(message=""):
    cprint("\n[SMART COACH]", "magenta", attrs=["bold"])
    cprint(message or "It looks like you might need help. Would you like a tip or walkthrough? Type 'help' anytime!", "yellow")

def error_handler():
    cprint("Oops! Something went wrong or wasn’t recognized. Here’s what you can do:", "red")
    show_help("main")
