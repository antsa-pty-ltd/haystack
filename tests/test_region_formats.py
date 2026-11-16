"""
Region date formats and region-neutral tool descriptions.

Behaviour is proven against the made-up ``zz`` region (conftest.py), whose
year-first templates no real country uses, so a hard-coded order cannot pass.
AU output is pinned to the exact strings Haystack produced before date
formats moved into region config.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import sys
from dataclasses import replace
from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import tools as tools_module  # noqa: E402
from regions import REGIONS, DateFormats, format_date, get_region, validate_region  # noqa: E402
from tools import tool_manager  # noqa: E402

MOMENT = datetime(2025, 3, 4, 9, 5)  # Tuesday 4 March 2025


# --- format_date --------------------------------------------------------------

def test_au_date_formats_unchanged():
    au = REGIONS["au"]
    assert au.locale == "en-AU"
    assert format_date(MOMENT, "numeric", au) == "04/03/2025"
    assert format_date(MOMENT, "long", au) == "Tuesday 4 March 2025"
    assert format_date(MOMENT, "weekday_day_month", au) == "Tuesday 4 March"
    assert format_date(MOMENT, "day_month_year", au) == "4 March 2025"


def test_deployment_region_is_the_default(monkeypatch):
    assert format_date(MOMENT) == "04/03/2025"  # COUNTRY_CODE unset -> AU fallback
    monkeypatch.setenv("COUNTRY_CODE", "us")
    assert format_date(MOMENT) == "03/04/2025"
    assert format_date(MOMENT, "long") == "Tuesday, March 4, 2025"


def test_formats_come_from_region_config(test_region, monkeypatch):
    monkeypatch.setenv("COUNTRY_CODE", "zz")
    assert get_region().locale == "en-ZZ"
    assert format_date(MOMENT) == "2025.03.04"
    assert format_date(MOMENT, "long") == "2025 March 4 (Tuesday)"
    assert format_date(MOMENT, "weekday_day_month") == "March 4 (Tuesday)"
    assert format_date(date(2025, 3, 4), "day_month_year") == "2025 March 4"


def test_unknown_style_is_rejected():
    with pytest.raises(ValueError):
        format_date(MOMENT, "shortish")


@pytest.mark.parametrize("template", ["", "{day}/{month}/{yr}", "{weekday!r}"])
def test_invalid_date_template_is_rejected(test_region, template):
    bad = replace(test_region, date_formats=replace(test_region.date_formats, numeric=template))
    with pytest.raises(ValueError):
        validate_region(bad)


def test_blank_locale_is_rejected(test_region):
    with pytest.raises(ValueError):
        validate_region(replace(test_region, locale=" "))


def test_every_configured_region_has_complete_formats():
    for region in REGIONS.values():
        assert isinstance(region.date_formats, DateFormats)
        validate_region(region)


# --- call sites ---------------------------------------------------------------

def _api(monkeypatch, routes):
    async def fake(method, endpoint, data=None, params=None):
        return routes[endpoint.lstrip("/")]

    monkeypatch.setattr(tool_manager, "_make_api_request", fake)


def _search_label(monkeypatch, timezone):
    tool_manager.set_page_context({"timezone": timezone})
    _api(monkeypatch, {"haystack/search-sessions": {"total": 1, "sessions": [{
        "id": "t", "sessionId": "r", "clientId": "c", "clientName": "Sam",
        "recordingDate": "2026-11-14T05:57:05.345Z",
    }]}})
    result = asyncio.run(tool_manager._search_sessions(client_id="c"))
    return result["sessions"][0]["recording_date_label"]


def test_session_label_au_unchanged(monkeypatch):
    assert _search_label(monkeypatch, "Australia/Sydney") == "Saturday 14 November 2026, 4:57 pm"


def test_session_label_follows_region(test_region, monkeypatch):
    monkeypatch.setenv("COUNTRY_CODE", "zz")
    assert _search_label(monkeypatch, "UTC") == "2026 November 14 (Saturday), 5:57 am"


def _time_block(monkeypatch, timezone):
    import haystack_pipeline

    instant = datetime(2026, 11, 16, 8, 15, tzinfo=ZoneInfo(timezone))

    class Frozen(datetime):
        @classmethod
        def now(cls, tz=None):
            return instant.astimezone(tz) if tz else instant.replace(tzinfo=None)

    monkeypatch.setattr(haystack_pipeline, "datetime", Frozen)
    return haystack_pipeline.build_current_time_block(timezone)


def test_time_block_au_unchanged(monkeypatch):
    block = _time_block(monkeypatch, "Australia/Sydney")
    assert "- Date: Monday 16 November 2026\n- Time: 8:15 am (Australia/Sydney)\n" in block


def test_time_block_follows_region(test_region, monkeypatch):
    monkeypatch.setenv("COUNTRY_CODE", "zz")
    block = _time_block(monkeypatch, "Pacific/Chatham")
    assert "- Date: 2026 November 16 (Monday)\n" in block


def test_day_label_follows_region(test_region, monkeypatch):
    assert tools_module.ToolManager._day_label(MOMENT) == "Tuesday 4 March"
    monkeypatch.setenv("COUNTRY_CODE", "zz")
    assert tools_module.ToolManager._day_label(MOMENT) == "March 4 (Tuesday)"


# --- tool descriptions ----------------------------------------------------------

def test_tool_descriptions_name_no_country():
    text = json.dumps([tool["definition"] for tool in tool_manager.tools.values()])
    for pattern in (r"Australia", r"outback", r"en-AU", r"\bAUD\b", r"\+61"):
        assert not re.search(pattern, text), pattern
