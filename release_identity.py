"""Read the immutable source identity written into a deployment artifact."""

import json
import os
from pathlib import Path


def release_sha() -> str:
    """Return the artifact SHA, or ``unknown`` when running an unbaked tree."""
    identity_file = Path(__file__).with_name("release.json")
    try:
        value = json.loads(identity_file.read_text(encoding="utf-8"))["gitSha"]
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
        value = os.getenv("RELEASE_SHA", "")
    value = str(value).strip().lower()
    if len(value) == 40 and all(character in "0123456789abcdef" for character in value):
        return value
    return "unknown"
