# agent/root_cause_analytics.py

import os
import json
import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from collections import defaultdict, Counter

EVENTS_DIR = Path("events")
INCIDENTS_FILE = Path("logs/incident_responder/incident_summaries.json")
ANALYTICS_LOG = Path("logs/root_cause_analytics")
ANALYTICS_LOG.mkdir(parents=True, exist_ok=True)


def load_events(since: Optional[datetime.datetime] = None) -> List[Dict[str, Any]]:
    """
    Load event JSON files from EVENTS_DIR filtered by timestamp >= since.
    """
    events = []
    if not EVENTS_DIR.exists():
        print(f"[RootCauseAnalytics] Events directory {EVENTS_DIR} does not exist.")
        return events
    for file in sorted(EVENTS_DIR.glob("event_*.json")):
        try:
            with open(file, encoding="utf-8") as f:
                event = json.load(f)
            event_time = datetime.datetime.fromtimestamp(event.get("timestamp", 0))
            if not since or event_time >= since:
                event["event_time"] = event_time
                events.append(event)
        except Exception as e:
            print(f"[RootCauseAnalytics] Failed to load event {file}: {e}")
    return events


def load_incidents(since: Optional[datetime.datetime] = None) -> List[Dict[str, Any]]:
    """
    Load incident summaries filtered by detected_at >= since.
    """
    if not INCIDENTS_FILE.exists():
        return []
    try:
        with open(INCIDENTS_FILE, encoding="utf-8") as f:
            data = json.load(f)
        if since:
            data = [
                i for i in data
                if datetime.datetime.fromisoformat(i.get("detected_at", "")) >= since
            ]
        return data
    except Exception as e:
        print(f"[RootCauseAnalytics] Failed to load incidents: {e}")
        return []


def build_parent_chain(correlation_id: str, parent_map: Dict[str, str]) -> List[str]:
    """
    Build a chain of parent event IDs recursively from the correlation_id.
    """
    chain = []
    current_id = correlation_id
    visited = set()
    while current_id and current_id in parent_map and current_id not in visited:
        parent = parent_map[current_id]
        chain.append(parent)
        visited.add(current_id)
        current_id = parent_map.get(current_id)
    return chain


def analyze_root_causes(days: int = 7) -> Dict[str, Any]:
    """
    Perform root cause analysis over the last 'days' days.

    Returns a dictionary containing:
    - summary_markdown: markdown report string
    - total_incidents: total incident count
    - agent_failure_counts: Counter of failures per agent
    - root_chains: list of (agent, parent_chain) tuples
    - notable_failures: last few failure events
    """
    since = datetime.datetime.now() - datetime.timedelta(days=days)
    events = load_events(since)
    incidents = load_incidents(since)

    failure_types = {"upgrade_failed", "rollback", "test_failed", "plugin_failed", "health_fail"}
    failure_events = [e for e in events if e.get("type") in failure_types]

    root_cause_map = defaultdict(list)
    agent_counter = Counter()
    parent_link_map = {}

    # Build parent correlation map
    for ev in events:
        corr_id = ev.get("correlation_id")
        parent = ev.get("parent_event")
        if corr_id and parent:
            parent_link_map[corr_id] = parent

    # Group incidents by agent and map event types
    for incident in incidents:
        agent = incident.get("agent", "unknown")
        related_events = incident.get("events", [])
        for ev in related_events:
            ev_type = ev.get("event_type") or ev.get("type")
            root_cause_map[agent].append((ev_type, ev.get("timestamp")))
            agent_counter[agent] += 1

    # Build root cause chains
    root_chains: List[Tuple[str, List[str]]] = []
    for fail_event in failure_events:
        data = fail_event.get("data", {})
        agent = data.get("agent") or data.get("plugin") or data.get("target") or fail_event.get("type", "unknown")
        corr_id = fail_event.get("correlation_id")
        chain = build_parent_chain(corr_id, parent_link_map) if corr_id else []
        root_chains.append((agent, chain))

    # Compose Markdown report
    summary_md = (
        f"# Root Cause Analytics Report\n\n"
        f"## Analysis Period: {since.date()} to {datetime.datetime.now().date()}\n"
        f"### Total Incidents: {len(incidents)}\n\n"
        f"### Incidents by Agent:\n"
    )
    for agent, count in agent_counter.most_common():
        summary_md += f"- {agent}: {count}\n"

    summary_md += "\n### Sample Root Cause Chains:\n"
    for agent, chain in root_chains[:10]:
        chain_str = " → ".join(str(c) for c in chain) if chain else "No parent chain"
        summary_md += f"- {agent}: {chain_str}\n"

    summary_md += "\n### Notable Recent Failures:\n"
    for f in failure_events[-5:]:
        ts = datetime.datetime.fromtimestamp(f.get("timestamp", 0))
        data = f.get("data", {})
        agent = data.get("agent") or data.get("plugin") or data.get("target") or f.get("type", "unknown")
        summary_md += f"- {ts} | {agent} | {f.get('type')}\n"

    result = {
        "summary_markdown": summary_md,
        "total_incidents": len(incidents),
        "agent_failure_counts": agent_counter,
        "root_chains": root_chains,
        "notable_failures": failure_events[-5:],
    }

    # Save report files
    timestamp_str = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    out_md = ANALYTICS_LOG / f"root_cause_report_{timestamp_str}.md"
    out_json = ANALYTICS_LOG / f"root_cause_report_{timestamp_str}.json"

    try:
        with open(out_md, "w", encoding="utf-8") as f_md:
            f_md.write(summary_md)
        print(f"[RootCauseAnalytics] Saved Markdown report: {out_md}")
    except Exception as e:
        print(f"[RootCauseAnalytics] Failed to write Markdown report: {e}")

    try:
        with open(out_json, "w", encoding="utf-8") as f_json:
            json.dump(result, f_json, indent=2)
        print(f"[RootCauseAnalytics] Saved JSON report: {out_json}")
    except Exception as e:
        print(f"[RootCauseAnalytics] Failed to write JSON report: {e}")

    return result


if __name__ == "__main__":
    print("[RootCauseAnalytics] Running 7-day root cause analysis...")
    analysis_result = analyze_root_causes(7)
    print(analysis_result["summary_markdown"])
