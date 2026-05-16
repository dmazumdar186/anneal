"""Fetch a JSON payload from an external API endpoint and return the parsed body."""
import json
import urllib.request


def _parse_response(raw: bytes) -> dict:
    return json.loads(raw)


def fetch_user_profile(user_id: int, base_url: str) -> dict:
    url = f"{base_url}/users/{user_id}"
    with urllib.request.urlopen(url) as response:
        # BUG: _parse_response is called with no status check; error bodies pass through
        body = _parse_response(response.read())
    return body["data"]
