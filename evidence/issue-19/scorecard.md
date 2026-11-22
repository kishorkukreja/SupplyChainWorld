# Issue #19 scorecard (diagnostic, free models, development set only)

Not a benchmark, no leaderboard, no single score. Full numbers: `scorecard.json`. Plain-language reading: `results.md`.

## Completion, validity, violations

| model | S01 episodes (completed/run) | S01 valid / invalid actions | S01 verifier feasible | S01 replay reproduced | static schema valid | static accepted | optimal awards (of 13) | exceptions accepted (of 7) |
|---|---|---|---|---|---|---|---|---|
| baidu/ernie-5.5-flash-preview:free | 4/4 | 68 / 1 | 4/4 | 4/4 | 19/20 | 19/20 | 13 | 6 |
| nvidia/nemotron-3-ultra-550b-a55b:free | 4/4 | 54 / 2 | 4/4 | 4/4 | 20/20 | 20/20 | 13 | 7 |
| nvidia/nemotron-3.5-super-vl:free | 2/3 | 25 / 4 | 3/3 | 3/3 | 16/20 | 16/20 | 11 | 5 |

Hard violations (S01 verifier codes): none in any episode. Static hard failures: schema_validation only (ernie 1, vl 4).

## Reliability, latency, tokens, cost

| model | requests | retries | HTTP 429 / 403 / 5xx / network | prompt tokens | completion tokens | summed latency (s) | cost (USD) |
|---|---|---|---|---|---|---|---|
| ernie | 97 | 2 | 1 / 0 / 0 / 1 | 623,574 | 61,997 | 722 | 0 |
| ultra | 77 | 0 | 0 / 0 / 0 / 0 | 533,908 | 72,598 | 1,487 | 0 |
| vl | 55 | 2 | 0 / 0 / 1 / 1 | 292,858 | 62,665 | 623 | 0 |

Total 231 of 250 requests (2 probe, 169 S01, 60 static). No model stopped by the breaker.

Per-scenario cost, service and risk comparison with the scripted policies, and the static reference and heuristic baselines: `scorecard.json` keys `s01_comparison_to_scripted` and `static_baselines`; the readable table is in `results.md`.
