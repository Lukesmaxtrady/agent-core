# agent/tester.py

import datetime
import json
import logging
import os
import subprocess
from typing import Tuple, Dict, Any, Optional

from agent.event_bus import publish_event, publish_response, start_listener_in_thread
from dotenv import load_dotenv
from agent import utils
from agent.context_loader import load_app_context

# Setup logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)

# Load env and setup OpenAI client
load_dotenv()
api_key = os.getenv("OPENAI_API_KEY")
try:
    import openai
    client = openai.OpenAI(api_key=api_key) if api_key else None
except ImportError:
    client = None

CENTRAL_TEST_LOG = "logs/test_runs.json"
BACKUP_ROOT = "logs/agent_backups"

class Tester:
    BACKUP_SUFFIX_FORMAT = ".bak_%Y%m%d_%H%M%S"
    TEST_FILE_MIN_SIZE = 50
    MODEL_NAME = os.getenv("OPENAI_MODEL_NAME", "gpt-4o")
    MAX_TOKENS = 1000
    RETRIES = 3

    @staticmethod
    def backup_file(file_path: str) -> Optional[str]:
        return utils.backup_file(file_path, BACKUP_ROOT)

    @staticmethod
    def run_command(cmd: str) -> Tuple[str, bool]:
        try:
            result = subprocess.run(
                cmd, shell=True, text=True, capture_output=True, check=True
            )
            return result.stdout + result.stderr, True
        except subprocess.CalledProcessError as e:
            logging.error(f"Command failed: {e}")
            return f"[ERROR: {e}]\n{e.stdout}\n{e.stderr}", False

    @classmethod
    def run_tests(cls, app_name: str, auto_generate: bool = True) -> bool:
        """
        Run all tests for an app, auto-generate missing/weak test files, run linters, log output.
        Returns True if tests pass, False otherwise.
        """
        app_dir = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "apps", app_name)
        )
        context = load_app_context(app_name)
        now = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")

        py_files = [
            f
            for f in os.listdir(app_dir)
            if f.endswith(".py") and not f.startswith("test_")
        ]

        # --- Auto-generate/upgrade missing/weak test files (LLM + retries) ---
        if auto_generate and client:
            logging.info("Checking for missing/weak test files...")
            for fname in py_files:
                tfname = f"test_{fname}"
                tpath = os.path.join(app_dir, tfname)
                attempt = 1
                while (not os.path.exists(tpath) or os.path.getsize(tpath) < cls.TEST_FILE_MIN_SIZE) and attempt <= cls.RETRIES:
                    code = context["code_files"].get(fname, "")
                    prompt = (
                        f"Write robust pytest tests for this module. "
                        f"Include edge cases, security, error handling. Output only valid code for '{tfname}':\n\n{code}\n"
                    )
                    try:
                        response = client.chat.completions.create(
                            model=cls.MODEL_NAME,
                            messages=[{"role": "system", "content": prompt}],
                            max_tokens=cls.MAX_TOKENS,
                        )
                        tcode = response.choices[0].message.content.strip()
                        cls.backup_file(tpath)
                        with open(tpath, "w", encoding="utf-8") as f:
                            f.write(tcode)
                        logging.info(f"Auto-generated or upgraded: {tfname}")
                        break
                    except Exception as e:
                        publish_event('error', {'agent': 'tester', 'error': str(e), 'timestamp': datetime.datetime.now().isoformat()})
                        logging.error(f"LLM error creating {tfname} (attempt {attempt}): {e}")
                        attempt += 1

        # --- Run static checks and pytest ---
        logging.info("Running static checks (flake8, mypy, bandit)...")
        static_logs = {}
        for tool in ["flake8", "mypy", "bandit -r"]:
            out, ok = cls.run_command(f"{tool} {app_dir}")
            static_logs[tool] = out
            logging.info(f"\n--- {tool.upper()} ---\n{out}")

        logging.info("Running pytest with coverage...")
        pytest_cmd = (
            f"pytest --cov={app_dir} --cov-report=term-missing "
            f"--cov-config=.coveragerc {app_dir}"
        )
        test_out, test_ok = cls.run_command(pytest_cmd)
        logging.info(f"\n--- PYTEST ---\n{test_out}")

        # --- LLM coverage analysis and improvement suggestions ---
        coverage_analysis = ""
        if client:
            cov_prompt = (
                f"Given these static check logs and test results for {app_name}, "
                f"summarize test coverage and weaknesses.\n"
                f"Suggest improvements, new edge cases, and fixes in Markdown.\n\n"
                f"FLAKE8:\n{static_logs['flake8']}\n\n"
                f"MYPY:\n{static_logs['mypy']}\n\n"
                f"BANDIT:\n{static_logs['bandit -r']}\n\n"
                f"PYTEST:\n{test_out}\n"
            )
            try:
                coverage_analysis = utils.llm_call(client, cov_prompt, model=cls.MODEL_NAME, max_tokens=cls.MAX_TOKENS) or ""
                logging.info("\n--- COVERAGE ANALYSIS ---\n")
                logging.info(coverage_analysis)
            except Exception as e:
                publish_event('error', {'agent': 'tester', 'error': str(e), 'timestamp': datetime.datetime.now().isoformat()})
                logging.error(f"Coverage analysis failed: {e}")

        # --- Central log and memory update ---
        logs_dir = os.path.join(app_dir, "logs")
        os.makedirs(logs_dir, exist_ok=True)
        log_path = os.path.join(logs_dir, f"test_{now}.log")
        with open(log_path, "w", encoding="utf-8") as f:
            f.write(
                f"Test run at {datetime.datetime.now().isoformat()}\n\n"
                f"STATIC CHECKS:\n{json.dumps(static_logs, indent=2)}\n\n"
                f"PYTEST OUTPUT:\n{test_out}\n\n"
                f"COVERAGE ANALYSIS:\n{coverage_analysis}\n"
            )

        # --- Save to central test log ---
        cls.save_test_run_central(app_name, test_ok, coverage_analysis, static_logs, test_out)

        mem_path = os.path.join(app_dir, "memory.json")
        try:
            mem = {}
            if os.path.exists(mem_path):
                with open(mem_path, encoding="utf-8") as mf:
                    mem = json.load(mf)
            if "test_runs" not in mem:
                mem["test_runs"] = []
            mem["test_runs"].append(
                {
                    "timestamp": datetime.datetime.now().isoformat(),
                    "test_ok": test_ok,
                    "coverage_analysis": coverage_analysis[:2000],
                }
            )
            with open(mem_path, "w", encoding="utf-8") as mf:
                json.dump(mem, mf, indent=2)
        except Exception as e:
            publish_event('error', {'agent': 'tester', 'error': str(e), 'timestamp': datetime.datetime.now().isoformat()})
            logging.error(f"Error updating memory: {e}")

        # --- Notification and optional auto-fix loop ---
        if not test_ok:
            utils.notify_human("❌ Tests failed. Consider rollback or auto-fix.")
            for attempt in range(1, cls.RETRIES + 1):
                resp = input(f"Attempt LLM auto-fix? (attempt {attempt}/3, y/n): ").strip().lower()
                if resp.startswith("y"):
                    utils.notify_human("Auto-fix not yet implemented. Please review code and fix manually.")
                else:
                    break
        else:
            utils.notify_human("✅ All tests and checks passed. Results logged and memory updated.")

        # Always return pass/fail
        return test_ok

    @staticmethod
    def explain_test_coverage(app_name: str):
        """
        Summarize test coverage, suggest missing edge cases, improvements.
        """
        app_dir = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "apps", app_name)
        )
        code_files = []
        for fname in os.listdir(app_dir):
            if fname.endswith(".py") and not fname.startswith("test_"):
                with open(os.path.join(app_dir, fname), encoding="utf-8") as f:
                    code_files.append((fname, f.read()))
        test_files = [
            f
            for f in os.listdir(app_dir)
            if f.startswith("test_") and f.endswith(".py")
        ]

        prompt = (
            f"Given the following code files and their corresponding tests, summarize test coverage. "
            f"Identify any missing edge cases, and suggest improvements in Markdown.\n"
        )
        for fname, code in code_files:
            prompt += f"\n# {fname}\n{code}\n"
        for tname in test_files:
            with open(os.path.join(app_dir, tname), encoding="utf-8") as f:
                prompt += f"\n# {tname}\n{f.read()}\n"

        if client:
            try:
                response = client.chat.completions.create(
                    model=Tester.MODEL_NAME,
                    messages=[{"role": "system", "content": prompt}],
                    max_tokens=Tester.MAX_TOKENS,
                )
                logging.info("\n--- TEST COVERAGE REPORT ---\n")
                logging.info(response.choices[0].message.content)
            except Exception as e:
                publish_event('error', {'agent': 'tester', 'error': str(e), 'timestamp': datetime.datetime.now().isoformat()})
                logging.error(f"Test coverage report failed: {e}")

    @staticmethod
    def save_test_run_central(app_name: str, test_ok: bool, coverage: str, static_logs: Dict[str, Any], test_out: str):
        os.makedirs(os.path.dirname(CENTRAL_TEST_LOG), exist_ok=True)
        if os.path.exists(CENTRAL_TEST_LOG):
            with open(CENTRAL_TEST_LOG, encoding="utf-8") as f:
                all_logs = json.load(f)
        else:
            all_logs = []
        all_logs.append({
            "app": app_name,
            "timestamp": datetime.datetime.now().isoformat(),
            "test_ok": test_ok,
            "coverage_analysis": coverage[:2000],
            "static_logs": static_logs,
            "test_out": test_out[:2000]
        })
        with open(CENTRAL_TEST_LOG, "w", encoding="utf-8") as f:
            json.dump(all_logs, f, indent=2)

# EventBus handler for test requests
def handle_test_request(event):
    """
    Auto-injected event handler for 'test_request' in this agent.
    """
    print(f"[EventBus] Received test_request: {event}")
    result = {"status": "handled", "details": f"test_request handled by agent."}
    publish_response("test_result", result, correlation_id=event.get("correlation_id"))

def main_entry():
    """
    Entry point for menu/CLI-driven test agent.
    """
    app_name = input("Enter app name to test: ").strip()
    passed = Tester.run_tests(app_name)
    if passed:
        print("✅ All tests passed.")
    else:
        print("❌ Some tests failed.")

start_listener_in_thread(handle_test_request, event_types=["test_request"])

if __name__ == "__main__":
    main_entry()
