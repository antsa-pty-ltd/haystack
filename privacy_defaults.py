"""Process-wide privacy defaults. Import this before anything imports `haystack`.

haystack-ai sends anonymous usage telemetry to PostHog (eu.posthog.com) unless
HAYSTACK_TELEMETRY_ENABLED is false, and it reads that variable once, when
`haystack` is first imported. ANTSA processes health information, and PostHog
is not a subprocessor we disclose or have an agreement with, so telemetry is
always off, in every region, whatever the deployment's app settings say.

The deployment also sets HAYSTACK_TELEMETRY_ENABLED=False as an app setting;
this module makes the code safe on its own (local runs, tests, a region whose
settings were staged by hand).
"""

import os

TELEMETRY_ENV = "HAYSTACK_TELEMETRY_ENABLED"

# Forced, not setdefault: there is no configuration in which ANTSA should send
# usage telemetry to a third party.
os.environ[TELEMETRY_ENV] = "False"
