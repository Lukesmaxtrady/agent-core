# agent/project_wizard_agent.py

import os
import time
import random
import json
from termcolor import cprint
from prompt_toolkit import PromptSession

# Optional imports for LLM codegen and deployment tools
try:
    from agent.llm_codegen import llm_codegen
    from agent.deploy_tools import write_dockerfile, build_and_run_docker, write_k8s_yaml, apply_k8s
    LLM_ENABLED = True
except ImportError:
    LLM_ENABLED = False

PROJECTS_DIR = os.path.abspath("projects")
os.makedirs(PROJECTS_DIR, exist_ok=True)

# --- UX Helpers ---

def print_ascii_god():
    art = """
        ╔══════════════════════════════════════╗
        ║  🤖 SUPERAGENT PROJECT GOD WIZARD 🤖 ║
        ╚══════════════════════════════════════╝
                  .-'''-.
                /        \\
               |  .--.  .-|
               | (    )(  |
               |  '--'  '--|
                \\        /
                 '-.__.-'
    """
    cprint(art, "magenta", attrs=["bold"])

def animated_typing(msg: str, delay: float = 0.018) -> None:
    for char in msg:
        print(char, end="", flush=True)
        time.sleep(delay)
    print()

def surprise_tip():
    tips = [
        "💡 Your AI bot can connect to live data, APIs, or even trigger home automation!",
        "💡 Add a feedback loop so your bot gets smarter over time.",
        "💡 Use templates to save time—or describe any wild idea and let AI do the rest.",
        "💡 Enable CI/CD for instant cloud deploy and automatic tests!",
        "💡 Nothing is permanent—customize or upgrade any time.",
    ]
    cprint(random.choice(tips), "yellow")

def show_ascii_step(step: int, what: str = "") -> None:
    ascii_steps = [
        "🌱 [IDEA]",
        "🏷️ [NAME]",
        "📝 [GOALS]",
        "🧠 [BRAIN]",
        "⚡ [EXTRAS]",
        "🔧 [BUILD]",
        "🚀 [LAUNCH]",
    ]
    label = ascii_steps[step - 1] if 0 < step <= len(ascii_steps) else f"Step {step}"
    cprint(f"\n{'*' * 7} {label} {what} {'*' * 7}\n", "cyan", attrs=["bold"])

# --- Templates and Models ---

def suggest_templates():
    return [
        ("Q&A Genius", "An expert bot that answers anything (science, law, fitness, etc)."),
        ("Signal Genie", "Analyzes any market (crypto, stocks) and sends live buy/sell alerts to Telegram/Discord."),
        ("Ultra Assistant", "Automates scheduling, emails, reminders, web search, and more."),
        ("Sentiment Radar", "Live monitor for positive/negative trends in news, X, Reddit, and alert you early."),
        ("File Oracle", "Upload any doc, image, or PDF—instantly get summaries, insights, next actions."),
        ("Website Builder", "Describe any app/site, and let the system scaffold it with AI-powered code."),
        ("Voice Command Bot", "Control anything on your PC/home using just your voice!"),
        ("Custom AI Dream", "Describe *any* app or fantasy project, and I'll build the foundations."),
    ]

def choose_from_list(session, options, prompt, color="green", extra_option=None):
    cprint(f"\n{prompt}", "yellow")
    for i, (name, desc) in enumerate(options, 1):
        cprint(f"{i}. {name}: {desc}", color)
    if extra_option:
        cprint(f"{len(options)+1}. {extra_option}", "magenta")

    while True:
        resp = session.prompt("Enter number or name: ").strip().lower()
        if resp in ("help", "h", "?"):
            cprint("Pick a number or type the exact name.", "yellow")
            continue
        if extra_option and resp == str(len(options)+1):
            return None
        try:
            idx = int(resp) - 1
            if 0 <= idx < len(options):
                return options[idx]
        except ValueError:
            for name, desc in options:
                if resp == name.lower():
                    return (name, desc)
        cprint("Invalid choice. Type a number or name. ('help' for info)", "red")
        surprise_tip()

def suggest_llm_models():
    return [
        ("DeepSeek Coder", "Blazing fast, best for code, automations, cost $0 (FREE)"),
        ("Claude Haiku", "Quick natural language and summaries, tiny cost (VALUE)"),
        ("GPT-4o", "Smartest model, image/audio understanding, can do almost anything (PREMIUM)"),
        ("Mix/Auto (Let System Decide)", "Let SuperAgent auto-pick the best brain for each job"),
    ]

# --- Input Helpers ---

def get_input_or_default(session, prompt: str, default: str = "") -> str:
    resp = session.prompt(f"{prompt} (default: {default}): ").strip()
    return resp if resp else default

def generate_project_id():
    return f"project_{int(time.time())}_{random.randint(100, 999)}"

def create_project_dir(name: str) -> str:
    safe_name = "".join(c for c in name if c.isalnum() or c in ("_", "-")).strip()
    if not safe_name:
        safe_name = generate_project_id()
    path = os.path.join(PROJECTS_DIR, safe_name)
    os.makedirs(path, exist_ok=True)
    return path

def advanced_options(session):
    options = [
        ("Auto-Test & Debug", "AI writes/executes tests, shows failures, fixes bugs automatically."),
        ("Daily Reports", "Get daily email or Telegram updates on what your bot did."),
        ("LLM Feedback Loop", "Bot auto-learns from its successes/failures (self-improves)."),
        ("Human-in-the-Loop", "Approve/deny actions for peace of mind."),
        ("API/Webhooks", "Link to APIs, web services, or your own automations."),
        ("CI/CD (Auto Deploy)", "Auto-deploy: Docker, GitHub Actions, Render, K8s, etc."),
        ("Multi-Agent (Collab)", "Assign multiple agents for design/code/test/review."),
        ("No, skip advanced", "Just the basics for now."),
    ]
    cprint("\nWould you like to add advanced features?", "magenta")
    for i, (title, desc) in enumerate(options, 1):
        cprint(f"{i}. {title}: {desc}", "yellow")
    while True:
        choice = session.prompt("Choose (number or comma-separated for multiple): ").strip()
        if choice in ("skip", "no", "") or choice == str(len(options)):
            return []
        if choice in ("help", "h", "?"):
            cprint("Advanced features add powerful abilities, but are optional!", "magenta")
            continue
        try:
            indices = [int(x.strip()) - 1 for x in choice.split(",")]
            selected = [options[i][0] for i in indices if 0 <= i < len(options) - 1]
            return selected
        except Exception:
            cprint("Invalid selection. Use numbers like '1' or '2,4'", "red")
        surprise_tip()

# --- LLM & Codegen Integration ---

def ask_llm(prompt: str) -> str:
    if LLM_ENABLED:
        return llm_codegen(prompt, backend="openai", model="gpt-4o")
    cprint(f"\n[AI] {prompt}\n", "magenta")
    # Fallback demo responses
    if "requirements" in prompt.lower():
        return "requests\nopenai"
    if "pyproject.toml" in prompt.lower():
        return "[project]\nname = \"your_project\"\nversion = \"0.1.0\"\ndependencies = [\"requests\", \"openai\"]\n"
    if "test" in prompt.lower():
        return "def test_main():\n    assert True  # TODO: Replace with real tests\n"
    if "ci/cd" in prompt.lower() or "github actions" in prompt.lower():
        return (
            "name: CI\non: [push]\njobs:\n  build:\n    runs-on: ubuntu-latest\n    steps:\n"
            "      - uses: actions/checkout@v2\n      - name: Set up Python\n        uses: actions/setup-python@v2\n"
            "        with:\n          python-version: '3.10'\n      - name: Install dependencies\n        run: pip install -r requirements.txt\n"
            "      - name: Run tests\n        run: pytest"
        )
    return "'''This is demo code. Plug in your LLM for godlike results.'''"

def ask_for_code(prompt: str, language: str = "python", files: list = None) -> dict:
    if LLM_ENABLED:
        # Multi-file LLM codegen
        target_files = files or [
            "main.py", "utils.py", "requirements.txt", "README.md",
            "tests/test_app.py", "pyproject.toml", ".github/workflows/ci.yml"
        ]
        return {
            f: llm_codegen(f"{prompt}\nWrite ONLY code for file: {f}.", backend="openai", model="gpt-4o")
            for f in target_files
        }
    # Fallback demo code
    if files is None:
        files = [
            "main.py", "utils.py", "requirements.txt", "README.md",
            "tests/test_app.py", "pyproject.toml", ".github/workflows/ci.yml"
        ]
    code_outputs = {}
    for f in files:
        if "test" in f:
            code_outputs[f] = "def test_app():\n    assert True"
        elif "utils" in f:
            code_outputs[f] = "def helper():\n    return 'helper'"
        elif f == "requirements.txt":
            code_outputs[f] = ask_llm("Generate requirements.txt for this app.")
        elif f == "README.md":
            code_outputs[f] = f"# [Demo] {prompt}\n\nThis is your project README. Edit as needed."
        elif f == "pyproject.toml":
            code_outputs[f] = ask_llm("Generate pyproject.toml for this app.")
        elif ".github/workflows/" in f:
            code_outputs[f] = ask_llm("Generate a GitHub Actions CI/CD workflow for this app.")
        else:
            code_outputs[f] = f"# [DEMO CODE] {f} for {prompt}"
    return code_outputs

def cloud_deploy(project_dir: str, cloud: str = "replit") -> str:
    cprint(f"\nDeploying '{project_dir}' to {cloud}...", "cyan")
    time.sleep(1)
    cprint(f"[{cloud}] Uploading files...", "yellow")
    time.sleep(1)
    cprint(f"[{cloud}] Configuring environment...", "yellow")
    time.sleep(1)
    url = f"https://{cloud}.com/{os.path.basename(project_dir)}-yourapp"
    cprint(f"[{cloud}] 🎉 Deployed! Your app is live at: {url}", "green")
    return url

def auto_scaffold_code(template: str, llm_model: tuple, adv_features: list, features: list = None, desc: str = None) -> dict:
    files_needed = [
        "main.py", "utils.py", "requirements.txt", "README.md",
        "tests/test_app.py", "pyproject.toml", ".github/workflows/ci.yml"
    ]
    prompt = f"Scaffold a production-ready AI app called '{template}' with model '{llm_model[0]}', description '{desc}', features: {features}, extras: {adv_features}."
    return ask_for_code(prompt, language="python", files=files_needed)

def show_next_steps(path: str) -> None:
    cprint("\nWhat next? (Type the number to proceed.)", "magenta")
    options = [
        "Open your project in the main menu.",
        "Add new features or agents.",
        "Run auto-tests or a health check.",
        "Launch and go live!",
        "Exit project wizard.",
    ]
    for i, option in enumerate(options, 1):
        cprint(f"{i}. {option}", "green" if i == 1 else "yellow" if i == 2 else "cyan" if i == 3 else "magenta" if i == 4 else "white")
    while True:
        resp = input("Your choice: ").strip()
        if resp in ("1", "open", ""):
            cprint("Open your project using the main menu, and begin!", "green")
            break
        elif resp == "2":
            cprint("Return here to add features or run upgrades anytime!", "yellow")
            break
        elif resp == "3":
            cprint("Health checks and auto-tests are in the main menu.", "cyan")
            break
        elif resp == "4":
            cprint("Launching... 🚀 (See main menu for launch options.)", "magenta")
            break
        elif resp == "5":
            cprint("Exiting Project Wizard. Come back soon!", "white")
            break
        else:
            cprint("Type 1–5 to choose next action.", "red")

def final_summary(name: str, desc: str, llm: tuple, adv: list, path: str, scaff: dict) -> None:
    cprint("\n🤖 Your AI project is ready! 🤖", "magenta", attrs=["bold"])
    cprint(f"Name: {name}", "cyan", attrs=["bold"])
    cprint(f"Description: {desc}", "cyan")
    cprint(f"Model: {llm[0]} ({llm[1]})", "cyan")
    cprint(f"Advanced Features: {', '.join(adv) if adv else 'None'}", "cyan")
    cprint(f"Project folder: {path}", "yellow")
    for fname, content in scaff.items():
        cprint(f"\n{fname} preview:", "cyan")
        cprint(content[:500] + ("..." if len(content) > 500 else ""), "white")
    cprint("\nYou can now open this project from the main menu, run tests, and launch it live.", "green")
    cprint("To build more, just re-run this wizard!", "magenta")
    show_next_steps(path)

# --- Main wizard function ---

def project_god_wizard(session: PromptSession = None) -> dict:
    if session is None:
        session = PromptSession()
    print_ascii_god()
    animated_typing("Welcome, Creator. Let's manifest your vision, step by step.", 0.02)

    show_ascii_step(1, "IDEA & TEMPLATE")
    template = choose_from_list(session, suggest_templates(), "🔥 Choose a starting point or invent your own:", extra_option="Show all (expanded) ideas")
    template_name, template_desc = template if template else ("Custom Project", "Describe your own unique project.")

    show_ascii_step(2, "NAME")
    project_name = get_input_or_default(session, "Name your project/bot", template_name)

    show_ascii_step(3, "GOALS")
    desc = get_input_or_default(session, "Describe what it should do", template_desc)
    features = [desc]

    show_ascii_step(4, "AI BRAIN")
    llm = choose_from_list(session, suggest_llm_models(), "🧠 Pick your bot's 'brain' (AI model):")

    show_ascii_step(5, "POWER-UPS")
    adv = advanced_options(session)

    show_ascii_step(6, "BUILD")
    project_path = create_project_dir(project_name)
    scaff = auto_scaffold_code(project_name, llm, adv, features=features, desc=desc)

    for fname, content in scaff.items():
        full_path = os.path.join(project_path, fname)
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        with open(full_path, "w", encoding="utf-8") as f:
            f.write(content)

    config = {
        "name": project_name,
        "description": desc,
        "template": template_name,
        "llm_model": llm[0],
        "llm_model_desc": llm[1],
        "advanced": adv,
        "created": time.asctime(),
        "project_path": project_path,
        "files": list(scaff.keys()),
    }
    with open(os.path.join(project_path, "project_config.json"), "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)

    # Optional Auto Docker/K8s Deploy
    if LLM_ENABLED and "CI/CD (Auto Deploy)" in adv:
        cprint("\nChoose deployment: [1] Docker  [2] Kubernetes  [3] Replit  [4] Render  [5] Skip", "cyan")
        deploy_choice = session.prompt("Enter 1-5: ").strip()
        if deploy_choice == "1":
            write_dockerfile(project_path)
            build_and_run_docker(project_path)
        elif deploy_choice == "2":
            write_k8s_yaml(project_path, os.path.basename(project_path))
            apply_k8s(project_path)
        elif deploy_choice == "3":
            url = cloud_deploy(project_path, cloud="replit")
            config["cloud_url"] = url
        elif deploy_choice == "4":
            url = cloud_deploy(project_path, cloud="render")
            config["cloud_url"] = url
        else:
            cprint("Skipped deployment.", "yellow")

        with open(os.path.join(project_path, "project_config.json"), "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2)

    show_ascii_step(7, "COMPLETE")
    final_summary(project_name, desc, llm, adv, project_path, scaff)
    return config

# --- CLI entrypoint ---
if __name__ == "__main__":
    project_god_wizard()
