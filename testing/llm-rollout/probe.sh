#!/usr/bin/env bash
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
credentials="$here/credentials.env"
set -a
# shellcheck disable=SC1090
source "$credentials"
set +a
expected_sha="$(git -C "${HAYSTACK_SOURCE:-$(cd "$here/../.." && pwd)}" rev-parse HEAD)"

deadline=$((SECONDS + 300))
while (( SECONDS < deadline )); do
  fixture="$(curl -fsS --max-time 5 http://127.0.0.1:18080/health || true)"
  gateway_status="$(curl -sS -o /dev/null -w '%{http_code}' --max-time 5 http://127.0.0.1:14000/health/liveliness || true)"
  health="$(curl -fsS --max-time 5 http://127.0.0.1:18001/health || true)"
  if [[ "$gateway_status" == 200 ]] && python3 - "$fixture" "$health" "$expected_sha" <<'PY'
import json, sys
fixture, health, expected = json.loads(sys.argv[1]), json.loads(sys.argv[2]), sys.argv[3]
ok = fixture.get("status") == "ready" and all((
    health.get("status") == "healthy",
    health.get("pipeline") == "ready",
    health.get("redis") == "ready",
    health.get("llmRoutes") == "ready",
    health.get("documentAgent") == "ready",
    health.get("releaseSha") == expected,
    health.get("openai") == "disabled",
))
raise SystemExit(0 if ok else 1)
PY
  then
    break
  fi
  sleep 5
done
(( SECONDS < deadline )) || { echo "Stack did not become ready within five minutes" >&2; exit 1; }

curl -fsS http://127.0.0.1:18080/api/v1/ai/transcripts/segments-by-sessions \
  -H 'Content-Type: application/json' \
  -H 'Authorization: Bearer synthetic-scoped-token' \
  -H 'ProfileID: synthetic-profile' \
  --data '{"session_ids":["session-synthetic-1"],"limit_per_session":1000}' \
  | python3 -c 'import json,sys; value=json.load(sys.stdin); assert len(value["segments"]) == 2'

# One real model call through Haystack -> edge -> LiteLLM -> OpenAI.
curl -fsS http://127.0.0.1:18001/previous-session-summary \
  -H 'Content-Type: application/json' \
  -H "X-Haystack-Secret: $HAYSTACK_WEBHOOK_SECRET" \
  --data '{"sessionId":"session-synthetic-1","transcript":"Practitioner: We practised paced breathing. Client: It reduced stress."}' \
  | python3 -c 'import json,sys; value=json.load(sys.stdin); required={"summary","keyTopics","homeworkStatus","insights","actionItems","moodTrend"}; assert required == value.keys()'

echo "Fixture, exact release readiness, scoped tools, and routed model call passed."
