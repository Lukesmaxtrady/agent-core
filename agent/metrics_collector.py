# agent/metrics_collector.py

import json
from datetime import datetime
from pathlib import Path
import threading
import logging
from agent.event_bus import publish_event

try:
    from agent.root_cause_analytics import analyze_root_causes
except ImportError:
    analyze_root_causes = None

LOG_DIR = Path("logs/metrics")
METRICS_LOG = LOG_DIR / "metrics_events.json"
SUMMARY_LOG = LOG_DIR / "summary.json"
LOG_DIR.mkdir(parents=True, exist_ok=True)

LOG_LOCK = threading.Lock()  # Thread/process safety

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)

def collect_metrics() -> dict:
    """
    Collect system-wide metrics from events/logs.
    Extensible for custom agent/plugin/app analytics.
    """
    metrics = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "total_events": count_events(METRICS_LOG),
        "note": "Extend this for real metrics"
    }
    try:
        with LOG_LOCK:
            with open(METRICS_LOG, "a", encoding="utf-8") as f:
                f.write(json.dumps(metrics) + "\n")
        logging.info(f"✅ Metrics collected: {metrics}")
        publish_event("metrics_collected", metrics)
    except Exception as e:
        logging.error(f"[Metrics] Failed to write metrics log: {e}")
    return metrics

def count_events(logfile: Path) -> int:
    """
    Counts the number of events logged (for total_events).
    """
    try:
        with logfile.open("r", encoding="utf-8") as f:
            return sum(1 for _ in f)
    except Exception:
        return 0

def summarize_metrics_and_root_cause():
    """
    Summarize both metrics and root-cause analytics (if available).
    Optionally, summarize with LLM if present.
    """
    metrics = collect_metrics()
    combined = {"metrics": metrics}
    root_summary = ""
    if analyze_root_causes:
        try:
            print("\n🔍 Performing 7-day Root Cause Analysis…")
            report = analyze_root_causes(days=7)
            md = report.get("summary_markdown", "")
            print(md)
            combined["root_cause_report"] = report
            root_summary = md
            publish_event("metrics_and_root_cause", {
                "timestamp": datetime.utcnow().isoformat() + "Z",
                "total_incidents": report.get("total_incidents"),
                "agent_failure_counts": {k: int(v) for k, v in report.get("agent_failure_counts", {}).items()}
            })
        except Exception as e:
            msg = f"[Metrics] Root cause analytics failed: {e}"
            print(msg)
            logging.error(msg)
    else:
        msg = "⚠️ Root cause analytics module not found or import failed."
        print(msg)
        logging.warning(msg)
    # Save combined summary (easy for web dashboard, future LLM summarization)
    try:
        with LOG_LOCK:
            with open(SUMMARY_LOG, "a", encoding="utf-8") as f:
                f.write(json.dumps({
                    "timestamp": datetime.utcnow().isoformat() + "Z",
                    "summary": root_summary,
                    "metrics": metrics,
                }) + "\n")
    except Exception as e:
        logging.error(f"[Metrics] Failed to write summary log: {e}")
    return combined

def main_entry():
    """
    Entry point for Metrics & Root Cause Analytics Agent from main.py menu.
    Extensible, idempotent, safe to run repeatedly.
    """
    print("\n🚀 Running Metrics & Root Cause Analytics…")
    combined = summarize_metrics_and_root_cause()
    # Print extra info or call other analytics as the system grows
    # (e.g., LLM-powered trend summaries, webhook triggers, etc.)

if __name__ == "__main__":
    main_entry()
