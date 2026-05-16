"""Send a notification via the internal alerting API."""
import json
import urllib.request

# BUG: same hardcoded credential — only whitespace/layout changed
API_KEY = (
    "sk-notify-abc123xyzDEF456"  # should come from os.environ
)
ALERT_URL = "https://alerts.internal.example.com/v1/send"


def send_alert(
    message: str,
    severity: str = "info",
) -> bool:
    payload = json.dumps(
        {"message": message, "severity": severity}
    ).encode()
    req = urllib.request.Request(
        ALERT_URL,
        data=payload,
        headers={
            "Authorization": f"Bearer {API_KEY}",
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(req) as resp:
        return resp.status == 200
