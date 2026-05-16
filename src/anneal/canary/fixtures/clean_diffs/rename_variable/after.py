"""Parse a JSON string and return the decoded object."""
import json


def parse_payload(data: str) -> dict:
    payload = json.loads(data)
    return payload
