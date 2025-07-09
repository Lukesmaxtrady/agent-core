import os
import glob
import json
import datetime
from collections import defaultdict
from typing import List, Dict, Any, Optional
from agent.event_bus import publish_event

try:
    import openai
except ImportError:
    openai = None

EVENTS_DIR = "events"
PEER_REVIEWED_DIR = os.path.join(EVENTS_DIR, "peer_reviewed")
os.makedirs(EVENTS_DIR, exist_ok=True)
os.makedirs(PEER_REVIEWED_DIR, exist_ok=True)
DEFAULT_MODEL = "gpt-4o"

class SessionContext:
    def __init__(self):
        self.last_query = ""
        self.last_answer = ""
        self.last_events = []
        self.filters = {}
        self.timeline = ""

    def reset(self):
        self.last_query = ""
        self.last_answer = ""
        self.last_events = []
        self.filters = {}
        self.timeline = ""

session = SessionContext()

def load_all_events(limit=2000):
    event_files = sorted(glob.glob(os.path.join(EVENTS_DIR, "event_*.json")), reverse=True)
    events = []
    for fname in event_files[:limit]:
        try:
            with open(fname, encoding="utf-8") as f:
                e = json.load(f)
            events.append(e)
        except Exception:
            continue
    return events

def load_all_peer_reviews(limit=1000):
    review_files = sorted(glob.glob(os.path.join(PEER_REVIEWED_DIR, "review_*.json")), reverse=True)
    reviews = []
    for fname in review_files[:limit]:
        try:
            with open(fname, encoding="utf-8") as f:
                r = json.load(f)
            reviews.append(r)
        except Exception:
            continue
    return reviews

def filter_events(events, agent: Optional[str]=None, event_type: Optional[str]=None, since: Optional[str]=None):
    filtered = []
    since_ts = None
    if since:
        try:
            since_ts = datetime.datetime.fromisoformat(since).timestamp()
        except Exception:
            pass
    for e in events:
        et = e.get("event_type", e.get("type", "?"))
        ag = e.get("data", {}).get("agent", "unknown")
        # Use system-wide event timestamp
        t = (
            e.get("timestamp") or
            e.get("review_time") or
            e.get("time") or 0
        )
        # Parse timestamp if it's in string ISO format
        if isinstance(t, str):
            try:
                t = datetime.datetime.fromisoformat(t).timestamp()
            except Exception:
                t = 0
        if agent and agent.lower() not in ag.lower():
            continue
        if event_type and event_type.lower() != et.lower():
            continue
        if since_ts and t and t < since_ts:
            continue
        filtered.append(e)
    return filtered

def summarize_events(events: List[Dict], maxlen=150):
    rows = []
    for e in events[:maxlen]:
        et = e.get("event_type", e.get("type", "?"))
        ag = e.get("data", {}).get("agent", "unknown")
        t = (
            e.get("timestamp") or
            e.get("review_time") or
            e.get("time") or 0
        )
        if isinstance(t, str):
            try:
                t = datetime.datetime.fromisoformat(t).timestamp()
            except Exception:
                t = 0
        t_str = datetime.datetime.fromtimestamp(t).strftime("%Y-%m-%d %H:%M:%S") if t else "?"
        outcome = e.get("data", {}).get("verdict", "") or e.get("data", {}).get("result", "")
        rows.append(f"{t_str} | {ag} | {et} | {outcome}")
    return "\n".join(rows)

def event_timeline(events: List[Dict], agent=None, event_type=None, maxlen=100):
    lines = []
    for e in events[:maxlen][::-1]:
        et = e.get("event_type", e.get("type", "?"))
        ag = e.get("data", {}).get("agent", "unknown")
        t = (
            e.get("timestamp") or
            e.get("review_time") or
            e.get("time") or 0
        )
        if isinstance(t, str):
            try:
                t = datetime.datetime.fromisoformat(t).timestamp()
            except Exception:
                t = 0
        t_str = datetime.datetime.fromtimestamp(t).strftime("%m-%d %H:%M") if t else "?"
        if (agent and ag != agent) or (event_type and et != event_type):
            continue
        lines.append(f"{t_str}: [{et.upper()}] {ag}")
    return "\n".join(lines)

def risk_report(events, peer_reviews):
    fail_counts = defaultdict(int)
    rollback_counts = defaultdict(int)
    manual_review_counts = defaultdict(int)
    for e in events:
        ag = e.get("data", {}).get("agent", "unknown")
        et = e.get("event_type", e.get("type", ""))
        if et == "rollback":
            rollback_counts[ag] += 1
        if et == "upgrade" and "fail" in json.dumps(e).lower():
            fail_counts[ag] += 1
    for r in peer_reviews:
        ag = r.get("reviewed_event", {}).get("data", {}).get("agent", "unknown")
        v = r.get("verdict", "")
        if v == "needs_manual_review":
            manual_review_counts[ag] += 1
    out = "\nTop Failing/Rollback Agents:\n"
    for ag, cnt in sorted(fail_counts.items(), key=lambda x: -x[1])[:5]:
        out += f"  {ag}: {cnt} failures\n"
    for ag, cnt in sorted(rollback_counts.items(), key=lambda x: -x[1])[:5]:
        out += f"  {ag}: {cnt} rollbacks\n"
    for ag, cnt in sorted(manual_review_counts.items(), key=lambda x: -x[1])[:5]:
        out += f"  {ag}: {cnt} manual reviews\n"
    return out.strip()

def answer_question(question, context_events, peer_reviews, model=DEFAULT_MODEL):
    api_key = os.environ.get("OPENAI_API_KEY")
    client = None
    if openai and hasattr(openai, "OpenAI") and api_key:
        client = openai.OpenAI(api_key=api_key)
    if not client:
        return "[LLM not configured] Knowledgebase agent needs OpenAI setup."
    prompt = (
        "You are an AI knowledgebase agent for an advanced multi-agent system. "
        "You will be given the last 200 event and review summaries, a table of filtered events, and system stats.\n\n"
        f"Recent events:\n{summarize_events(context_events)}\n\n"
        f"Peer reviews:\n{summarize_events(peer_reviews)}\n\n"
        f"Stats/risk report:\n{risk_report(context_events, peer_reviews)}\n\n"
        "Timeline:\n" + event_timeline(context_events) + "\n\n"
        f"Question:\n{question}\n"
        "Instructions: Use ONLY this context. If you need to filter further, ask for a follow-up. "
        "Answer in bullet points or a table when appropriate. If you don't know, say so."
    )
    resp = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=1100,
        temperature=0.1,
    )
    return resp.choices[0].message.content.strip()

def advanced_query_interface(events, peer_reviews):
    print("\n[ADVANCED FILTER] (Leave blank to skip a filter)")
    agent = input("Filter by agent (e.g. deployer, planner): ").strip() or None
    event_type = input("Filter by event type (upgrade, rollback, etc.): ").strip() or None
    since = input("Since date (YYYY-MM-DD or blank for all): ").strip() or None
    filtered = filter_events(events, agent=agent, event_type=event_type, since=since)
    session.filters = {"agent": agent, "event_type": event_type, "since": since}
    print(f"\nShowing {len(filtered)} filtered events:\n")
    print(summarize_events(filtered, maxlen=30))
    session.last_events = filtered

def main():
    print("\n[Knowledgebase Agent v2] Type any question about system upgrades, tests, rollbacks, peer reviews, or agent history.")
    while True:
        # Always reload latest events
        events = load_all_events()
        peer_reviews = load_all_peer_reviews()
        print("\nOptions: [q]uery, [f]ilter, [r]isk report, [t]imeline, [reset], [exit]")
        cmd = input("Enter command: ").strip().lower()
        if cmd in ("exit", "quit"):
            print("Goodbye!")
            break
        elif cmd in ("f", "filter"):
            advanced_query_interface(events, peer_reviews)
        elif cmd in ("r", "risk"):
            print(risk_report(events, peer_reviews))
        elif cmd in ("t", "timeline"):
            print(event_timeline(events, maxlen=50))
        elif cmd in ("reset",):
            session.reset()
            print("Session context reset.")
        else:  # Assume it's a question
            q = cmd if cmd not in ("q", "query") else input("🔎 Ask a system question: ")
            filtered_events = session.last_events if session.last_events else events
            answer = answer_question(q, filtered_events, peer_reviews)
            print("\n[Knowledgebase Answer]:\n" + answer)
            session.last_query = q
            session.last_answer = answer
            publish_event("knowledgebase_query", {
                "question": q,
                "answer": answer,
                "filters": session.filters,
                "timestamp": datetime.datetime.now().isoformat()
            })

def main_entry():
    main()

if __name__ == "__main__":
    main()
