"""Pytest bootstrap — runs before any test module is collected/imported.

CI exports OPENAI_API_KEY as an empty string. `config.py` builds a module-level
`settings = Settings()` singleton whose `openai_api_key` is captured the moment
config.py is first imported (via main/tools/haystack_pipeline). The Haystack
generators are constructed with `Secret.from_token(settings.openai_api_key)`,
which raises "Authentication token cannot be empty" on a blank key.

A per-test-file guard is too late: the pre-existing test modules import the
settings chain during collection before any single test file's top-level code
runs. A rootdir conftest is imported by pytest before collection begins, so
setting a dummy key here guarantees a non-empty value before config.py loads.
No network call is made at construction time, so a dummy token is safe.
"""

import os

import privacy_defaults  # noqa: F401  (tests import haystack modules directly)

if not os.environ.get("OPENAI_API_KEY"):
    os.environ["OPENAI_API_KEY"] = "sk-test-dummy-key"

# Region-dependent text (crisis lines, persona wording, default timezone) is
# resolved from COUNTRY_CODE. Start every run from the unset state (the AU
# fallback) so a developer's shell cannot change results; tests that need a
# region set it with monkeypatch.
os.environ.pop("COUNTRY_CODE", None)

import pytest

from llm_routing import router_registry  # noqa: E402


@pytest.fixture(autouse=True)
def isolate_router_registry():
    """Keep tests isolated from import-time router registration.

    Unit tests that import main (e.g. the mobile-api bridge tests) trigger the
    production startup wiring, which populates the shared module-level
    ``router_registry`` with real, dummy-keyed gateway/direct clients. Without
    this fixture those entries leak into unrelated test files and the
    registry-first call sites (document draft, language repair, conversation
    summary) bypass their injected mock clients and hit the network. Clear
    before and after every test so injected clients always win in tests; the
    real process re-registers at startup.
    """
    router_registry.clear()
    yield
    router_registry.clear()


# A made-up region for tests. Tests prove region behaviour against this entry,
# never against a real country's config, so changing a real region's copy
# cannot silently rewrite what the tests assert.
TEST_REGION_CODE = "zz"


@pytest.fixture
def test_region(monkeypatch):
    """Register the made-up ``zz`` region for the duration of one test."""
    from regions import CRISIS_LINE, EMERGENCY, REGIONS, CrisisResource, Region, validate_region

    region = Region(
        code=TEST_REGION_CODE,
        language_variety="Testland English",
        default_timezone="Pacific/Chatham",
        crisis_resources=(
            CrisisResource("Testland Emergency", "555", "immediate danger", kind=EMERGENCY),
            CrisisResource("Testland Helpline", "0100 200 300", "24/7 crisis support", kind=CRISIS_LINE),
            CrisisResource("Testland Textline", "text TEST to 4000", "24/7", kind=CRISIS_LINE),
            CrisisResource("Testland Peer Support", "0100 999 888"),
        ),
    )
    validate_region(region)
    monkeypatch.setitem(REGIONS, TEST_REGION_CODE, region)
    return region
