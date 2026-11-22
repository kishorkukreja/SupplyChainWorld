# Issue #19 fixes: results (plain language)

No model was called. Everything below was checked with fake models and offline tests. Numbers are provisional, nothing here says anything about how good a model is.

## 1. The plant world no longer gives away the answer

Before: the world showed a scenario name like "warned-delayed", which told a model the outcome. Now (new version v0.5) the world shows only a code like "scn-bc29021c". The code is computed from the visible setup only, so the "warned and delayed" and "warned and not delayed" scenarios carry the very same code. A hand-picked descriptive name is refused by the world and flagged by the independent checker.

Proof: a generated-scenario test (Hypothesis) builds twin scenarios that differ only in the hidden outcome and checks that everything the agent sees, every state, rule text, tool result and error message, is identical until the firm notice. Through the model harness, the requests sent for the twin scenarios are byte for byte identical until the notice. The old v0.4 world fails the same comparison (kept as a regression check). All 25 episodes (5 scenarios x 5 scripted policies) agree across the simulator, the independent checker and the hand-worked ledgers, replay exactly and pass the leak scan. The numbers did not change from v0.4, so the hand ledgers are the v0.4 ledgers renamed; a committed generator reproduces both fixture files and a test checks they match.

## 2. Every enforced rule is now told to the model

The rule "production cannot exceed open customer demand" was enforced but never stated. The next run's prompt and tool descriptions now state it, together with capacity per day, components on hand, one release per day, the recovery budget, once-only purchases, the per-day call limit, when recovery can be bought, offer windows, tier cancellation, penalties and salvage. A test reads the source code, finds every refusal reason the world and runner can give, and fails if one has no stated rule or if its sentence is missing from the prompt and tool descriptions. A new unexplained refusal would fail the suite.

## 3. Strict answer shapes for the purchasing task

Each answer kind (award, clarification, infeasible) has exactly its own fields; extra or missing fields are rejected with a message naming the field, with no credit and no repair. The new harness gives the model one tool per kind, so an extra field is not even expressible, and grades the shape first. The older 1.2 contract and fixtures are unchanged. Property tests (valid answers accepted, one extra or one missing field rejected, wrong types rejected) and fuzz tests (arbitrary JSON, damaged real answers) pass. The first run's failure patterns (extra fields on a clarification, evidence as one string) each get no credit and a clear message.

## Versioning

The first run's harness files and manifest are unchanged and verified by a test, so that run record stays valid. The next run uses `eval19_v2` with a bumped, draft manifest that records the old hashes. The owner must set the roster and commit the manifest before any call.

## Tests

Full suite: 652 tests, all pass, no skips (command in tests.log). New in this work: about 85 tests across property (twin scenarios, whole episodes, strict shape), fuzz (tool calls, scenario ids, leak scan, strict shape), end to end (25 episodes through the model harness, 33 static cases, the whole run script and report with a mocked network) and pinned checks.

## Left open

Practitioner confirmation of every number is still pending. The rerun, more models and the preregistered manifest are the owner's next step. No browser test was needed (no page changed).
