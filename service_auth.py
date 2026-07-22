"""Authentication helpers for privileged API <-> Haystack operations."""

import hmac
import os
from typing import Optional


def is_valid_service_secret(presented: Optional[str]) -> bool:
    """Fail closed and compare the shared service credential in constant time."""
    expected = os.getenv("HAYSTACK_WEBHOOK_SECRET")
    if not expected or not presented:
        return False
    return hmac.compare_digest(
        presented.encode("utf-8"), expected.encode("utf-8")
    )
