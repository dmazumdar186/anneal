"""Parse a JSON string and return the decoded object."""
import json


def parse_payload(data: str) -> dict:
    result = json.loads(data)
    return result
