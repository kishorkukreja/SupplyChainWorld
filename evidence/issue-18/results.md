# Issue #18 results

Status is stated separately for implemented, tested offline, and live-verified. Nothing here measures model ability; the live runs are connectivity/diagnostic runs, not an evaluation or benchmark.

## Implemented

- `src/supplychainworld/llm_adapter.py`, `config/llm_roster.json`, `scripts/run_llm_connectivity_check.py`, `scripts/run_llm_live_episode.py`, `tests/test_llm_adapter.py`.
- All acceptance items in the issue except "actual screenshots" (none exist and none are claimed; evidence is raw sanitized JSON/logs).

## Tested offline (no network, no credentials)

`tests.log`: full suite 167 tests OK (the existing 126 plus 41 new). Covered by injected-transport mocks: free-only guard and verified-zero-pricing guard, scorer role refusal, tool schema translation, manifest pinning, malformed JSON arguments, unknown/hidden tools, multiple tool calls, non-tool replies and nudges, 429/5xx/network retries with capped backoff and Retry-After, 4xx no retry, 200-with-error body, refusal and content_filter, HTTP 400 context limit, configured context limit, malformed response shapes, call/token/cost limits, missing usage reported as unknown (not zero), latency, secret redaction (patterns, deep, provider echo, header not stored, env credential), no-leak (module source and every request body of a mocked full episode), memory window, and a mocked full S01 five-day episode that completes, passes `verify_episode`, and replays identically.

## Live-verified (OpenRouter, free models, 2026-11-15, key injected by proxy)

Connectivity check, one request per roster model, max_tokens 64, one retry allowed (`connectivity.json`, `connectivity.log`). Cost reported as 0 by the provider for all that responded.

| Model | Result |
|---|---|
| baidu/ernie-5.5-flash-preview:free | responded, 1071 ms, 134 tokens, returned a tool call |
| nvidia/nemotron-3-ultra-550b-a55b:free | responded, 1075 ms, 328 tokens, returned a tool call |
| thinkingmachines/inkling-2-small:free | failed: HTTP 403, "only available on agentic harnesses" (provider_error). Not retried, not faked |
| cohere/north-mini-code:free | responded, 544 ms, 98 tokens, finish_reason length with no tool call or text within the 64 token cap; tool calling not demonstrated |
| nvidia/nemotron-3.5-super-vl:free | responded, 688 ms, 341 tokens, returned a tool call |
| respan/span-01-lite (scorer) | not attempted, request format unverified |

Live S01 five-day diagnostic episodes, model `baidu/ernie-5.5-flash-preview:free`, cap 12 model calls:

- Run 1 (`live-episode-run1-nudge-bug.json`, max output 1024): stopped incomplete after 4 calls. The model spent its 1024 token output cap twice without emitting a tool call (finish_reason length), and the adapter's nudge budget was counted over the whole episode rather than consecutive replies, so it stopped (`agent_stopped`, `no_tool_call`). The runner recorded no scorecard. This exposed that adapter bug; it was fixed (budget now counts consecutive non-tool replies, test added) and max output was set to 2048 for run 2. This is a second live run beyond the "one episode" brief, disclosed here.
- Run 2 (`live-episode.json`): 9 model calls, 9 HTTP requests, 0 retries, tokens prompt 21,974, completion 1,056, total 23,030, 12.8 s summed latency, cost 0. Runner status `complete`; independent verifier `feasible` with no codes; replay reproduced the transcript. Actions: expedite recovery, release 4 on days 1 to 3, advance each day. Scorecard: 12/12 on time, spend 24, penalties 0, comparison cost 24. One diagnostic episode proves the plumbing works; it supports no claim about model ability.

## Not done / limits

- No screenshots. `respan/span-01-lite` scoring request format unknown, so no scorer client exists. `inkling-2-small` and `north-mini-code` not shown to work with tool calling here. Token budgets rely on provider-reported usage; if usage is missing, only the call limit bounds the run. Runner remains an in-process boundary, not a sandbox against hostile code.
