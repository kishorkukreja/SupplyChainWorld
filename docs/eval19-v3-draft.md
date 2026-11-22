# eval19-3 DRAFT: harness materials for S01 v0.6 (not run)

Status: DRAFT. Nothing here has been run with a model, nothing is pre-registered, and no live call is made by any file in this
change. The owner runs the diagnostic later. Free models only, USD 0 ceiling, through the existing adapter. All business numbers are
PROVISIONAL, needs practitioner value. No practitioner has reviewed anything (owner review only, not independent). No claim about
model ability is made.

## What is frozen and untouched

- `evidence/issue-19/` (the first diagnostic) and its manifest, which hashes `eval19.py`, `scripts/run_eval19.py` and
  `dynamic_verifier_v4.py`, are not edited. `tests/test_eval19_v2.py` still checks every one of those hashes, and
  `tests/test_eval19_v3.py` checks them again.
- `eval19_v2.py` and `scripts/run_eval19_v2.py` (the next-run harness on the v0.5 world) are not edited either. Whether the owner runs
  eval19-2 or this draft is the owner's choice.

## What the draft adds (new files only)

| File | What it is |
|---|---|
| `src/supplychainworld/eval19_v3.py` | S01 prompt, tool descriptions, tool schemas, agent, episode runner, grader and a draft manifest builder for the v0.6 world |
| `tests/test_eval19_v3.py` | offline tests: every v0.6 refusal reason maps to a stated rule; 25 episodes through a mocked model; draft manifest checks |
| `src/supplychainworld/dynamic_v6.py`, `agent_runner_v6.py`, `dynamic_verifier_v6.py`, `dynamic_demo_v6.py` | the v0.6 world, runner and rules table, rebuilt independent checker, demonstration packet |

## What changes for the model compared with eval19-2

1. World: v0.6 (opaque scenario label as in v0.5, plus a conventions block in the visible rules, plus exact-once purchases without an
   action id, plus the rebuilt independent checker).
2. Prompt: built from `agent_runner_v6.RULES_V6`. It adds one sentence for each convention (same-day use of receipts, when production
   completes, when shipping starts and in what order, the unit of the penalty rate, the cap, cancellation, repeated purchases, what is
   only a plan before a firm notice) and restates the once-only rule for the case of no action id.
3. Tool schema: `commit_recovery` may carry an optional `action_id` argument, which the agent forwards as the call's own `action_id`.
   Without one, a repeat of the same purchase on the same day is refused.
4. Static task: unchanged from eval19-2.

## Things the owner should know before running it

- The conventions block makes every observation larger (about 4 KB of text, roughly 1,000 tokens, in every observation and again in
  the system prompt). With the adapter's memory window of 8 this adds several thousand tokens to each request. Check it against the
  free models' context limits before the run.
- The scripted baselines and the mocked model never send an action id, so their results do not change from v0.5 to v0.6; the
  numbers of the five scenarios are identical (tested).
- A live model can still misread the block. The tests show that the numbers can be computed exactly from the view (S01.3), not that a
  model does so.

## Not done here, on purpose

The diagnostic was not run. No manifest was pre-registered. `eval19_v3.draft_manifest()` builds a draft that carries file hashes, the
prompt and the tool descriptions; it is not committed as a file because its hashes would go stale with any later edit.
