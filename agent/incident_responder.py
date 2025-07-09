# agent/incident_responder.py

import os
import time
import json
import datetime
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional
from agent.event_bus import listen_events, publish_event

LOGS_DIR = Path("logs/incident_responder")
LOGS_DIR.mkdir(parents=True, exist_ok=True)
INCIDENT_SUMMARIES = LOGS_DIR / "incident_summaries.json"
METRICS_FILE = LOGS_DIR / "metrics.json"
LAST_NOTIFY_FILE = LOGS_DIR / "last_notify.json"

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)

FAILURE_EVENTS = {"upgrade_failed", "test_failed", "rollback", "plugin_failed", "health_fail", "plugin_static_analysis_failed"}
ROLLBACK_EVENTS = {"rollback", "plugin_failed"}
SUCCESS_EVENTS = {"upgrade_applied", "test_passed", "heal_succeeded"}
WINDOW = 1800  # 30 min incident window, can be per-agent in future
RETRY_LIMIT = 3  # Escalate if more than N failures per agent
NOTIFY_COOLDOWN = 600  # 10 min cooldown per agent for escalations

class IncidentResponderAgent:
    def __init__(self):
        self.recent_events: List[Any] = []
        self.agent_fail_counts: Dict[str, int] = {}
        self.incidents: List[Any] = []
        self.last_notified: Dict[str, float] = self.load_last_notify()

    def on_event(self, event: Dict[str, Any]):
        event_type = event.get("event_type")
        agent = event.get("agent") or event.get("plugin") or event.get("target")
        timestamp = event.get("timestamp", time.time())
        parent = event.get("parent_event")
        context = event.get("context") or {}

        # Maintain rolling window of recent events
        self.recent_events.append((event_type, agent, timestamp, event))
        now = time.time()
        self.recent_events = [(t, a, ts, ev) for t, a, ts, ev in self.recent_events if now - ts < WINDOW]

        # Detect failures
        if event_type in FAILURE_EVENTS and agent:
            prev_count = self.agent_fail_counts.get(agent, 0)
            count = prev_count + 1
            self.agent_fail_counts[agent] = count

            if count >= RETRY_LIMIT:
                # Incident escalation with cooldown
                if not self.cooldown_active(agent, now):
                    incident = {
                        "agent": agent,
                        "event_type": event_type,
                        "count": count,
                        "window": WINDOW,
                        "first_failure_time": self.find_first_failure_time(agent),
                        "events": [ev for t, a, ts, ev in self.recent_events if a == agent and t in FAILURE_EVENTS],
                        "parent": parent,
                        "context": context,
                        "detected_at": datetime.datetime.utcfromtimestamp(now).isoformat() + "Z",
                        "root_cause_hint": self.root_cause_hint(agent)
                    }
                    self.incidents.append(incident)
                    publish_event("incident_escalated", {"agent": agent, "incident": incident})
                    self.notify_admins(incident)
                    self.log_incident(incident)
                    self.last_notified[agent] = now
                    self.save_last_notify()
                    self.agent_fail_counts[agent] = 0  # Reset
                    logging.error(f"[INCIDENT] Agent {agent} had {count} failures in {WINDOW//60}min window! Incident escalated.")
                else:
                    logging.info(f"[INCIDENT] Escalation for {agent} suppressed due to cooldown.")
            else:
                logging.warning(f"[Warning] {agent} failure count: {count}/{RETRY_LIMIT}")
                publish_event("incident_warning", {"agent": agent, "fail_count": count})
        elif event_type in SUCCESS_EVENTS and agent:
            self.agent_fail_counts[agent] = 0  # Reset on any success
        self.write_metrics()

    def cooldown_active(self, agent: str, now: float) -> bool:
        last = self.last_notified.get(agent, 0)
        return (now - last) < NOTIFY_COOLDOWN

    def find_first_failure_time(self, agent: str) -> Optional[str]:
        for t, a, ts, ev in self.recent_events:
            if a == agent and t in FAILURE_EVENTS:
                return datetime.datetime.utcfromtimestamp(ts).isoformat() + "Z"
        return None

    def root_cause_hint(self, agent: str) -> str:
        # Naive: if last parent event was a deploy/upgrade, suggest as root cause
        for t, a, ts, ev in reversed(self.recent_events):
            if a == agent and ev.get("parent_event") in {"upgrade_applied", "deploy"}:
                return f"Likely caused by recent {ev['parent_event']} at {datetime.datetime.utcfromtimestamp(ts).isoformat()}Z"
        return "No clear root cause found"

    def notify_admins(self, incident: Dict[str, Any]):
        summary = (f"🚨 Incident Escalated: {incident['agent']} had {incident['count']} failures in "
                   f"{incident['window']//60}min.\nRoot Cause Hint: {incident.get('root_cause_hint')}")
        logging.error(summary)
        publish_event("admin_notify", {"type": "incident", "summary": summary})
        # (Optional) Slack/webhook/email logic can be placed here.

    def log_incident(self, incident: Dict[str, Any]):
        try:
            data = []
            if INCIDENT_SUMMARIES.exists():
                with open(INCIDENT_SUMMARIES, encoding="utf-8") as f:
                    data = json.load(f)
            data.append(incident)
            with open(INCIDENT_SUMMARIES, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logging.error(f"Failed to log incident: {e}")

    def write_metrics(self):
        metrics = {
            "total_incidents": len(self.incidents),
            "last_incident_time": self.incidents[-1]['detected_at'] if self.incidents else None,
            "agent_failure_counts": dict(self.agent_fail_counts)
        }
        try:
            with open(METRICS_FILE, "w", encoding="utf-8") as f:
                json.dump(metrics, f, indent=2)
        except Exception as e:
            logging.error(f"Failed to write metrics: {e}")

    def load_last_notify(self) -> Dict[str, float]:
        try:
            if LAST_NOTIFY_FILE.exists():
                with open(LAST_NOTIFY_FILE, encoding="utf-8") as f:
                    return json.load(f)
        except Exception:
            pass
        return {}

    def save_last_notify(self):
        try:
            with open(LAST_NOTIFY_FILE, "w", encoding="utf-8") as f:
                json.dump(self.last_notified, f, indent=2)
        except Exception:
            pass

    def run(self):
        logging.info("[IncidentResponder] Listening for agent failures, rollbacks, and patterns...")
        listen_events(
            callback=self.on_event,
            event_types=list(FAILURE_EVENTS | SUCCESS_EVENTS | ROLLBACK_EVENTS),
            poll_interval=1.0
        )
        # This call blocks and will keep listening forever.

def main_entry():
    """
    Entry point for the Incident Response Agent from main.py menu.
    """
    agent = IncidentResponderAgent()
    agent.run()

if __name__ == "__main__":
    main_entry()
