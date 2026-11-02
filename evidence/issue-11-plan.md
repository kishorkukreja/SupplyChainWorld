# Issue 11 plan

Run an actual offline smoke experiment over approximately 100 generated procurement instances. Freeze lineage-separated train/dev/evaluation assignment and hash manifest before any baseline execution. Store evaluation instances, answers, trajectories, and reproducibility seeds only in `/workspace/SupplyChainWorld-private`; publish aggregate counts and manifest hashes without private case reconstruction data.

Use the generation, lineage, runner, checker, replay, and admission APIs from issues 7–10. Run reference and heuristic baselines plus deterministic agents through the tool environment; admit training trajectories with replay and checker gates, export accepted train examples, and account for every rejection. Report split/outcome/variation coverage, baseline status, tool calls, zero offline token use and zero provider cost. This verifies software integration and deterministic baselines, not model success.

Implement `scripts/run_smoke.py`, focused integration tests, and `docs/smoke.md`. Capture actual private experiment artifacts and a sanitized public aggregate report in `evidence/issue-11-results.md`; send the resulting paths to evidence review for screenshot capture.
