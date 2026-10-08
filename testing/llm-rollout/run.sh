#!/usr/bin/env bash
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo="$(cd "$here/../.." && pwd)"
credentials="$here/credentials.env"
: "${HAYSTACK_SOURCE:=$repo}"
: "${GATEWAY_SOURCE:=/Users/alec/Projects/antsa/.worktrees/gateway-rollout-20261008}"

[[ -f "$credentials" ]] || { echo "Run ./prepare-credentials.sh first" >&2; exit 1; }
mode="$(stat -f '%Lp' "$credentials" 2>/dev/null || stat -c '%a' "$credentials")"
[[ "$mode" == "600" ]] || { echo "credentials.env must have mode 600 (found $mode)" >&2; exit 1; }
set -a
# shellcheck disable=SC1090
source "$credentials"
set +a
for name in OPENAI_API_KEY LITELLM_MASTER_KEY HAYSTACK_GATEWAY_KEY HAYSTACK_WEBHOOK_SECRET; do
  [[ -n "${!name:-}" ]] || { echo "$name is required in credentials.env" >&2; exit 1; }
done
[[ ${#LITELLM_MASTER_KEY} -ge 32 && ${#HAYSTACK_GATEWAY_KEY} -ge 32 ]] || {
  echo "Gateway keys must contain at least 32 characters" >&2; exit 1;
}
[[ "$LITELLM_MASTER_KEY" != "$HAYSTACK_GATEWAY_KEY" ]] || {
  echo "Master and Haystack gateway keys must differ" >&2; exit 1;
}
export HAYSTACK_SOURCE GATEWAY_SOURCE
export HAYSTACK_SHA="$(git -C "$HAYSTACK_SOURCE" rev-parse HEAD)"
export GATEWAY_SHA="$(git -C "$GATEWAY_SOURCE" rev-parse HEAD)"

docker compose --project-directory "$here" -f "$here/compose.yaml" config --quiet
docker compose --project-directory "$here" -f "$here/compose.yaml" up --build -d
echo "Stack started. Run $here/probe.sh after containers become healthy."

