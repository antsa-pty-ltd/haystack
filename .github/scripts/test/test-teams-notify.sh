#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
NOTIFY_SCRIPT="${SCRIPT_DIR}/../teams-notify.sh"
WORKFLOW="${SCRIPT_DIR}/../../workflows/ci.yml"
TEST_DIR="$(mktemp -d)"
SERVER_PID=""

cleanup() {
  if [[ -n "${SERVER_PID}" ]]; then
    kill "${SERVER_PID}" 2>/dev/null || true
  fi
  rm -rf "${TEST_DIR}"
}
trap cleanup EXIT

expect_failure() {
  if "$@"; then
    echo "Expected command to fail" >&2
    exit 1
  fi
}

start_server() {
  local status="$1"
  local prefix="$2"
  local port_file="${TEST_DIR}/${prefix}.port"
  local body_file="${TEST_DIR}/${prefix}.json"

  python3 "${SCRIPT_DIR}/mock_webhook.py" "${status}" "${port_file}" "${body_file}" &
  SERVER_PID="$!"
  for _attempt in {1..100}; do
    [[ -s "${port_file}" ]] && break
    sleep 0.02
  done
  [[ -s "${port_file}" ]] || { echo "Mock webhook failed to start" >&2; exit 1; }
  MOCK_URL="http://127.0.0.1:$(<"${port_file}")"
  MOCK_BODY_FILE="${body_file}"
}

run_notify() {
  WEBHOOK="${1:-}" \
  TITLE='Haystack "quoted" checks failed' \
  REPO='antsa-pty-ltd/haystack-service' \
  BRANCH='feature/probe → develop' \
  COMMIT='1234567890abcdef' \
  RUN_URL='https://github.example/actions/runs/42' \
    "${NOTIFY_SCRIPT}"
}

# A protected-branch failure is reproducible on a PR without merging broken
# code to develop. The notification job must cover that PR and push failures.
grep -Fq "github.event_name == 'pull_request'" "${WORKFLOW}"
grep -Fq "github.base_ref == 'develop'" "${WORKFLOW}"
grep -Fq "github.event_name == 'push'" "${WORKFLOW}"
grep -Fq "needs.test.result == 'failure'" "${WORKFLOW}"

bash -n "${NOTIFY_SCRIPT}"

# Missing configuration must fail visibly rather than report a green no-op.
expect_failure run_notify ""

start_server 202 success
run_notify "${MOCK_URL}"
wait "${SERVER_PID}"
SERVER_PID=""

jq -e '
  .type == "message" and
  .attachments[0].content.body[0].text == "❌ Haystack \"quoted\" checks failed" and
  .attachments[0].content.body[1].facts[0].value == "antsa-pty-ltd/haystack-service" and
  .attachments[0].content.body[1].facts[1].value == "feature/probe → develop" and
  .attachments[0].content.body[1].facts[2].value == "1234567" and
  .attachments[0].content.actions[0].url == "https://github.example/actions/runs/42"
' "${MOCK_BODY_FILE}" >/dev/null

# A rejected webhook must also fail the notification step.
start_server 500 rejected
expect_failure run_notify "${MOCK_URL}"
wait "${SERVER_PID}"
SERVER_PID=""

echo "Haystack Teams notification tests passed"
