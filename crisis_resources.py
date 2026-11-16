"""
Country-specific crisis resources for the B2C ANTSABOT_COMPANION persona.

Background (feature/b2c-pivot code review). The companion's CRISIS PROTOCOL
told the model to "direct them to the country-specific crisis lines provided
to you in this conversation's context". Nothing in this service ever injected
those lines, and `get_system_prompt()` only appended context when the persona
had `has_db_access=True` (the companion is False) — so even an
API-supplied resource would have been silently dropped. For an unsupervised
B2C persona with no practitioner to escalate to, that left the model to
hallucinate phone numbers or defer vaguely.

This module renders the crisis lines for the configured regions (the contacts
themselves live in `regions.REGIONS`, the single source of truth) and owns the
service-controlled crisis-continuity rules appended to the companion system
prompt at runtime. The receiving end for the "crisis lines injected upstream"
contract lives HERE: even if the API never sends a country, the companion
falls back to the deployment's region (COUNTRY_CODE; `au` if unset) and always
has concrete resources to surface. Keeping the continuity rules here also
means a published persona prompt cannot remove the requirement to follow an
unresolved crisis across topic changes.
"""
from __future__ import annotations

from typing import List

from regions import (
    FALLBACK_COUNTRY_CODE,
    CrisisResource,
    get_region,
    resolve_country_code,
)

# Fixed fallback, used only when neither the request nor the deployment's
# COUNTRY_CODE setting names a configured region. Crisis contacts themselves
# live in regions.REGIONS (the single source of truth).
DEFAULT_COUNTRY_CODE = FALLBACK_COUNTRY_CODE

__all__ = [
    "DEFAULT_COUNTRY_CODE",
    "CrisisResource",
    "build_crisis_continuity_block",
    "build_crisis_resources_block",
    "get_crisis_resources",
    "normalize_country_code",
]


def normalize_country_code(country_code: str | None) -> str:
    """
    Map an inbound country code to a configured region key, falling back to
    the deployment's region (COUNTRY_CODE). Accepts mixed case and whitespace.
    """
    return resolve_country_code(country_code)


def get_crisis_resources(country_code: str | None) -> List[CrisisResource]:
    """Return the concrete crisis resources for a (possibly fuzzy) country code."""
    return list(get_region(country_code).crisis_resources)


def build_crisis_resources_block(country_code: str | None) -> str:
    """
    Render the crisis-resources block appended to the companion system prompt.

    The block is self-contained: it names the country it resolved to and lists
    concrete contacts, so the model never has to invent a number. All contact
    names come from the resolved region's config.
    """
    region = get_region(country_code)
    lines = "\n".join(r.render() for r in region.crisis_resources)
    crisis_line_names = "/".join(r.name for r in region.crisis_lines)
    return (
        "\n\n# CRISIS RESOURCES (use these exact contacts)\n"
        f"These are the crisis lines for the user's region ({region.code.upper()}). "
        "When the crisis protocol applies, surface these specific contacts — "
        "do NOT invent, guess, or substitute other numbers. If you are unsure "
        f"of the user's location, give the emergency number below and {crisis_line_names} "
        "as appropriate and suggest they confirm their local service.\n"
        f"{lines}"
    )


def build_crisis_continuity_block() -> str:
    """Keep an unresolved crisis active across later topic changes."""
    return (
        "\n\n# CRISIS CONTINUITY (higher priority than a topic change)\n"
        "Review the recent conversation, not only the latest message. After a "
        "user discloses current or recent suicidal thoughts, self-harm, intent "
        "to harm someone, or immediate danger, the crisis remains unresolved "
        "until the user explicitly confirms they are safe right now and an "
        "immediate real-world safety step is in place, or emergency/crisis "
        "support has taken over.\n"
        "- If the user changes the subject before then, do not treat the topic "
        "change as evidence that they are safe. Briefly acknowledge the new "
        "issue, then return to immediate safety and ask one direct safety "
        "question.\n"
        "- A practical obstacle such as \"I lost my phone\" is part of the "
        "safety response: suggest using another person's phone or going directly "
        "to a trusted person, staffed public place, emergency department, or "
        "emergency services. Do not switch to an unrelated recovery checklist.\n"
        "- Use calm, direct acknowledgement such as \"Thank you for telling "
        "me.\" Do not praise or celebrate the disclosure, and do not say \"I'm "
        "glad\" in response to it.\n"
        "- Write crisis replies in plain text. Do not use Markdown emphasis "
        "markers such as ** because the client chat displays them literally."
    )
