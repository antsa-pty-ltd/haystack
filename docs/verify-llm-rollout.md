# Haystack LiteLLM rollout verifier

`scripts/verify-llm-rollout.py` is a bounded, payload-safe canary runner for use
inside the Azure Haystack private-network worker. It makes no call unless
`--execute` is present. It prints only stable coverage labels, outcome, elapsed
milliseconds and sanitized failure categories. It never prints URLs, aliases,
credentials, generated text, request payloads or fixture IDs.

## Evidence layers

Gateway-direct probes prove private DNS/TLS connectivity, the Haystack virtual
key's alias scope and basic completion contracts. They do **not** prove an
application endpoint, parsing, persistence, tools or the user-visible result.

Haystack-application probes exercise the deployed FastAPI routes and streaming
pipeline with synthetic content. They prove Haystack product contracts but do
not, by themselves, prove the public Nest API controller, Bull persistence or
API readback. The rollout evidence must combine these results with the
authenticated API canaries below.

## Environment

Gateway mode reads:

- `LLM_GATEWAY_BASE_URL` (HTTPS and ending in `/v1`)
- `HAYSTACK_LLM_GATEWAY_API_KEY`
- all eleven `HAYSTACK_LITELLM_MODEL_<STEM>_OPENAI` variables, or the matching
  `_FOUNDRY` variables with `--route foundry`

Application mode reads:

- `ROLL_OUT_HAYSTACK_BASE_URL`
- `ROLL_OUT_API_BEARER_TOKEN` for an approved disposable test identity
- `ROLL_OUT_SYNTHETIC_PROFILE_ID` for that same identity
- `HAYSTACK_WEBHOOK_SECRET`
- optional `ROLL_OUT_DOCUMENT_SESSION_IDS`, a comma-separated set of approved
  synthetic transcript IDs which the document agent may retrieve through its
  real tools. Without it the tool-enabled document-agent row is reported SKIP.

Keep these in the worker's existing secret environment. Do not pass secrets on
the command line or capture the process environment in evidence.

```bash
python3 scripts/verify-llm-rollout.py --mode gateway --route openai --execute
python3 scripts/verify-llm-rollout.py --mode application --execute
python3 scripts/verify-llm-rollout.py --mode all --route openai --execute
```

Document calls default to 180 seconds; all other calls default to 45 seconds.
Use `--document-timeout` and `--timeout` only to apply a smaller known endpoint
budget. A timeout is a failure; the runner does not retry and cannot duplicate
a tool action.

The blocked-policy canary is disabled by default because the current Haystack
endpoint posts a policy-violation record back to the API. Run it only against an
approved disposable fixture with `--allow-policy-write`. Policy provider
failure/malformed JSON fail-open must be tested with isolated fault injection,
not by breaking a shared live provider.

## Coverage and remaining API proof

| Workload | Gateway probe | Haystack application proof | Required authenticated API proof after shipment |
| --- | --- | --- | --- |
| `previous_session_summary` | strict JSON support | `/previous-session-summary`, exact six fields | Complete a disposable transcript, observe Bull retry behaviour, exactly one durable row and API readback |
| `conversation_summary` | completion | `/summarize-ai-conversations`, content and metadata | `POST /api/v1/ai/summarize-ai-conversations-haystack` using approved conversation IDs |
| `document_language` | completion | generated English fixture containing unexpected Devanagari | API document job: assert repair, quotes/tokens, 422 and no saved error document under injected empty/failure |
| `document_policy` | JSON completion | allowed template; blocked template only with write flag | API document job for allowed/blocked disposable templates; correlate observable malformed/provider-failure fail-open |
| `document_draft` | completion | initial draft plus explicit 50% shortening refinement | Verify exactly one saved result for each job and provider-failure cleanup |
| `document_agent` | tools request contract | real exploration only when approved transcript IDs are supplied | API document job with synthetic transcript ownership, callback auth, bounded tools and no duplicate output |
| `chat` | completion | every persona, two turns, response DTO | Authenticated public chat flow for every published persona, ownership rejection and persisted history |
| `web_assistant` | completion | private API-style WebSocket bridge, ordered chunks and terminal event | Browser/API bridge with a reversible no-side-effect tool/UI action, hot reload and one persisted reply |
| `therapist` | completion | private API-style WebSocket bridge, ordered chunks and terminal event | Clinical-owner-approved synthetic safety cases, history, hot reload and one reply |
| `companion` | completion | private API-style WebSocket bridge, ordered chunks and terminal event | Product-approved synthetic resource cases, history, hot reload and one reply without duplicate tool effect |
| `transcriber` | completion | private API-style WebSocket bridge, ordered chunks and terminal event | Approved long synthetic transcript/template flow, retry and no duplicate output |

The public API rows depend on fixture references and identity metadata from the
release owner. Fixture identifiers must remain in the secret environment and
must not be copied into terminal output or rollout evidence. Real client or
clinical records are out of scope.

## Local verification

```bash
python3 -m unittest -v tests.test_verify_llm_rollout
```

The isolated tests cover all eleven gateway aliases, explicit live-call
acknowledgement, secret/body redaction, deterministic synthetic document
fixtures, stream completion, terminal failure and timeout.
