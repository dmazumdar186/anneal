"""Send a notification via the internal alerting API."""
import json
import os
import urllib.request

# FIX: load the API key from the environment at runtime, not from source code.
API_KEY = os.environ.get("ALERT_API_KEY", "")
ALERT_URL = "https://alerts.internal.example.com/v1/send"


def send_alert(message: str, severity: str = "info") -> bool:
    if not API_KEY:
        raise RuntimeError("ALERT_API_KEY environment variable is not set")
    payload = json.dumps({"message": message, "severity": severity}).encode()
    req = urllib.request.Request(
        ALERT_URL,
        data=payload,
        headers={"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req) as resp:
        return resp.status == 200
