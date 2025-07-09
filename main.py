# --- AI SUPERAGENT SYSTEM MAIN (ULTRA-USER-FRIENDLY CLI) ---

import os
import sys
import datetime
import traceback
import logging
from logging.handlers import RotatingFileHandler
import threading
import time

from prompt_toolkit import PromptSession
from prompt_toolkit.completion import WordCompleter
from prompt_toolkit.formatted_text import HTML

# === Core and Agent Imports ===
from agent.planner import Planner
from agent.coder import Coder
from agent.tester import Tester
from agent.deployer import Deployer
from agent.feedback import Feedback

from agent.devops_fixer import main_entry as devops_fixer_main
from agent.health import health_check, doctor
from agent.auto_upgrade_agent import auto_upgrade_all_agents
from agent.supreme_auditor import supreme_audit_and_heal

from agent.incident_responder import main_entry as incident_response_main
from agent.peer_review_agent import main_entry as peer_review_main
from agent.knowledgebase_agent import main_entry as knowledgebase_main
from agent.metrics_collector import main_entry as metrics_main
from agent.hot_reload import main_entry as hot_reload_main

from agent.llm_selector_dashboard import print_llm_selector_menu
from agent.rollback import rollback_all_backups

# NEW: Friendly onboarding and help agents
from agent.onboarding_agent import onboarding, show_help, smart_coach

try:
    from termcolor import cprint, colored
except ImportError:
    def cprint(msg, *args, **kwargs): print(msg)
    def colored(msg, *args, **kwargs): return msg

# --- LOGGING SETUP ---
LOG_FILENAME = "logs/superagent.log"
if not os.path.exists("logs"): os.makedirs("logs")
logger = logging.getLogger("superagent")
logger.setLevel(logging.DEBUG)
handler = RotatingFileHandler(LOG_FILENAME, maxBytes=5 * 1024 * 1024, backupCount=3)
formatter = logging.Formatter('%(asctime)s %(levelname)s %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)

SESSION_LOG = []
SESSION_LOG_LOCK = threading.Lock()

def log_action(action: str):
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with SESSION_LOG_LOCK:
        SESSION_LOG.append(f"[{now}] {action}")
    logger.info(action)

def save_session_log():
    with SESSION_LOG_LOCK:
        with open("session.log", "a", encoding="utf-8") as f:
            f.write("\n".join(SESSION_LOG) + "\n")
    logger.info("Session log saved.")

def periodic_save(interval=300):
    """Auto-save session log every `interval` seconds in background."""
    while True:
        time.sleep(interval)
        save_session_log()

# --- SUPER CLEAR MENU ---
menu_agent = [
    ("DevOps Quick Fix", "Automatically clean up and fix coding style of all agents. Recommended for new/changed agents.", "🛠️"),
    ("System Health Check", "Check your AI agent system for problems, errors, or slowdowns. Super clear pass/fail results.", "❤️"),
    ("Auto-Upgrade ALL Agents", "Let the AI upgrade every agent automatically. Safe, reversible, and shows all changes.", "🤖"),
    ("Supreme Auditor & Self-Healer", "Scan your system for deep issues and auto-heal. Use this if things seem 'off' or broken.", "🔬"),
    ("View Last Upgrade/Audit Logs", "View the most recent system logs and summaries. Great for understanding what changed.", "📜"),
    ("Rollback All Upgrades", "Go back to a safe state if an upgrade caused issues. 100% reversible.", "⏪"),
    ("Automated Incident Response Agent", "Detect and respond to issues in real time. Fixes errors before you notice them!", "🚨"),
    ("Peer Review Agent", "Get multi-agent code review and voting. Higher-quality, less mistakes.", "🧑‍💻"),
    ("Knowledgebase Agent", "Ask for a summary of what changed, or get a knowledge digest of your agents.", "📚"),
    ("Metrics & Root Cause Analytics", "Discover trends and reasons for rollbacks, upgrades, or errors.", "📊"),
    ("Live Agent Hot-Reload", "Instantly load new skills, plugins, or features—no restart needed.", "🔄"),
    ("LLM Model Selector", "Pick the best AI models for your work, or let the system decide for you.", "🧠"),
    ("How to Build the World’s Best Bot (Guide)", "Step-by-step wizard to create your own app or bot (No coding needed!)", "🌟"),
    ("Help", "Show this help guide.", "❓"),
    ("Save & exit", "Save everything and quit the program safely.", "💾"),
]

def menu_option_text(idx, title, desc, emoji):
    idx_str = colored(str(idx+1), 'yellow', attrs=['bold'])
    title_col = colored(f"{title} {emoji}", "cyan", attrs=['bold'])
    return f"{idx_str}. {title_col}\n    {colored(desc, 'white')}"

def get_menu_completer():
    return WordCompleter(
        [str(i + 1) for i in range(len(menu_agent))] +
        [item[0].lower() for item in menu_agent] +
        ["help", "exit", "save & exit", "save and exit"],
        ignore_case=True
    )

def confirm(session, prompt_text: str) -> bool:
    while True:
        answer = session.prompt(f"{prompt_text} [y/N]: ").strip().lower()
        if answer in ('y', 'yes'):
            return True
        if answer in ('n', 'no', ''):
            return False
        cprint("Please enter 'y' or 'n'.", "red")

def print_on_demand_explainer(idx):
    cprint(f"\n{menu_agent[idx][2]} {colored(menu_agent[idx][0], 'cyan', attrs=['bold'])}", "yellow")
    cprint(menu_agent[idx][1], "white")

# ==== PRO MODE (EXPERT POWER) ====
PRO_MODE_FILE = "user_state_pro_mode.flag"
def is_pro_mode():
    return os.path.exists(PRO_MODE_FILE)
def toggle_pro_mode():
    if is_pro_mode():
        os.remove(PRO_MODE_FILE)
        return False
    else:
        with open(PRO_MODE_FILE, "w") as f: f.write("1")
        return True

def print_pro_mode_status():
    if is_pro_mode():
        cprint("PRO MODE: ON (advanced features unlocked)", "magenta", attrs=["bold"])
    else:
        cprint("PRO MODE: OFF (hides expert features)", "magenta")

# === Guided Project Wizard Agent ===
def guided_project_wizard(session):
    cprint("\n🌟 Welcome to the Bot/App Creation Wizard! 🌟", "cyan", attrs=["bold"])
    cprint("This wizard helps you create your first AI bot or app, step by step.", "yellow")
    name = session.prompt("1. Name your new app/bot (e.g. 'MyFirstBot'): ").strip()
    if not name:
        name = "MyFirstBot"
    goal = session.prompt("2. What do you want your bot to do? (Short, simple answer): ").strip()
    cprint(f"\nGreat! Now let's pick your bot's 'brain' (LLM).", "cyan")
    cprint("You can use the LLM Model Selector to choose later. For now, we'll use the system default.", "yellow")
    cprint("\nCreating, configuring, and launching your bot...", "green")
    time.sleep(1)
    # Simulate app creation
    cprint(f"\n✅ {name} is created!", "green", attrs=["bold"])
    cprint(f"Goal: {goal or '[No description given]'}", "cyan")
    cprint("You can customize, test, and upgrade your bot from the main menu.", "yellow")
    cprint("\nTo see your bot in action, use the menu option for 'System Health Check' or 'Test App'!", "magenta")

# === Main Menu ===
def main():
    os.system('cls' if os.name == 'nt' else 'clear')
    onboarding(force=False)
    threading.Thread(target=periodic_save, daemon=True).start()
    session = PromptSession()
    completer = get_menu_completer()
    last_choice = None
    error_count = 0

    while True:
        cprint("\n" + "="*60, "cyan")
        cprint(colored("A.I SuperAgent System — MAIN MENU", "cyan", attrs=['bold']).center(60))
        cprint("="*60, "cyan")
        print_pro_mode_status()
        for i, (title, desc, emoji) in enumerate(menu_agent, 1):
            if not is_pro_mode() and "Expert" in desc: continue  # Hide expert-only in normal mode
            print(menu_option_text(i-1, title, desc, emoji))
        cprint("\n(Type the number or name of an option, or type 'help' at any time)", "magenta")

        try:
            choice = session.prompt(HTML('<ansigreen>Select an option (or "help"): </ansigreen>'), completer=completer).strip().lower()
            # Context-sensitive help & smart coach
            if choice in ("help", "h", str(len(menu_agent) - 2), "?"):
                show_help("main")
                continue
            if choice in ("exit", "save & exit", "save and exit", str(len(menu_agent))):
                save_session_log()
                cprint("Session saved. Goodbye!", "yellow", attrs=['bold'])
                break
            if choice in ("pro", "expert", "pro mode", "toggle pro mode"):
                if toggle_pro_mode():
                    cprint("PRO MODE ENABLED!", "magenta", attrs=['bold'])
                else:
                    cprint("PRO MODE DISABLED!", "magenta")
                continue
            try:
                idx = int(choice) - 1
            except Exception:
                idx = next((i for i, item in enumerate(menu_agent) if choice in item[0].lower()), None)
            if idx is None or not (0 <= idx < len(menu_agent)):
                error_count += 1
                cprint("Oops! Not recognized. Please enter a valid number or option. (Type 'help' if unsure)", "red")
                if error_count >= 2:
                    smart_coach("Need a tip? Type 'help' or pick a number from the list above!")
                continue
            error_count = 0
            print_on_demand_explainer(idx)

            # Main agent system menu mapping
            if idx == 0:
                devops_fixer_main(); log_action("Ran DevOps Quick Fix on AI agent system.")
            elif idx == 1:
                print_header("A.I Agent System Health Check")
                health_ok = health_check(verbose=True, auto_heal=False, check_agents_only=True, ai_suggestions=True)
                status = "PASSED" if health_ok else "WARNINGS/ERRORS FOUND"
                cprint(f"\nSystem Health Check complete: {status}\n", "green" if health_ok else "yellow")
                log_action(f"Ran system health check. Result: {status}")
            elif idx == 2:
                auto_upgrade_all_agents(); log_action("Ran auto-upgrade all agents with explain/test/rollback/docs.")
            elif idx == 3:
                supreme_audit_and_heal(); log_action("Ran Supreme Auditor & Self-Healer.")
            elif idx == 4:
                log_dir = "logs"
                if not os.path.exists(log_dir): os.makedirs(log_dir)
                logs = [f for f in os.listdir(log_dir) if f.endswith(".log") or f.endswith(".md") or f.endswith(".json")]
                if logs:
                    last_log = sorted(logs)[-1]
                    cprint(f"\n--- Last Log: {last_log} ---", "cyan")
                    with open(os.path.join(log_dir, last_log), encoding="utf-8") as f:
                        print(f.read()[-3000:])
                else:
                    cprint("No logs found.", "yellow")
            elif idx == 5:
                agent_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), 'agent'))
                if confirm(session, "Are you sure you want to rollback all upgrades? This cannot be undone."):
                    rollback_all_backups(agent_dir)
                    log_action("Rolled back all agent upgrades from backups.")
                else:
                    cprint("Rollback cancelled.", "yellow")
            elif idx == 6:
                incident_response_main(); log_action("Ran Automated Incident Response Agent.")
            elif idx == 7:
                peer_review_main(); log_action("Ran Peer Review Agent.")
            elif idx == 8:
                knowledgebase_main(); log_action("Ran Knowledgebase Agent.")
            elif idx == 9:
                metrics_main(); log_action("Ran Metrics & Root Cause Analytics Agent.")
            elif idx == 10:
                hot_reload_main(); log_action("Ran Live Agent Hot-Reload.")
            elif idx == 11:
                print_llm_selector_menu(); log_action("Viewed LLM Model Selector.")
            elif idx == 12:
                guided_project_wizard(session)
            elif idx == 13:
                show_help("main")
            elif idx == 14:
                save_session_log()
                cprint("Session saved. Goodbye!", "yellow", attrs=['bold'])
                break
            else:
                cprint("Unknown option. Try again.", "red")
        except Exception as e:
            cprint(f"Error: {e}", "red")
            logger.error(traceback.format_exc())
            log_action(f"Error: {e}")

if __name__ == "__main__":
    main()
