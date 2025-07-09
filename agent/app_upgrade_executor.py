import datetime
import difflib
import logging
import os
from pathlib import Path
from typing import Optional, Tuple, List, Dict
from agent.event_bus import publish_event

try:
    from termcolor import cprint
except ImportError:
    def cprint(msg, color=None, **kwargs): print(msg)

try:
    import openai
    from dotenv import load_dotenv

    load_dotenv()
    OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
    if OPENAI_API_KEY:
        openai.api_key = OPENAI_API_KEY
    else:
        cprint("[ERROR] OPENAI_API_KEY not set in environment.", "red")
except Exception as e
    publish_event('error', {'agent': 'app_upgrade_executor', 'error': str(e), 'timestamp': datetime.now().isoformat()})  # [event_bus hook]
:
    openai = None
    cprint(f"[ERROR] OpenAI not configured: {e}", "red")

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)

REPORTS_DIR = Path("logs/perfection_reports")
BACKUP_ROOT = Path("logs/agent_backups/app_upgrades")
REPORTS_DIR.mkdir(parents=True, exist_ok=True)
BACKUP_ROOT.mkdir(parents=True, exist_ok=True)

class Planner:
    """
    Planner agent for interactive app goal decomposition, upgrade planning, and more.
    """

    def __init__(self, apps_base_dir: Optional[str] = None):
        self.apps_base_dir = (
            Path(apps_base_dir)
            if apps_base_dir
            else Path(__file__).parent.parent / "apps"
        )

    def read_all_code(self, app_path: str) -> Dict[str, str]:
        """
        Collect all code, config, and docs in app directory recursively as text.
        """
        file_data = {}
        app_path = Path(app_path)
        for path in app_path.rglob("*"):
            if path.suffix.lower() in {
                ".py", ".js", ".ts", ".json", ".yaml", ".yml",
                ".env", ".md", ".toml"
            }:
                try:
                    rel_path = path.relative_to(app_path)
                    file_data[str(rel_path)] = path.read_text(
                        encoding="utf-8", errors="ignore"
                    )
                except Exception as e
    publish_event('error', {'agent': 'app_upgrade_executor', 'error': str(e), 'timestamp': datetime.now().isoformat()})  # [event_bus hook]
:
                    logging.warning(f"Could not read {path}: {e}")
        return file_data

    def enumerate_upgrades(self, suggestions: str) -> List[str]:
        """
        Parse upgrade suggestions list from LLM output.
        """
        upgrades = []
        for line in suggestions.split("\n"):
            line = line.strip()
            if line and (line[0].isdigit() or line.startswith("-")):
                upgrades.append(line.lstrip("0123456789.- ").strip())
        return upgrades

    def show_diff(self, old: str, new: str, fname: str) -> None:
        diff = difflib.unified_diff(
            old.splitlines(),
            new.splitlines(),
            fromfile=f"{fname} (old)",
            tofile=f"{fname} (new)",
            lineterm="",
        )
        cprint("\n".join(diff), "blue")

    def ask_user(self, prompt: str) -> str:
        cprint(f"\n{prompt} [y/n/skip/quit/all]: ", "yellow", end="")
        return input().strip().lower()

    def app_llm_analysis(self, app_name: str, max_tokens: int = 4000) -> str:
        """
        Run LLM analysis of app for perfection suggestions.
        """
        if not openai:
            cprint("[ERROR] OpenAI client not configured.", "red")
            return ""

        app_path = self.apps_base_dir / app_name
        all_files = self.read_all_code(app_path)
        big_text = "\n\n".join(
            [
                f"\n# {fname}\n{content[:2000]}"
                for fname, content in list(all_files.items())[:25]
            ]
        )

        prompt = (
            "You are an expert multi-domain app reviewer AI. Deeply analyze this app, "
            "listing every way to make it world-class: security, architecture, UX, "
            "scalability, docs, CI/CD, and suggest at least 5 new features. Give actionable "
            "upgrade list, and summary.\n"
            f"{big_text}\n\n"
        )
        try:
            resp = openai.ChatCompletion.create(
                model="gpt-4o",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=max_tokens,
                temperature=0.15,
            )
            text = resp.choices[0].message.content
            return text
        except Exception as e
    publish_event('error', {'agent': 'app_upgrade_executor', 'error': str(e), 'timestamp': datetime.now().isoformat()})  # [event_bus hook]
:
            cprint(f"[ERROR] LLM analysis failed: {e}", "red")
            return ""

    def llm_apply_patch(
        self, app_path: str, upgrade_suggestion: str
    ) -> Tuple[Optional[str], Optional[str], Optional[str], Optional[str]]:
        """
        Use LLM to generate code patch for an upgrade suggestion.
        Returns (filename, new_code, explanation, summary) or (None, None, None, None) if fail.
        """
        if not openai:
            cprint("[ERROR] OpenAI client not configured.", "red")
            return None, None, None, None

        prompt = (
            f"Given the app at {app_path}, implement the following upgrade in the minimal, "
            f"world-class way:\n{upgrade_suggestion}\n"
            "Reply ONLY in this format:\n"
            "Filename: <filename>\n"
            "Explanation:\n"
            "<Short explanation of why and how the upgrade was made, line by line>\n"
            "Summary:\n"
            "<Plain English summary for users>\n"
            "Code:\n"
            "```python\n<code here>\n```"
        )
        try:
            resp = openai.ChatCompletion.create(
                model="gpt-4o",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=3000,
                temperature=0.1,
            )
            reply = resp.choices[0].message.content

            fname = None
            explanation = ""
            new_code = None
            summary = ""

            if "Filename:" in reply:
                parts = reply.split("Filename:")[1].split("\n", 1)
                fname = parts[0].strip()
                rest = parts[1] if len(parts) > 1 else ""
                if "Explanation:" in rest:
                    exp_part = rest.split("Explanation:")[1]
                    if "Summary:" in exp_part:
                        explanation = exp_part.split("Summary:")[0].strip()
                        sum_part = exp_part.split("Summary:")[1]
                        if "Code:" in sum_part:
                            summary = sum_part.split("Code:")[0].strip()
                            code_part = sum_part.split("Code:")[1]
                            if "```python" in code_part:
                                new_code = (
                                    code_part.split("```python")[1].split("```")[0].strip()
                                )
            return fname, new_code, explanation, summary
        except Exception as e
    publish_event('error', {'agent': 'app_upgrade_executor', 'error': str(e), 'timestamp': datetime.now().isoformat()})  # [event_bus hook]
:
            cprint(f"[ERROR] LLM patch generation failed: {e}", "red")
            return None, None, None, None

    def interactive_app_upgrade(self, app_path: str, suggestions_text: str) -> None:
        """
        Interactive loop: show each suggested upgrade, show/explain diff, apply or skip, with safe backup,
        summary, technical explanation, and rollback on error.
        """
        app_path = Path(app_path)
        upgrades = self.enumerate_upgrades(suggestions_text)
        applied = []
        skipped = []
        rollbacks = []
        session_summaries = []

        for upgrade in upgrades:
            cprint(f"\n=== Suggested Upgrade: ===\n{upgrade}", "cyan")
            fname, new_code, explanation, summary = self.llm_apply_patch(app_path, upgrade)
            if fname and new_code:
                target_path = app_path / fname
                # Dedicated backup in backup dir
                backup_dir = BACKUP_ROOT / app_path.name
                backup_dir.mkdir(parents=True, exist_ok=True)
                backup_path = backup_dir / f"{fname}_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.bak"
                old_code = target_path.read_text(encoding="utf-8") if target_path.exists() else ""
                if target_path.exists():
                    backup_path.write_text(old_code, encoding="utf-8")
                cprint(f"\n--- AI Explanation of Upgrade ---\n{explanation}", "magenta")
                cprint(f"\n--- Plain Summary ---\n{summary}", "yellow")
                self.show_diff(old_code, new_code, fname)
                resp = self.ask_user(f"Apply this upgrade to {fname}?")
                if resp in ("y", "yes", "all"):
                    target_path.write_text(new_code, encoding="utf-8")
                    cprint(f"[OK] Upgrade applied to {fname}!", "green")
                    applied.append(fname)
                    # Self-test
                    try:
                        import importlib.util
                        spec = importlib.util.spec_from_file_location(
                            fname.replace(".py", ""), str(target_path)
                        )
                        mod = importlib.util.module_from_spec(spec)
                        spec.loader.exec_module(mod)
                        if hasattr(mod, "self_test"):
                            cprint(f"[INFO] Running self_test for {fname}...", "blue")
                            result = mod.self_test()
                            if not result:
                                cprint(
                                    f"[FAIL] Self-test failed. Rolling back {fname}.", "red"
                                )
                                target_path.write_text(old_code, encoding="utf-8")
                                rollbacks.append(fname)
                            else:
                                cprint(f"[PASS] Self-test passed for {fname}.", "green")
                    except Exception as e
    publish_event('error', {'agent': 'app_upgrade_executor', 'error': str(e), 'timestamp': datetime.now().isoformat()})  # [event_bus hook]
:
                        cprint(f"[FAIL] Error during self-test: {e}", "red")
                        target_path.write_text(old_code, encoding="utf-8")
                        rollbacks.append(fname)
                    # Update README.md doc with explanation
                    readme = app_path / "README.md"
                    if readme.exists():
                        current = readme.read_text(encoding="utf-8")
                        readme.write_text(
                            current + f"\n\n# Upgrade: {upgrade}\n{explanation}\n", encoding="utf-8"
                        )
                    session_summaries.append({"file": fname, "summary": summary, "explanation": explanation})
                elif resp == "quit":
                    break
                else:
                    cprint(f"[SKIP] Upgrade skipped for {fname}.", "yellow")
                    skipped.append(fname)
            else:
                cprint(f"[INFO] LLM could not generate patch for: {upgrade}", "yellow")
                skipped.append(upgrade)

        if applied:
            resp = self.ask_user("Rollback all upgrades? (restore all backups)")
            if resp in ("y", "yes"):
                for fname in applied:
                    backup_dir = BACKUP_ROOT / app_path.name
                    backup_baks = sorted(backup_dir.glob(f"{fname}_*.bak"))
                    if backup_baks:
                        last_backup = backup_baks[-1]
                        target_path = app_path / fname
                        target_path.write_text(last_backup.read_text(encoding="utf-8"), encoding="utf-8")
                cprint("[OK] All upgrades rolled back.", "yellow")

        # Save session report
        report_path = (
            REPORTS_DIR / f"upgrade_report_{app_path.name}_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
        )
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(f"# Interactive App Upgrade Report ({app_path})\n")
            f.write(f"\n## Applied Upgrades\n{json.dumps(applied, indent=2)}\n")
            f.write(f"\n## Skipped Upgrades\n{json.dumps(skipped, indent=2)}\n")
            f.write(f"\n## Rollbacks\n{json.dumps(rollbacks, indent=2)}\n")
            f.write(f"\n## Summaries & Explanations\n{json.dumps(session_summaries, indent=2)}\n")
        cprint(f"[INFO] Upgrade session complete. Report saved to {report_path}", "yellow")
