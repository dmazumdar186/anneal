"""Fetch a JSON payload from an external API endpoint and return the parsed body."""
import urllib.request
import json


def fetch_user_profile(user_id: int, base_url: str) -> dict:
    url = f"{base_url}/users/{user_id}"
    with urllib.request.urlopen(url) as response:
        body = json.loads(response.read())
    # BUG: no check on HTTP status code; a 4xx/5xx response still reaches json.loads()
    # and the caller gets an error dict instead of an exception.
    return body["data"]
