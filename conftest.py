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

if not os.environ.get("OPENAI_API_KEY"):
    os.environ["OPENAI_API_KEY"] = "sk-test-dummy-key"

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
