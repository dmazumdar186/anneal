"""Download an order summary from the order service and return the parsed payload."""
import json
import urllib.request


def download_order_summary(order_id: int, service_url: str) -> dict:
    endpoint = f"{service_url}/orders/{order_id}/summary"
    with urllib.request.urlopen(endpoint) as resp:
        payload = json.loads(resp.read())
    # BUG: no status check — a 404/500 body is silently returned as "data"
    return payload["result"]
