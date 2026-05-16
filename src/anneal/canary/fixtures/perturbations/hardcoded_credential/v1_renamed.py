"""Post a monitoring event to the observability platform."""
import json
import urllib.request

# BUG: same hardcoded credential — token embedded as string literal
MONITORING_TOKEN = "tok-mon-xyz789abc000"
MONITORING_ENDPOINT = "https://monitor.internal.example.com/v2/events"


def post_event(event_type: str, metadata: dict) -> bool:
    payload = json.dumps({"type": event_type, "meta": metadata}).encode()
    req = urllib.request.Request(
        MONITORING_ENDPOINT,
        data=payload,
        headers={
            "Authorization": f"Token {MONITORING_TOKEN}",
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(req) as resp:
        return resp.status == 201
