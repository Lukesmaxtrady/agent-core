import os
import json
import time
import threading
import uuid
from pathlib import Path
from typing import Callable, Dict, Any, List, Optional, Union

EVENTS_DIR = Path("events")
EVENTS_DIR.mkdir(exist_ok=True)

def _event_filename(event_type, ts=None):
    ts = ts or time.time()
    return EVENTS_DIR / f"event_{event_type}_{int(ts*1000)}_{uuid.uuid4().hex[:8]}.json"

def publish_event(
    event_type: str,
    data: Dict[str, Any],
    correlation_id: Optional[str] = None,
    parent_event: Optional[str] = None,
    is_request: bool = False,
    is_response: bool = False
) -> Path:
    """
    Publish an event to the events/ directory.
    Supports requests, responses, and regular events.
    """
    ts = time.time()
    event = {
        "type": event_type,
        "timestamp": ts,
        "data": data,
        "correlation_id": correlation_id or str(uuid.uuid4()),
        "parent_event": parent_event,
        "is_request": is_request,
        "is_response": is_response
    }
    fname = _event_filename(event_type, ts)
    with open(fname, "w", encoding="utf-8") as f:
        json.dump(event, f)
    return fname

def publish_request(event_type: str, data: Dict[str, Any], parent_event: Optional[str] = None) -> str:
    correlation_id = str(uuid.uuid4())
    publish_event(event_type, data, correlation_id=correlation_id, parent_event=parent_event, is_request=True)
    return correlation_id

def publish_response(event_type: str, data: Dict[str, Any], correlation_id: str, parent_event: Optional[str] = None):
    publish_event(event_type, data, correlation_id=correlation_id, parent_event=parent_event, is_response=True)

def listen_events(
    callback: Callable[[Dict[str, Any]], None],
    event_types: Optional[List[str]] = None,
    correlation_id: Optional[str] = None,
    poll_interval: float = 1.0
):
    """
    Continuously listen for new events in events/ directory.
    Can filter by event_types and/or correlation_id (request/response workflows).
    """
    seen = set()
    while True:
        files = sorted(EVENTS_DIR.glob("event_*.json"))
        for file in files:
            if file in seen:
                continue
            with open(file, encoding="utf-8") as f:
                try:
                    event = json.load(f)
                except Exception:
                    continue
            if (event_types is None or event["type"] in event_types) and \
               (correlation_id is None or event["correlation_id"] == correlation_id):
                callback(event)
            seen.add(file)
        time.sleep(poll_interval)

def start_listener_in_thread(callback, event_types=None, correlation_id=None, poll_interval=1.0):
    t = threading.Thread(
        target=listen_events, 
        args=(callback, event_types, correlation_id, poll_interval),
        daemon=True
    )
    t.start()
    return t

# --- USAGE EXAMPLES ---

# Agent A (requester):
# correlation_id = publish_request("upgrade_request", {"target": "agent_b", "params": {...}})

# Agent B (responder):
# def handle(event):
#     # ... do upgrade ...
#     publish_response("upgrade_result", {"result": "success"}, correlation_id=event["correlation_id"])
# start_listener_in_thread(handle, event_types=["upgrade_request"])

# Agent A (listen for result):
# def result_handler(event): ...
# start_listener_in_thread(result_handler, event_types=["upgrade_result"], correlation_id=correlation_id)

