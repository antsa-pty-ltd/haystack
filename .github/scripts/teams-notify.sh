#!/usr/bin/env bash
set -euo pipefail

if [[ -z "${WEBHOOK:-}" ]]; then
  echo "::error::TEAMS_WEBHOOK is not configured; no Teams notification was sent." >&2
  exit 2
fi

for required_name in TITLE REPO BRANCH COMMIT RUN_URL; do
  if [[ -z "${!required_name:-}" ]]; then
    echo "::error::${required_name} is required to send a Teams notification." >&2
    exit 2
  fi
done

payload_file="$(mktemp)"
response_file="$(mktemp)"
cleanup() {
  rm -f "${payload_file}" "${response_file}"
}
trap cleanup EXIT

short_sha="${COMMIT:0:7}"
jq -n \
  --arg title "❌ ${TITLE}" \
  --arg repo "${REPO}" \
  --arg branch "${BRANCH}" \
  --arg commit "${short_sha}" \
  --arg run_url "${RUN_URL}" \
  '{
    type: "message",
    attachments: [{
      contentType: "application/vnd.microsoft.card.adaptive",
      content: {
        type: "AdaptiveCard",
        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
        version: "1.4",
        body: [
          {type: "TextBlock", size: "Medium", weight: "Bolder", text: $title, color: "Attention"},
          {type: "FactSet", facts: [
            {title: "Repo:", value: $repo},
            {title: "Branch:", value: $branch},
            {title: "Commit:", value: $commit}
          ]}
        ],
        actions: [{type: "Action.OpenUrl", title: "View workflow run", url: $run_url}]
      }
    }]
  }' >"${payload_file}"

set +e
status="$(curl --silent --show-error --output "${response_file}" --write-out '%{http_code}' \
  --request POST --header 'Content-Type: application/json' \
  --data @"${payload_file}" "${WEBHOOK}")"
curl_exit="$?"
set -e

if [[ "${curl_exit}" -ne 0 ]]; then
  echo "::error::Teams notification request failed before an HTTP response was received." >&2
  exit 1
fi

if [[ "${status}" =~ ^2[0-9][0-9]$ ]]; then
  echo "Teams notification sent (HTTP ${status})."
  exit 0
fi

echo "::error::Teams notification was rejected (HTTP ${status})." >&2
exit 1
