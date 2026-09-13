# Report refinement

Refinement edits the existing document. It does not retrieve old transcripts or
run the document exploration agent. This lets a practitioner shorten or rename
content without regenerating information they have already removed.

## Request context

`generator.py` accepts the browser's `ORIGINAL DOCUMENT:` /
`REQUESTED MODIFICATIONS:` envelope and the assistant tool's legacy
`**Original Document:**` / `**Refinement Instructions:**` envelope. Keep the
latest requested edit separate from the source document: measurable shortening
limits are calculated from those two fields by `refinement.py`.

The browser should also preserve the source document's template guidance,
initial generation instructions and previous edits. A different currently
selected template must not replace the original guidance. The latest request
can override an earlier preference.

The API tokenizes names in both source content and instructions before sending
them to Haystack. `[CLIENT_NAME]` represents the full name;
`[CLIENT_FIRST_NAME]` represents the given name and `[CLIENT_LAST_NAME]` the
surname. A first-name-only request must use `[CLIENT_FIRST_NAME]` rather than
requiring the practitioner to type the surname. The API restores these tokens
for display after generation.

## Shortening

Explicit percentage or word limits apply to the document being edited, not the
model's first attempted rewrite. A general request such as “make it more
concise” sets a target of at most 75% of the original word count. Clinical goals
such as “reduce anxiety by 50%” are not document-length instructions.

The generator checks the returned word count and allows at most two corrective
attempts. It never truncates clinical text to meet a limit. Naming preferences
and clinically relevant meaning must survive the rewrite.

## Failure contract

- HTTP 422 means the requested length could not be met after the bounded
  attempts, or a corrective attempt returned empty content.
- HTTP 503 means refinement failed because of a provider or processing error,
  including a failure during a corrective attempt or a provider refusal.
- A failed refinement must not return a successful response containing a
  “Generation Error” document. Log only the failure category, not provider
  response text, client details or the document itself.

Callers must treat non-success responses, and legacy responses with
`metadata.error`, as failures. Keep the original note intact, remove the failed
pending version and show a retry message. Do not save failure text as a note or
report that a failed edit completed successfully.

Regression coverage lives in `tests/test_refinement_routing.py`. It covers both
request envelopes, naming guidance, shortening limits, retries, provider
failures and the non-document error response contract. Run `pytest tests`
before releasing changes to this flow.
