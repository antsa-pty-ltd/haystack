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

This module owns the concrete crisis lines for the supported countries
(AU/US/UK — see root CLAUDE.md "Multi-country") and the service-controlled
crisis-continuity rules appended to the companion system prompt at runtime.
The receiving end for the "crisis lines injected upstream" contract now lives
HERE: even if the API never sends a country, the companion falls back to the
platform default (`au`) and always has concrete resources to surface. Keeping
the continuity rules here also means a published persona prompt cannot remove
the requirement to follow an unresolved crisis across topic changes.
"""
from __future__ import annotations

from typing import Dict, List

# Platform default country (root CLAUDE.md: frontend detection order ends in
# "default au"). Used whenever no country code can be resolved from the request.
DEFAULT_COUNTRY_CODE = "au"


class CrisisResource:
    """A single named crisis contact for a country."""

    def __init__(self, name: str, contact: str, note: str = ""):
        self.name = name
        self.contact = contact
        self.note = note

    def render(self) -> str:
        line = f"- {self.name}: {self.contact}"
        if self.note:
            line += f" ({self.note})"
        return line


# Concrete, well-known crisis resources per supported country. These are
# deliberately hard-coded here rather than relying on an upstream context
# channel, so the companion can never be left without numbers to surface.
CRISIS_RESOURCES: Dict[str, List[CrisisResource]] = {
    "au": [
        CrisisResource("Emergency services", "000", "immediate danger"),
        CrisisResource("Lifeline", "13 11 14", "24/7 crisis support"),
        CrisisResource("Suicide Call Back Service", "1300 659 467", "24/7"),
        CrisisResource("Beyond Blue", "1300 22 4636", "24/7"),
        CrisisResource("13YARN", "13 92 76", "24/7 support for Aboriginal and Torres Strait Islander people"),
    ],
    "us": [
        CrisisResource("Emergency services", "911", "immediate danger"),
        CrisisResource("988 Suicide & Crisis Lifeline", "988", "call or text, 24/7"),
        CrisisResource("Crisis Text Line", "text HOME to 741741", "24/7"),
    ],
    "uk": [
        CrisisResource("Emergency services", "999", "immediate danger"),
        CrisisResource("Samaritans", "116 123", "free, 24/7"),
        CrisisResource("Shout", "text SHOUT to 85258", "24/7"),
    ],
}


def normalize_country_code(country_code: str | None) -> str:
    """
    Map an inbound country code to a supported key, falling back to the
    platform default. Accepts mixed case and surrounding whitespace.
    """
    if not country_code:
        return DEFAULT_COUNTRY_CODE
    normalized = country_code.strip().lower()
    if normalized in CRISIS_RESOURCES:
        return normalized
    return DEFAULT_COUNTRY_CODE


def get_crisis_resources(country_code: str | None) -> List[CrisisResource]:
    """Return the concrete crisis resources for a (possibly fuzzy) country code."""
    return CRISIS_RESOURCES[normalize_country_code(country_code)]


def build_crisis_resources_block(country_code: str | None) -> str:
    """
    Render the crisis-resources block appended to the companion system prompt.

    The block is self-contained: it names the country it resolved to and lists
    concrete contacts, so the model never has to invent a number.
    """
    resolved = normalize_country_code(country_code)
    resources = CRISIS_RESOURCES[resolved]
    lines = "\n".join(r.render() for r in resources)
    return (
        "\n\n# CRISIS RESOURCES (use these exact contacts)\n"
        f"These are the crisis lines for the user's region ({resolved.upper()}). "
        "When the crisis protocol applies, surface these specific contacts — "
        "do NOT invent, guess, or substitute other numbers. If you are unsure "
        "of the user's location, give the emergency number below and Lifeline/"
        "Samaritans/988 as appropriate and suggest they confirm their local "
        "service.\n"
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
