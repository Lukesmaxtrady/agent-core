# agent/peer_review_agent.py

import os
import datetime
import json
from pathlib import Path

from agent.event_bus import publish_event
from agent import utils

try:
    from termcolor import cprint
except ImportError:
    def cprint(msg, color=None, **kwargs): print(msg)


class PeerReviewAgent:
    BACKUP_ROOT = "logs/agent_backups"
    RETRIES = 3

    def __init__(self, agent_dir=None):
        self.agent_dir = Path(agent_dir) if agent_dir else Path(__file__).parent
        self.backup_root = Path(self.BACKUP_ROOT)

    def backup_agent_file(self, file_path: Path) -> str:
        backup_path = utils.backup_file(str(file_path), str(self.backup_root))
        if backup_path:
            utils.notify_human(f"[PeerReview] Backup created at {backup_path}")
        else:
            utils.notify_human(f"[PeerReview] Backup skipped, file not found: {file_path}")
        return backup_path

    def load_agent_code(self, file_path: Path) -> str:
        if file_path.exists():
            return file_path.read_text(encoding="utf-8")
        else:
            utils.notify_human(f"[PeerReview] Agent file not found: {file_path}")
            return ""

    def run_llm_review(self, agent_name: str, code: str) -> str:
        prompt = (
            f"Perform a thorough peer code review of this Python agent '{agent_name}'. "
            f"Identify any code smells, security issues, bugs, or improvements. "
            f"Suggest fixes or improvements with explanations.\n\n"
            f"Code:\n{code}"
        )
        response = utils.llm_call(client=None, prompt=prompt, model="gpt-4o", max_tokens=2000)
        if response:
            utils.notify_human(f"[PeerReview] LLM review completed for {agent_name}")
            return response
        else:
            utils.notify_human(f"[PeerReview] LLM review failed or returned empty for {agent_name}")
            return ""

    def save_review_report(self, agent_name: str, report: str):
        reports_dir = self.agent_dir / "peer_reviews"
        reports_dir.mkdir(exist_ok=True)
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        report_path = reports_dir / f"{agent_name}_review_{timestamp}.md"
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(report)
        utils.notify_human(f"[PeerReview] Review report saved: {report_path}")

    def perform_review(self, agent_name: str):
        file_path = self.agent_dir / f"{agent_name}.py"
        original_code = self.load_agent_code(file_path)
        if not original_code:
            return

        # Backup before review (in case fixes are applied later)
        self.backup_agent_file(file_path)

        # Run LLM review
        review_report = None
        for attempt in range(1, self.RETRIES + 1):
            review_report = self.run_llm_review(agent_name, original_code)
            if review_report:
                break
            utils.notify_human(f"[PeerReview] Retry {attempt}/{self.RETRIES} for LLM review...")

        if not review_report:
            utils.notify_human(f"[PeerReview] Failed to get review report after {self.RETRIES} attempts.")
            return

        self.save_review_report(agent_name, review_report)

        # Publish event with review details
        publish_event("peer_review_completed", {
            "agent": agent_name,
            "timestamp": datetime.datetime.now().isoformat(),
            "report_summary": review_report[:300]
        })


# CLI / entrypoint
def main_entry():
    agent_name = input("Enter the agent name to peer review: ").strip()
    if not agent_name:
        utils.notify_human("No agent name provided.")
        return
    pra = PeerReviewAgent()
    pra.perform_review(agent_name)

if __name__ == "__main__":
    main_entry()
