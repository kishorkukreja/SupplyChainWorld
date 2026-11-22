# Issue #19 results: small free-model diagnostic

## Plain-language summary

What this is: a small check, on free models only, of whether the procurement world, its checkers and the model harness hold up when a real model is plugged in. It is not a ranking and says nothing about how good any model is in general. It cost USD 0.

What ran: 3 free models (baidu ernie-5.5-flash-preview, nvidia nemotron-3-ultra, nvidia nemotron-3.5-super-vl). 231 live requests of the 250 allowed. Two other planned models were gone before the run started (cohere north-mini-code and thinkingmachines inkling-2-small both answered "no longer available", HTTP 404) so they were not run.

- Multi-day plant task (S01 v0.4, 5 scenarios): each model got ONE attempt per scenario, not 3. Repeating 5 scenarios 3 times for 3 models would need over 1,000 requests, far above the 250 cap. The 250 ran out before the fifth scenario (alt-cheaper) and before the vl model's fourth scenario, so those were not run. 11 episodes ran.
- One-shot purchasing task (static v1.2, 20 of 33 cases, picked by a fixed rule written down in advance): every model answered all 20.

What happened, per model, in plain words:
- ernie: finished all 4 plant episodes it ran, no rule breaks (it made 1 invalid release, then fixed it). Purchasing: 19 of 20 accepted, every award optimal. The 1 miss was a format slip (an extra field in a clarification), not a wrong decision.
- nemotron-ultra: finished all 4 plant episodes, no rule breaks (2 harmless invalid calls). Purchasing: 20 of 20 accepted, all 13 awards optimal, all 7 exception cases right. It was the slowest (median 27 s per purchasing answer).
- nemotron-vl: plant task 3 episodes: 2 finished, 1 stopped because three replies in a row ran out of output tokens (4096) with no tool call. Purchasing: 16 of 20 accepted; 4 were format failures (3 put the evidence in as text instead of a list, 1 added extra fields). Their reasoning was right: after a mechanical format repair (exploratory only, not a result) all 4 pass.

What broke or looked wrong: (1) the plant world's state shows a scenario name such as "warned-delayed", which gives away the outcome. I hid it from the models; the world itself still has the issue (task defect). (2) One rule (do not produce more than open demand) is enforced but is not written in the rules or tool text, so two models hit it once (harness gap). (3) Models called the scorecard before the end (harmless, refused). (4) Format slips caused all 5 static failures; the tool definition did not stop them. No grader defect and no replay problem was found. See failure-taxonomy.md.

Recommendation for teacher collection (#20): REPAIR, then go. Not a stop: the plumbing, checkers and replay worked, and nothing was fabricated or leaked. Not a go yet: fix the three items above (hide the scenario id in the world itself, state the production rule, per-kind submission schema), rerun this same diagnostic once, and have the owner read this record. Training-use terms for each free model are UNCHECKED, and nothing here supports training value or says what a model learns. 11 episodes and 60 one-shot answers cannot support a capability claim.

## What was frozen before any model call

`manifest.json` was committed on its own (commit 26469ea, after the harness commit 4545198 and before any request): roster, case selection rule, prompts, tool profile, limits, retry rules, breaker rules, metrics and baselines. Files are hashed in the manifest and unchanged since. No prompt, tool, limit or rule was changed after the freeze, so no rerun was needed and no harness fix was made.

Deviations, all stated in the manifest in advance or forced by the world: 1 attempt not 3 repeats (request cap); 2 conditional models unavailable (404 at the probe); S01 allowance ran out before 4 of the 15 model-scenario slots (listed below).

## Numbers

Requests: 231 of 250 (2 probe, 169 plant task, 60 purchasing). Retries: ernie 2 (one HTTP 429, one network error), vl 2 (one HTTP 502, one network error), ultra 0. No HTTP 403. No model was stopped by the breaker. Cost: USD 0 reported for every call with usage (usage was present for all). Raw requests per model: ernie 97, ultra 77, vl 55.

### Plant task (S01 v0.4), one attempt per scenario

| model | episodes run | completed | verifier feasible | replay reproduced | valid actions | invalid actions | hard violations |
|---|---|---|---|---|---|---|---|
| ernie | 4 | 4 | 4 | 4 | 68 | 1 | 0 |
| nemotron-ultra | 4 | 4 | 4 | 4 | 54 | 2 | 0 |
| nemotron-vl | 3 | 2 | 3 | 3 | 25 | 4 | 0 |

Not run (allowance exhausted): alt-cheaper-10d for all 3 models; multitier-cancel-10d for vl. Every observation shown to a model was scanned for outcome leaks: none. No request carried a private marker.

Metrics are reported separately, never combined. Cost = net cost (USD, lower is better); service = orders on time (otif, 1 means all on time), on-time units of 12, units-days late; downstream = cancelled order value. Scripted policies are the five S01 baselines run on the same scenarios (maintain / expedite / alternate / combo / staged).

| scenario | who | net cost | recovery spend | penalties | orders on time | on-time units | unit-days late | cancelled value |
|---|---|---|---|---|---|---|---|---|
| sudden-5d | scripted maintain | 18 | 0 | 18 | 0 | 4 | 12 | 0 |
| | scripted expedite / alternate / combo / staged | 32 / 24 / 28 / 36 | same | 0 | 1 | 12 | 0 | 0 |
| | ernie, ultra, vl | 24, 24, 24 | 24 | 0 | 1 | 12 | 0 | 0 |
| warned-delayed-10d | scripted maintain | 30 | 0 | 30 | 0 | 4 | 20 | 0 |
| | scripted expedite / alternate / combo / staged | 32 / 24 / 28 / 36 | same | 0 | 1 | 12 | 0 | 0 |
| | ernie / ultra / vl | 32 / 32 / 40 | same | 0 | 1 | 12 | 0 | 0 |
| warned-no-delay-10d | scripted maintain | 0 | 0 | 0 | 1 | 12 | 0 | 0 |
| | scripted expedite / alternate / combo / staged | 32 / 24 / 28 / 16 | same | 0 | 1 | 12 | 0 | 0 |
| | ernie / ultra / vl | 24 / 0 / not completed | 24 / 0 / - | 0 | 1 | 12 | 0 | 0 |
| multitier-cancel-10d | scripted maintain | 67 | 0 | 67 | 0 | 4 | 48 | 320 |
| | scripted expedite / alternate / combo / staged | 60 / 37 / 36 / 64 | 32 / 24 / 28 / 36 | 28 / 13 / 8 / 28 | 1 | 12 / 8 / 12 / 12 | 28 / 12 / 8 / 28 | 320 / 0 / 0 / 320 |
| | ernie | 34 | 12 | 22 | 1 | 8 | 20 | 0 |
| | ultra | 56 | 40 | 16 | 1 | 12 | 16 | 160 |

Reading it plainly, without ranking: in the three simple scenarios the models landed inside the scripted range, often matching "alternate" (cost 24). The one scenario with tiers and cancellation shows a real spread: ernie had the lowest net cost of anyone (34, against 36 for the cheapest scripted policy) but delivered only 8 of 12 units on time, the same as the scripted alternate policy; ultra spent the whole recovery budget (40), cut lateness but one order was cancelled (160 value) where the two cheaper scripted policies had none. These are single attempts, so they say nothing about consistency. In warned-no-delay, ultra did nothing and spent 0, which matches the cheapest scripted policy; ernie bought insurance for 24. Neither model could see which of the two paired scenarios it was in (the id was hidden), so these are fair single decisions under the same signal.

Clarification and escalation in S01: not applicable (the S01 tool profile has no ask or escalate tool).

Latency and tokens (plant + purchasing, summed per model): ernie 722 s, 624k prompt / 62k completion tokens; ultra 1,487 s, 534k / 73k; vl 623 s, 293k / 63k. Median one-shot purchasing answer: ernie 9 s, vl 13 s, ultra 27 s.

### One-shot purchasing (static v1.2), 20 cases, one answer each

Selection (frozen): all 7 non-award cases (6 clarification, 1 infeasible) plus every second award case in id order (13): ref-01, 03, 05, 07, 09, 10, 11, 13, 15, 17, 18, 19, 21, 23, 25, 27, 29, 30, 31, 32.

| model | schema valid | accepted by checker | feasible awards | optimal awards | right kind of answer | exception cases accepted | false escalation on awards | award given where exception was needed |
|---|---|---|---|---|---|---|---|---|
| ernie | 19 | 19 | 13 of 13 | 13 | 20 of 20 | 6 of 7 | 0 | 0 |
| ultra | 20 | 20 | 13 of 13 | 13 | 20 of 20 | 7 of 7 | 0 | 0 |
| vl | 16 | 16 | 11 of 13 | 11 | 20 of 20 | 5 of 7 | 0 | 0 |

"Right kind of answer" means award / clarification / infeasible matched the expected outcome. The grader gives no credit when the format is invalid, and nothing was repaired. Baselines on the same visible world and the same checker: reference solver accepted 20 of 20 (13 optimal awards); greedy heuristic produced an accepted answer on 17 of 20 and no answer on 3 (ref-10, ref-13, ref-15, solver returned its error status), 11 optimal awards of the awards it produced where run. Permitted compute differs: the reference solver searches exhaustively, the heuristic is greedy, a model gets one answer with no tools and no calculator, so a model matching the reference is not like-for-like with a solver.

Exploratory, not a result (`exploratory-format-repair.json`): the 5 schema failures all pass the checker after a mechanical repair (wrap text in a list, drop extra keys). So these were format failures, not wrong decisions.

## What is not known

Whether any result holds on repeat (one attempt each), on the 13 static cases not run, on the alt-cheaper scenario, or for any model beyond these runs. Provider versions behind each free id are not exposed. Free-model terms for training use are unchecked. The S01 and static numbers are provisional working values and were not confirmed against real data; the reviewer did not check the fixtures case by case (#17 decision).

## Files

`manifest.json` (preregistration), `runs/` (sanitized per-run records: 11 plant, 60 purchasing), `scorecard.json` (all numbers, including baselines), `request-ledger.jsonl` (one line per HTTP request, no bodies or keys), `failure-taxonomy.md`, `exploratory-format-repair.json`, `tests.log`. Full private transcripts and raw model answers stay outside the repository.

Reproduce offline: `PYTHONPATH=src python -m unittest discover -s tests`. Live run: `OPENROUTER_API_KEY=... PYTHONPATH=src python scripts/run_eval19.py run --state DIR`, then `report`.
