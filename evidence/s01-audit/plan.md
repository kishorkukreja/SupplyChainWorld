# S01 audit plan

Branch `implementation/s01-audit` off `origin/main` (after the test infrastructure PR #45). Refs the S01 issues; closes nothing.

Owner's ask: strengthen each S01 sub-scenario (S01.1 to S01.6) against its own acceptance evidence in
`docs/acceptance/scenario-map.md` section 4, using the primary test types of `CLAUDE.md` (property, fuzz,
end-to-end, browser), not more example tests. Nothing here is practitioner-reviewed and nothing claims model ability.

## Checklist and how each item was done

1. **Traceability.** Table in `docs/testing.md`: one row per acceptance criterion for S01.1 to S01.6, plus the gates G1 to G9, for v0.1 to v0.4, with exact test names and an honest status (covered, partial, GAP). A criterion shown only by a scripted example is `partial`.
2. **S01.3 assessment.** `tests/support/s01_assess.py` reads only an agent view and computes units at risk, earliest feasible delivery and penalties under each recovery option; `tests/test_s01_assessment_property.py` compares with the independent verifier's ground truth over generated scenarios and every fixture. Note: `s01-3-assessment.md`.
3. **Property tests (Hypothesis, ci profile)** for the simulator, runner and verifier of each version: generated scenario parameters and call sequences; conservation, no negative stock, budget, exact-once, penalty and cancellation rules, time order, replay, verifier accepts valid runs and rejects mutated ones (drop, duplicate, reorder, change amounts, retype, flip, shift day; forged scorecard and action log); equivalences v0.4 to v0.3, v0.3 to v0.2, v0.2 to v0.1.
4. **Fuzz tests.** Malformed and adversarial tool calls, authority subsets, damaged scenarios, damaged transcripts, garbage and event-shaped histories, wrong-version transcripts; early-warning twin pairs (delay or no delay, different delayed day, different notice day) must give identical observations until the firm notice.
5. **End-to-end.** Every fixture x every declared policy through runner, simulator, verifier and replay against the committed hand-worked ledgers; a JSON-only agent; committed transcripts replay; each demo script regenerates the committed evidence byte for byte.
6. **Browser (Playwright).** Pages for v0.1 to v0.4 generated fresh into a temp directory, opened in Chromium, compared with the source JSON, no console errors; one small real screenshot per version.
7. **Defects.** For each real defect: a failing regression test first (`tests/test_s01_audit_regressions.py`), then the smallest fix, with its effect on committed evidence stated. Result: `results.md`.
8. **Evidence.** This directory: `plan.md`, `results.md`, `tests.log`, `mutation-fuzz-summary.md/.json`, `s01-3-assessment.md`, `screenshots/`.
9. **Run.** Full suite passes locally; total runtime stated in `results.md`. PR to `main`, not merged.

## Rules kept

- Old versions are not rewritten. The only source edits are minimal defect fixes in the four verifiers and in the v0.1 scripted policy, each pinned by a regression test; committed evidence for v0.1 to v0.4 regenerates byte for byte after them (an end-to-end test checks it).
- New helper modules and a new timeline-page script are added beside the old ones.
- The verifier stays independent of the simulator (the existing AST tests still pass).
- No paid model calls, no network, no credentials.
