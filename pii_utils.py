"""
PII Utilities for the Haystack service.

Since the NestJS backend now sends tokenized data (with [CLIENT_NAME], [PRACTITIONER_NAME]
placeholders), the Haystack service primarily needs:
1. Log sanitization — ensure PII never appears in log output
2. Defensive tokenization — catch any PII that slipped through
"""

import re
import logging
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


def sanitize_for_logging(text: str, sensitive_values: Optional[List[str]] = None) -> str:
    """
    Remove or mask PII from text before logging.

    Args:
        text: The text to sanitize
        sensitive_values: Optional list of known sensitive values to mask

    Returns:
        Sanitized text safe for logging
    """
    if not text:
        return text

    sanitized = text

    # Mask any explicitly provided sensitive values
    if sensitive_values:
        for value in sensitive_values:
            if value and len(value) > 1:
                sanitized = sanitized.replace(value, "[REDACTED]")

    return sanitized


def sanitize_dict_for_logging(data: dict, sensitive_keys: Optional[List[str]] = None) -> dict:
    """
    Create a log-safe copy of a dictionary by redacting sensitive keys.

    Args:
        data: Dictionary to sanitize
        sensitive_keys: Keys whose values should be redacted.
                       Defaults to common PII field names.

    Returns:
        New dictionary with sensitive values redacted
    """
    if not data:
        return data

    if sensitive_keys is None:
        sensitive_keys = [
            "name", "firstName", "lastName", "first_name", "last_name",
            "email", "phone", "address", "dob", "date_of_birth",
            "occupation", "provider_number", "providerNumber",
        ]

    result = {}
    for key, value in data.items():
        if key.lower() in [k.lower() for k in sensitive_keys]:
            result[key] = "[REDACTED]"
        elif isinstance(value, dict):
            result[key] = sanitize_dict_for_logging(value, sensitive_keys)
        elif isinstance(value, list) and len(value) > 0 and isinstance(value[0], dict):
            result[key] = [sanitize_dict_for_logging(item, sensitive_keys) if isinstance(item, dict) else item for item in value]
        else:
            result[key] = value

    return result


def is_tokenized(text: str) -> bool:
    """
    Check if text contains PII tokens (indicating it's already been tokenized).

    Returns True if the text contains patterns like [CLIENT_NAME], [PRACTITIONER_NAME], etc.
    """
    if not text:
        return False
    return bool(re.search(r'\[[A-Z_]+(?:_\d+)?\]', text))
