"""
Per-country region configuration: the single source of truth for everything
Haystack says or assumes that differs between countries.

ANTSA runs one isolated deployment per country; each Haystack app has the
``COUNTRY_CODE`` app setting (``au``, ``us``, ...). Region differences are
data in ``REGIONS`` below, never ``if country == ...`` branches in code:

- ``language_variety`` — the English variety personas and generated documents
  write in (rendered into prompts via the ``${language_variety}`` placeholder).
- ``default_timezone`` — the IANA timezone used for schedule maths when neither
  the browser nor the service configuration supplies one.
- ``locale`` — the BCP 47 locale of the region (``en-AU``, ``en-US``, ...).
- ``date_formats`` — how dates are written for this region (day-first or
  month-first, separators). Every human-readable date goes through
  ``format_date`` so no call site hard-codes an order.
- ``crisis_resources`` — the concrete crisis contacts surfaced to users. Each
  region needs exactly one ``EMERGENCY`` contact and at least one
  ``CRISIS_LINE``; this is checked at import so a bad entry fails the deploy
  rather than a person in crisis.

Adding a country is a config change only: add an entry to ``REGIONS`` (and an
alias to ``COUNTRY_ALIASES`` if it has other common codes), then set
``COUNTRY_CODE`` on that deployment's Haystack app.

Resolution order for "which region applies":
1. a supported country code carried on the request (e.g. the B2C companion's
   ``country_code`` context),
2. the deployment's ``COUNTRY_CODE`` setting,
3. ``FALLBACK_COUNTRY_CODE`` (``au``) — only when ``COUNTRY_CODE`` is unset or
   unsupported, which keeps the pre-region behaviour of the AU deployment.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, fields
from datetime import date, datetime
from typing import Dict, Mapping, Optional, Tuple, Union

# Used only when the deployment's COUNTRY_CODE is unset or not in REGIONS.
FALLBACK_COUNTRY_CODE = "au"

# App setting naming the deployment's region.
COUNTRY_CODE_SETTING = "COUNTRY_CODE"

# Kinds of crisis contact. A region must have exactly one EMERGENCY contact and
# at least one CRISIS_LINE (named in the "unsure of location" guidance).
EMERGENCY = "emergency"
CRISIS_LINE = "crisis_line"
SUPPORT = "support"
_CONTACT_KINDS = (EMERGENCY, CRISIS_LINE, SUPPORT)


@dataclass(frozen=True)
class CrisisResource:
    """A single named crisis contact for a country."""

    name: str
    contact: str
    note: str = ""
    kind: str = SUPPORT

    def render(self) -> str:
        line = f"- {self.name}: {self.contact}"
        if self.note:
            line += f" ({self.note})"
        return line


# Tokens available in a date template. Names come from strftime (%A, %B) so
# they follow the process locale exactly as before.
DATE_TOKENS = ("weekday", "day", "dd", "month", "mm", "year")
_DATE_TOKEN = re.compile(r"\{([^{}]*)\}")


@dataclass(frozen=True)
class DateFormats:
    """
    Date templates for a region, written with ``{token}`` placeholders from
    ``DATE_TOKENS``: ``weekday`` (Monday), ``day`` (3), ``dd`` (03),
    ``month`` (March), ``mm`` (03), ``year`` (2025).
    """

    numeric: str  # e.g. 03/03/2025
    long: str  # weekday, day, month and year
    weekday_day_month: str  # weekday, day and month (no year)
    day_month_year: str  # day, month and year (no weekday)


@dataclass(frozen=True)
class Region:
    """Everything that differs between country deployments."""

    code: str
    language_variety: str
    default_timezone: str
    crisis_resources: Tuple[CrisisResource, ...]
    locale: str
    date_formats: DateFormats

    @property
    def emergency_contact(self) -> CrisisResource:
        return next(r for r in self.crisis_resources if r.kind == EMERGENCY)

    @property
    def crisis_lines(self) -> Tuple[CrisisResource, ...]:
        return tuple(r for r in self.crisis_resources if r.kind == CRISIS_LINE)

    def text_values(self) -> Dict[str, str]:
        """Placeholder values available to region-rendered prompt text."""
        return {"language_variety": self.language_variety}


# Concrete, well-known crisis resources per supported country. These are
# deliberately held here rather than relying on an upstream context channel,
# so the companion can never be left without numbers to surface.
REGIONS: Dict[str, Region] = {
    "au": Region(
        code="au",
        language_variety="Australian English",
        default_timezone="Australia/Sydney",
        locale="en-AU",
        date_formats=DateFormats(
            numeric="{dd}/{mm}/{year}",
            long="{weekday} {day} {month} {year}",
            weekday_day_month="{weekday} {day} {month}",
            day_month_year="{day} {month} {year}",
        ),
        crisis_resources=(
            CrisisResource("Emergency services", "000", "immediate danger", kind=EMERGENCY),
            CrisisResource("Lifeline", "13 11 14", "24/7 crisis support", kind=CRISIS_LINE),
            CrisisResource("Suicide Call Back Service", "1300 659 467", "24/7"),
            CrisisResource("Beyond Blue", "1300 22 4636", "24/7"),
            CrisisResource("13YARN", "13 92 76", "24/7 support for Aboriginal and Torres Strait Islander people"),
        ),
    ),
    "us": Region(
        code="us",
        language_variety="American English",
        default_timezone="America/New_York",
        locale="en-US",
        date_formats=DateFormats(
            numeric="{mm}/{dd}/{year}",
            long="{weekday}, {month} {day}, {year}",
            weekday_day_month="{weekday}, {month} {day}",
            day_month_year="{month} {day}, {year}",
        ),
        crisis_resources=(
            CrisisResource("Emergency services", "911", "immediate danger", kind=EMERGENCY),
            CrisisResource("988 Suicide & Crisis Lifeline", "call or text 988", "24/7 crisis support", kind=CRISIS_LINE),
            CrisisResource("Crisis Text Line", "text HOME to 741741", "24/7"),
        ),
    ),
    "uk": Region(
        code="uk",
        language_variety="British English",
        default_timezone="Europe/London",
        locale="en-GB",
        date_formats=DateFormats(
            numeric="{dd}/{mm}/{year}",
            long="{weekday} {day} {month} {year}",
            weekday_day_month="{weekday} {day} {month}",
            day_month_year="{day} {month} {year}",
        ),
        crisis_resources=(
            CrisisResource("Emergency services", "999", "immediate danger", kind=EMERGENCY),
            CrisisResource("Samaritans", "116 123", "free, 24/7", kind=CRISIS_LINE),
            CrisisResource("Shout", "text SHOUT to 85258", "24/7"),
        ),
    ),
}

# Other common codes for a configured region.
COUNTRY_ALIASES: Dict[str, str] = {"gb": "uk"}


def validate_region(region: Region) -> None:
    """Raise ValueError if a region entry is unsafe or incomplete."""
    if not region.language_variety.strip():
        raise ValueError(f"Region {region.code!r} has no language_variety")
    if not region.default_timezone.strip():
        raise ValueError(f"Region {region.code!r} has no default_timezone")
    if not region.locale.strip():
        raise ValueError(f"Region {region.code!r} has no locale")
    for field in fields(DateFormats):
        template = getattr(region.date_formats, field.name)
        unknown = set(_DATE_TOKEN.findall(template)) - set(DATE_TOKENS)
        if not template.strip() or unknown:
            raise ValueError(
                f"Region {region.code!r} has an invalid {field.name} date format {template!r}"
            )
    for resource in region.crisis_resources:
        if resource.kind not in _CONTACT_KINDS:
            raise ValueError(f"Region {region.code!r} has unknown contact kind {resource.kind!r}")
        if not resource.name.strip() or not resource.contact.strip():
            raise ValueError(f"Region {region.code!r} has a blank crisis contact")
    emergencies = [r for r in region.crisis_resources if r.kind == EMERGENCY]
    if len(emergencies) != 1:
        raise ValueError(f"Region {region.code!r} needs exactly one emergency contact")
    if not region.crisis_lines:
        raise ValueError(f"Region {region.code!r} needs at least one crisis line")


def _validate_regions(regions: Mapping[str, Region]) -> None:
    if FALLBACK_COUNTRY_CODE not in regions:
        raise ValueError("The fallback region must be configured")
    for code, region in regions.items():
        if code != region.code:
            raise ValueError(f"Region key {code!r} does not match its code {region.code!r}")
        validate_region(region)


_validate_regions(REGIONS)


def _supported_code(country_code: Optional[str]) -> Optional[str]:
    if not country_code or not isinstance(country_code, str):
        return None
    normalized = country_code.strip().lower()
    normalized = COUNTRY_ALIASES.get(normalized, normalized)
    return normalized if normalized in REGIONS else None


def configured_country_code() -> Optional[str]:
    """The region named by COUNTRY_CODE, or None if it is unset or unsupported."""
    return _supported_code(os.environ.get(COUNTRY_CODE_SETTING))


def deployment_country_code() -> str:
    """The deployment's region: COUNTRY_CODE, else the fixed fallback."""
    return configured_country_code() or FALLBACK_COUNTRY_CODE


def resolve_country_code(country_code: Optional[str] = None) -> str:
    """
    Map a (possibly fuzzy or missing) country code to a configured region key.
    A supported request code wins; otherwise the deployment's region applies.
    """
    return _supported_code(country_code) or deployment_country_code()


def get_region(country_code: Optional[str] = None) -> Region:
    """The region for a request code, defaulting to the deployment's region."""
    return REGIONS[resolve_country_code(country_code)]


_PLACEHOLDER = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")


def render_region_text(text: str, region: Region) -> str:
    """
    Fill ``${placeholder}`` tokens in prompt text from the region config.
    Only the ``${name}`` form is a placeholder, so a bare ``$`` (e.g. a price)
    is left alone. Strict: an unknown placeholder raises rather than shipping
    a raw token to the model.
    """
    values = region.text_values()

    def fill(match: "re.Match[str]") -> str:
        key = match.group(1)
        if key not in values:
            raise KeyError(f"Unknown region placeholder ${{{key}}}")
        return values[key]

    return _PLACEHOLDER.sub(fill, text)


DateStyle = str  # one of the DateFormats field names


def format_date(
    moment: Union[date, datetime],
    style: DateStyle = "numeric",
    region: Optional[Region] = None,
) -> str:
    """
    Write a date the way the region writes it. ``style`` names a
    ``DateFormats`` field; ``region`` defaults to the deployment's region.
    The caller converts ``moment`` to the right time zone first.
    """
    formats = (region or get_region()).date_formats
    if style not in {f.name for f in fields(DateFormats)}:
        raise ValueError(f"Unknown date style {style!r}")
    template = getattr(formats, style)
    return template.format(
        weekday=moment.strftime("%A"),
        day=moment.day,
        dd=f"{moment.day:02d}",
        month=moment.strftime("%B"),
        mm=f"{moment.month:02d}",
        year=moment.year,
    )
