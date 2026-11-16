"""Haystack must never send usage telemetry to PostHog, in any region."""

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _run(code: str, env_overrides: dict) -> str:
    env = {k: v for k, v in os.environ.items() if k != "HAYSTACK_TELEMETRY_ENABLED"}
    env.update(env_overrides)
    env.setdefault("OPENAI_API_KEY", "sk-test-dummy-key")
    result = subprocess.run(
        [sys.executable, "-c", code], cwd=ROOT, env=env, capture_output=True, text=True, timeout=120
    )
    assert result.returncode == 0, result.stderr
    return result.stdout.strip()


PROBE = "from haystack.telemetry import _telemetry; print(_telemetry.telemetry is None)"


def test_haystack_telemetry_is_off_when_the_app_is_imported():
    # A fresh interpreter with no setting at all: importing the app must be enough.
    assert _run("import main; " + PROBE, {}) == "True"


def test_every_module_that_imports_haystack_disables_telemetry_first():
    for module in ["routed_generator", "haystack_pipeline", "components.ui_actions", "agents.document_agent"]:
        assert _run(f"import {module}; " + PROBE, {}) == "True", module


def test_an_app_setting_cannot_turn_telemetry_back_on():
    assert _run("import main; " + PROBE, {"HAYSTACK_TELEMETRY_ENABLED": "True"}) == "True"


def test_deploy_paths_also_set_the_variable():
    assert "HAYSTACK_TELEMETRY_ENABLED=False" in (ROOT / "startup.sh").read_text()
    assert "HAYSTACK_TELEMETRY_ENABLED=False" in (ROOT / "Dockerfile").read_text()
