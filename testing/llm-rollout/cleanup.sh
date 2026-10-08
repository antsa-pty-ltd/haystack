#!/usr/bin/env bash
set -euo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
docker compose --project-directory "$here" -f "$here/compose.yaml" down --volumes --remove-orphans

