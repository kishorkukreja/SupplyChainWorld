# Decisions API client: results

Scope: `src/supplychainworld/decisions_client.py`, the real client behind the `decision_system1` scorer slot
(`respan/span-01-lite`, OpenRouter `POST /api/alpha/decisions`).

## Implemented

- `DecisionsClient.yes_no`, `ask_many`, `route` (router built on independent yes/no scoring: per-option probabilities,
  argmax, `ambiguous` flag when no option reaches the threshold or the top two are within a margin; probabilities are not
  normalized and do not sum to 1).
- Only `noul` questions are accepted; other types and malformed criteria are rejected before any request is made.
- Free-only guard (roster kind `scorer` and verified zero pricing), $0 ceiling (a reported non-zero cost disables the client),
  bounded retries for 429/5xx/network, no retry on 400, no fabricated answers on missing or out-of-range fields,
  usage and cost tracking (`unknown` when not reported), secret redaction.
- `config/llm_roster.json`: `decision_system1` status is `verified: noul-only via /api/alpha/decisions`, with the verified
  request shape and the limitation recorded. The slot is a scorer and never acts through `ObservableRunner`.

## Tested (offline, mocked transport)

`tests/test_decisions_client.py`, 35 tests: roster guard, request/response shape, thresholds, many-question requests,
non-noul rejection, route clear/ambiguous/none-above-threshold/tie cases, retries and bounds, 400/429/5xx, errors in a 200 body,
malformed responses, usage and cost accounting, cost ceiling, secret redaction, and a test that only the caller-supplied
`state` string and question text are sent and that the module imports no world, runner or verifier code.

## Live-verified (`decisions-check.json`, 2026-11-16)

Three requests total, no retries, neutral S01-style text written in the script: one `yes_no`, one `ask_many` (2 questions),
one `route` (3 options). All three returned HTTP 200 with well-formed noul probabilities in [0, 1], `output_tokens` 0 and
cost 0. Total input tokens 1185, total cost $0.

## Not claimed

Three calls are connectivity and response-shape evidence only. They are not an evaluation, and nothing here says whether
the probabilities are accurate or calibrated. The API is alpha, so request and response shapes may change.
