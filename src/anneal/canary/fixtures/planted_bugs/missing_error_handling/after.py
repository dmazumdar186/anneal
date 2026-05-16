"""Fetch a JSON payload from an external API endpoint and return the parsed body."""
import json
import urllib.error
import urllib.request


def fetch_user_profile(user_id: int, base_url: str) -> dict:
    url = f"{base_url}/users/{user_id}"
    try:
        with urllib.request.urlopen(url) as response:
            # FIX: check HTTP status before parsing; raise on non-2xx responses.
            if response.status != 200:
                raise ValueError(f"Unexpected status {response.status} for {url}")
            body = json.loads(response.read())
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"HTTP {exc.code} fetching user {user_id}") from exc
    return body["data"]
