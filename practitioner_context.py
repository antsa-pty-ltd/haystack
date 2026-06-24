"""
Practitioner-context injection for ANTSABOT_THERAPIST and ANTSABOT_COMPANION.

The ANTSAbot personas previously gave generic "speak to a professional" advice
regardless of whether the client had an active practitioner on the platform.
This module resolves the client's practitioner (if any) via the NestJS API and
renders a prompt block so the model can name the practitioner rather than
giving vague guidance.

Pattern follows crisis_resources.py — a self-contained module that builds a
prompt block appended to the system prompt at runtime.
"""
from __future__ import annotations

import logging
import os
from typing import Any, Dict, Optional

import httpx

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Prompt block builder
# ---------------------------------------------------------------------------


def build_practitioner_context_block(practitioner_info: Optional[Dict[str, Any]]) -> str:
    """
    Render the practitioner-context block appended to the companion/therapist
    system prompt.

    Args:
        practitioner_info: Dict from the API endpoint with keys:
            - hasPractitioner (bool)
            - firstName (str) — practitioner's first name
            - practitionerType (str) — e.g. "Psychologist"
            - isB2c (bool) — whether the client came via B2C signup
        Or None if the lookup failed / was skipped.
    """
    if practitioner_info is None or not practitioner_info.get("hasPractitioner"):
        # Scenario C: no practitioner
        return (
            "\n\n# PRACTITIONER CONTEXT\n"
            "This user does not currently have a practitioner on ANTSA.\n"
            "When suggesting professional support, mention they can use the "
            "\"Connect with a practitioner\" option in the app to find support "
            "through ANTSA.\n"
            "Do NOT claim that a practitioner or care team is monitoring this "
            "conversation — none exists.\n"
            "In crisis situations, ALWAYS surface the crisis resources listed "
            "above."
        )

    first_name = practitioner_info.get("firstName", "their practitioner")
    pract_type = practitioner_info.get("practitionerType") or "practitioner"
    is_b2c = practitioner_info.get("isB2c", False)

    if is_b2c:
        # Scenario B: B2C client who has connected with a practitioner
        return (
            "\n\n# PRACTITIONER CONTEXT\n"
            f"This user has connected with {first_name}, a {pract_type} on "
            "ANTSA.\n"
            f"When suggesting professional support, mention {first_name} by "
            "name as someone they can reach out to through the app.\n"
            f'Example: "You might find it helpful to talk to {first_name}, '
            f'your {pract_type} on ANTSA, about what you\'re going through."\n'
            "In crisis situations, ALWAYS surface the crisis resources listed "
            f"above first, then also suggest reaching out to {first_name} as "
            "a follow-up once immediate safety is addressed."
        )

    # Scenario A: B2B — practitioner-assigned chat
    return (
        "\n\n# PRACTITIONER CONTEXT\n"
        f"This user is working with {first_name}, their {pract_type}.\n"
        f"When suggesting professional support, refer to {first_name} by "
        "name rather than giving generic \"speak to a professional\" advice.\n"
        f'Example: "I\'d encourage you to talk to {first_name}, your '
        f'{pract_type}, about this."\n'
        "In crisis situations, ALWAYS surface the crisis resources listed "
        f"above first, then also suggest contacting {first_name} as a "
        "follow-up once immediate safety is addressed."
    )


# ---------------------------------------------------------------------------
# API fetch
# ---------------------------------------------------------------------------


async def fetch_practitioner_context(
    auth_token: str,
    api_base_url: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """
    Fetch the authenticated client's practitioner context from the NestJS API.

    Returns the JSON payload from GET /api/v1/gpt/client/practitioner-context,
    or None on any failure (network, auth, 404, etc.).
    """
    base = api_base_url or os.getenv("NESTJS_API_URL", "http://localhost:8080")
    url = f"{base}/api/v1/gpt/client/practitioner-context"

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(
                url,
                headers={
                    "Authorization": f"Bearer {auth_token}",
                    "Content-Type": "application/json",
                },
            )
            if resp.status_code == 200:
                return resp.json()
            logger.warning(
                "practitioner-context API returned %d: %s",
                resp.status_code,
                resp.text[:200],
            )
            return None
    except Exception as exc:
        logger.warning("practitioner-context fetch failed: %s", exc)
        return None
