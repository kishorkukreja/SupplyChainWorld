# eval19-3 run: six models on S01 v0.6 (prepared, not run)

Status: code, roster and tests only. No model has been called. The plan file is committed on its own before any call.
All business numbers are PROVISIONAL, needs practitioner value. Owner review only, not independent. No claim about model ability.

## What it is

One diagnostic: 6 models x 5 S01 v0.6 scenarios x 2 repeats = **60 episodes** (30 on OpenRouter free models, 30 on Sarvam).
It looks for task, checker, harness and model defects. It is not a benchmark and not a leaderboard.

| Route | Models | Rule |
|---|---|---|
| OpenRouter (`llm_adapter`) | `baidu/ernie-5.5-flash-preview:free`, `nvidia/nemotron-3-ultra-550b-a55b:free`, `google/gemma-4-31b-it:free` | free only, USD 0 |
| Sarvam (`sarvam_adapter`) | `sarvam-105b`, `glm5.3-flash`, `deepseekv4.1-flash-1017` | paid, one cap of INR 10000 for the whole run |

`config/eval19_v3_roster.json` holds the list. The older `config/llm_roster.json` is untouched. The full `glm5.3` is not used
(about 9 times the price and always thinks at maximum effort) unless the owner asks.

## Files

| File | What it is |
|---|---|
| `config/eval19_v3_roster.json` | the six models and their route |
| `src/supplychainworld/eval19_v3_run.py` | roster check, plan builder, queue, resumable run, live Sarvam check, summary |
| `scripts/run_eval19_v3.py` | command line: `plan`, `check`, `run`, `summary` |
| `evidence/eval19-3/plan.json` | the pre-registration, committed alone before any call |
| `tests/test_eval19_v3_run_{property,fuzz,e2e}.py` | the tests below |

## How a run goes

1. `plan` writes `evidence/eval19-3/plan.json` (no model call). It is committed alone. It carries the models, scenarios, repeats,
   queue, limits, caps, rules and the hash of every frozen file.
2. `check --live` (a session that has `SARVAM_API_KEY`): one small call per Sarvam model through the real adapter, to confirm the
   request shape is accepted and token usage comes back. Costs a few paise.
3. `run --live`: refuses unless the plan is committed, clean, and every frozen file still matches its hash. Plays the queue in a fixed
   order (repeat, scenario, model), one private record per episode in `--state`. Restart-safe: counters are rebuilt from ledgers.
4. Each finished episode can go to Langfuse (off unless `SCW_LANGFUSE=1`); a Langfuse problem never costs a finished run.
5. `summary` prints a table per model. The checker verdicts are never merged into one score.

## Money and request rules

- Sarvam: every call reserves its worst-case price before it is sent; unknown billing counts at the worst case; the run stops when a call
  could pass INR 10000. Worst-case reservations are small (well under INR 1 per call).
- Request caps: 2000 HTTP requests per route, retries included. The worst case of model calls is 1620 per route (6 x horizon days per
  episode), so retries have room. OpenRouter free models have daily request limits that are not checked: a model that hits them is stopped
  by the breaker and its remaining episodes are reported as not run; the run can continue on another day.
- Throttle: at least 3.5 s between requests on a route. A full run is therefore hours, not minutes.

## Test traceability (software only)

| Requirement | Tests |
|---|---|
| Only allowed routes: OpenRouter ids end in `:free`, Sarvam ids in the price table, actors only, no duplicates | property `Roster`, fuzz `MalformedInputs` |
| 60 episodes, every (repeat, scenario, model) exactly once, any stopped prefix balanced | property `Queue`, e2e `FullRun` |
| Plan cannot be changed unnoticed (any field, any frozen file, any fixture) | property `PlanIntegrity`, fuzz `MalformedInputs` |
| Run refuses without `--live`, without a committed plan | e2e `ScriptRefusals` |
| Real entry points, checker, replay, leak scan on every episode | e2e `FullRun` |
| Resume gives the same records as an uninterrupted run; a restart cannot pass a cap | e2e `ResumeAfterAStop` |
| Spend: free route costs 0, Sarvam positive and under the cap, worst case on unknown billing | e2e `FullRun`, fuzz `HostileProviders` |
| Broken or hostile providers (timeout, 5xx, 429, 403, 402, raise, junk, error in 200) | fuzz `HostileProviders` |
| No secret in any record, ledger or trace | e2e `FullRun`, `Tracing`, fuzz `HostileProviders` |
| No scenario name in any request | fuzz `PrivateStrings` (and the existing guard tests) |
| Langfuse export once per episode | e2e `Tracing` |

Gaps, reported honestly: no browser test (no user-visible page changes in this work); the live provider behaviour (Sarvam tool-call
shape and usage fields, reasoning tokens, OpenRouter daily limits) is not tested until a session with the key runs `check`.
The plain-language run stories and the exact-message run record suggested by the tracing thread are not part of this change.
