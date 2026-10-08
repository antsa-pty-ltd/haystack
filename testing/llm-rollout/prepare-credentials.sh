#!/usr/bin/env bash
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
target="$here/credentials.env"
if [[ -e "$target" ]]; then
  echo "Refusing to overwrite $target" >&2
  exit 1
fi
umask 077
master="$(openssl rand -hex 32)"
haystack="$(openssl rand -hex 32)"
service="$(openssl rand -hex 32)"
printf '%s\n' \
  'OPENAI_API_KEY=' \
  "LITELLM_MASTER_KEY=$master" \
  "HAYSTACK_GATEWAY_KEY=$haystack" \
  "HAYSTACK_WEBHOOK_SECRET=$service" > "$target"
chmod 600 "$target"
echo "Created $target with local scoped keys. Add OPENAI_API_KEY without changing its mode."

