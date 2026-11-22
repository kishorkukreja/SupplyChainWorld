# S01 audit results

Nothing here is practitioner-reviewed and nothing claims model ability. All business numbers are PROVISIONAL,
needs practitioner value. These are software tests of synthetic rules.

## Summary in plain language

**What was checked.** Every S01 version (v0.1, v0.2, v0.3, v0.4 and the new v0.5) was exercised with generated
scenarios and generated action sequences (not only the committed examples): stock and goods are conserved, nothing
goes negative, budgets hold, rejected actions change nothing, time only moves forward, penalties and cancellations
follow the written contract, replaying a recorded run gives the same result, and the independent checker accepts
valid runs and rejects tampered ones. Bad and hostile inputs were thrown at the tool interface, the scenario files,
the recorded transcripts and the checker. Twin worlds that differ only in a hidden future event (delay or not, how
late, even the date of the firm notice) were shown to look identical to the agent until the firm notice. Every
fixture was run with every declared policy through the real interfaces, the demo scripts were shown to regenerate the
committed evidence byte for byte, and the report and timeline pages for v0.1 to v0.4 were generated fresh and opened
in a real browser. A separate assessor that sees only what the agent sees was compared with the independent checker
(S01.3).

**What broke.** Seven real defects, six in the independent checker and one in the v0.1 scripted baseline. Fixed in
v0.1 to v0.3 (and D1 in v0.2, D7 in v0.1). **NOT fixed in v0.4 and v0.5:** the v0.4 checker file is frozen by the
first diagnostic run's manifest (`evidence/issue-19/manifest.json`, enforced by `tests/test_eval19_v2.py`), and the v0.5
checker builds on it, so D2 to D6 stay open there and are pinned by tests, disclosed here, and need a new checker version
(recommended). None of the fixes changes any committed evidence (the committed packets regenerate byte for byte). Each
fix has a test that failed before it.

**What is still a gap.** S01.3 is only partly shown: v0.1 does not show the size of the incoming supplier order, so
exposure cannot be worked out there; v0.2 to v0.5 show every number needed, but the rules that turn numbers into
outcomes are not written in any observation. Exact-once execution of a recovery in v0.2 to v0.5 holds only when the
caller supplies an `action_id`. The readability of the experience record has no test. v0.5 has no demo script or
page, so no browser test exists for it.

## Defects found and fixed (each: failing regression test first, then the smallest fix)

Regression tests: `tests/test_s01_audit_regressions.py` (10 tests). Run against the unfixed `origin/main` code they give
42 failures and 95 errors; against the fixed code they pass. Effect on committed evidence for every fix: none, checked by
`test_s01_versions_e2e.DemoScriptsRegenerateCommittedEvidence` (all files for v0.1 to v0.4 equal the committed ones) and
by the existing suite.

| Id | Defect | Where found | Fix |
|---|---|---|---|
| D1 | v0.2 verifier refused a scenario the simulator runs (rate-card unit cost 0) | generated scenarios | `dynamic_verifier_v2._config` allows unit cost 0 |
| D2 | All verifiers ignored the `day_open` and `opening_before_notice` records and their order: a forged opening state (the published state-ledger files are built from it), or a deleted, duplicated or reordered opening record, was accepted | mutation tests | opening records compared with the ledger; pure reordering of records detected; money codes unchanged so old corruption cases keep their code sets |
| D3 | Verifiers compared only part of each claimed state (horizon, open demand, order quantity and due day, late counters, v0.1 notices) | mutation tests | those fields are compared |
| D4 | A record whose `details` or `state` is not a mapping crashed every verifier (AttributeError) | fuzz | reported as malformed, no crash |
| D5 | A scenario with malformed `orders` or `tiers` crashed the v0.2 to v0.4 verifiers (TypeError, KeyError) instead of ScenarioError | fuzz | `_config` wraps and re-raises as ScenarioError |
| D6 | A claimed action log with a non-mapping entry crashed every verifier | fuzz | entries reported as malformed |
| D7 | v0.1 scripted `expedite` and `alternate` policies retried an unaffordable recovery forever (500 attempts, never left day 1) | property equivalence setup | tried once (`agent_runner.scripted_policy`) |

D2 to D6 are open in v0.4 and v0.5 (frozen file; `OpenDefectsInTheFrozenV04Verifier` pins them; the tests that need the fixes are skipped there and reported as skipped, not passed). Before and after numbers: `mutation-fuzz-summary-before-fixes.md`
(history mutants surviving: 433 of 1022 in v0.1, 1305 of 3297 in v0.2, 1730 of 4155 in v0.3, 1742 of 4142 in v0.4, 1801 of 4174 in v0.5;
checker crashes on garbage histories: 286 to 321 per 1000) against `mutation-fuzz-summary.md` (0 survivors and 0 crashes in v0.1 to v0.3; v0.4 and v0.5 still show the unfixed numbers).

## Findings that are not defects (left as they are, stated honestly)

- F1 v0.2 to v0.4 demo scripts write only `timeline.txt`; added `scripts/render_s01_timeline_html.py` (new file) so a timeline page can be tested.
- F2 From a history alone nobody can detect deletion, repetition or moving of REJECTED command records, or extra records of unknown kind; the runner transcript and replay protect that and are tested.
- F3 The verifier does not compare the schema and runtime version fields of claimed states.
- F4 v0.2 to v0.5: a recovery is exact-once only with an `action_id`; the same call re-sent without one is a second purchase (tested and pinned).
- F5 v0.1 never shows the inbound primary PO quantity (S01.3).
- F6 v0.2 to v0.5 observations do not state the rules (same-day use of receipts, shipping from the due day, serving order, penalty rate units; percent means whole percent in v0.2 and basis points in v0.3 and later). Recommendation: a `conventions` block in a new version module; not implemented here.
- F7 Before a firm notice of a real delay the observations support only a range (intended).
- F8 No test of the readability of the experience record; no v0.5 demo script, page or screenshot.

## S01.3 verdict

See `s01-3-assessment.md`. v0.1: insufficient. v0.2 to v0.5: quantities sufficient and equal to the independent checker's
ground truth (generated scenarios and every fixture, day and option); rule statements missing; before the firm notice only bounds.

## What was exercised

- Hypothesis examples requested per full run (ci profile, derandomized): see `mutation-fuzz-summary.md` (audit modules only).
- Seeded campaign: see `mutation-fuzz-summary.md`. v0.1 to v0.3 kill every history mutant with no crash; v0.4 and v0.5 do not (open defects). Scorecard and action-log forgeries are all rejected in every version; malformed tool calls are all rejected with state unchanged in every version.
- Equivalences: v0.4 = v0.3 without alternate buys; v0.4 vs v0.3 spend differs by exactly base cost x alternate units; v0.3 = v0.2 with v0.3-only features off; v0.2 = v0.1 for one order and whole-lot recovery.
- Browser: 10 tests, pages generated fresh, no console errors; screenshots in `screenshots/` (v0.1 timeline, v0.2, v0.3, v0.4 reports), viewed and confirmed to render.

## Run time

See the last lines of `tests.log` for the measured wall time of the full suite on this machine (the sandbox clock and speed may differ from CI; CI duration is not guessed here).
