# Isolated LiteLLM rollout stack

This stack runs the reviewed request edge, the exact LiteLLM configuration,
Haystack source, Redis and a synthetic Nest API fixture in one Docker network
namespace. Only loopback ports are published. Haystack uses
`http://localhost:4000/v1`, which is permitted by its existing local URL rule;
the production URL validation is unchanged.

## Dependencies

- Docker with Compose v2 and enough space to build the pinned LiteLLM image.
- `bash`, `curl`, `git`, `openssl` and Python 3 on the host.
- Gateway source at `GATEWAY_SOURCE` (default:
  `/Users/alec/Projects/antsa/.worktrees/gateway-rollout-20261008`).
- Haystack source at `HAYSTACK_SOURCE` (defaults to the repository containing
  this directory).
- An OpenAI API credential supplied by the operator. It is the only external
  provider credential and is never committed or printed.

The stack performs real OpenAI inference only when `probe.sh` is run. Building,
starting and fixture tests do not call external models.

## Run

```bash
cd testing/llm-rollout
./prepare-credentials.sh
# Edit credentials.env and set OPENAI_API_KEY, then retain mode 600.
./run.sh
./probe.sh
./cleanup.sh
```

Override source trees when needed:

```bash
HAYSTACK_SOURCE=/absolute/haystack GATEWAY_SOURCE=/absolute/infra ./run.sh
```

`run.sh` labels images with each source HEAD and bakes the Haystack SHA into
`/health`. It refuses missing credentials, short/equal gateway keys, or a
credential file whose mode is not 600. `probe.sh` requires that exact SHA,
all eleven routes, the document agent, Redis and the pipeline to be ready. It
then tests the scoped transcript fixture and makes one strict-schema previous
session summary call through Haystack, edge, LiteLLM and OpenAI.

The fixture accepts only `synthetic-profile` / `synthetic-scoped-token` for
exploration endpoints and `HAYSTACK_WEBHOOK_SECRET` for persona configs and
callbacks. Its two transcript segments are hardcoded synthetic statements.
It has no database, cloud access or real client records.

Run fixture contract tests without Docker:

```bash
python3 -m unittest -v test_fixture_api.py
```

Inspect metadata-only request outcomes with:

```bash
docker compose -f compose.yaml logs edge haystack
```

