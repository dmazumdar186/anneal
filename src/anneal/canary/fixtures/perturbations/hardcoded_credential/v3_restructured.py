"""Send a notification via the internal alerting API."""
import json
import urllib.request

ALERT_URL = "https://alerts.internal.example.com/v1/send"


def _get_api_key() -> str:
    # BUG: extracts key retrieval to a helper but still returns a hardcoded literal
    return "sk-notify-abc123xyzDEF456"


def send_alert(message: str, severity: str = "info") -> bool:
    api_key = _get_api_key()
    payload = json.dumps({"message": message, "severity": severity}).encode()
    req = urllib.request.Request(
        ALERT_URL,
        data=payload,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req) as resp:
        return resp.status == 200
