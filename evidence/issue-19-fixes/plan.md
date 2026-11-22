# Issue #19 fixes: plan

Scope set by the owner: fix exactly the three findings of the #19 diagnostic, then stop. No live model call, no rerun of the diagnostic (the owner reruns later with more models and enhanced tests). Mocked transports only. evidence/issue-19/ and every frozen earlier version are untouched.

1. Task defect (S01 world exposed a scenario name that gives away the outcome). New version beside the old: S01 v0.5 (`dynamic_v5`, `agent_runner_v5`, `dynamic_verifier_v5`, `dynamic_demo_v5`, `fixtures/dynamic/v0.5/`). The scenario id inside the world must be an opaque label (`scn-` plus 8 hex characters) derived from the visible parameters only, so the paired warned scenarios share one label. Same rules and numbers as v0.4.
2. Harness gap (rule stated nowhere). `agent_runner_v5.RULES` holds one sentence per enforced rule; the prompt and tool descriptions of the new harness are built from it; a test ties every rejection reason found in the source to a sentence.
3. Submission schema. `schemas_v121`: one exact shape per answer kind, extra or missing fields rejected with a clear message, no repair. The new harness offers one tool per kind and grades strict-first.

The first diagnostic harness is frozen (its hashes are in its manifest), so the next run uses `eval19_v2.py` and `scripts/run_eval19_v2.py`, with a bumped manifest (`eval19-manifest-2`, harness version `eval19-2`, predecessor hashes recorded). The new manifest is a draft: the owner sets the roster and commits it before any call.

Browser tests: no user-visible page or report changed, so none were added.
