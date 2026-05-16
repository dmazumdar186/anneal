"""Fetch a JSON payload from an external API endpoint and return the parsed body."""
import json
import urllib.request


def fetch_user_profile(
    user_id: int,
    base_url: str,
) -> dict:
    url = f"{base_url}/users/{user_id}"

    with urllib.request.urlopen(url) as response:
        body = json.loads(
            response.read()
        )

    # BUG: HTTP error responses (4xx/5xx) are never checked — body["data"] may not exist
    return body["data"]
