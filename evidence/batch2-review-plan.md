# Batch 2 independent review plan

Review issues #7–#11 against their contracts and tests after implementations arrive. Independently exercise ancestor split isolation, bounded generation, agent answer isolation, admission integrity, deterministic replay and smoke artifacts. Inspect public exports for evaluation inputs, expected answers and private logs. Add integration tests in `tests/test_batch2_integration.py` and a sanitized review command in `scripts/review_batch2.py`.

Capture actual final passing commands through `scripts/capture_evidence.py` for `issue-7-lineage`, `issue-8-generation`, `issue-9-runner`, `issue-10-admission`, `issue-11-smoke`, `batch2-integrated`, and independent review. Preserve the evidence index and record limitations in `evidence/review-batch2.md`. Freeze reviewed files after final evidence and notify coordinator. Screenshots show command evidence, not a product UI.
