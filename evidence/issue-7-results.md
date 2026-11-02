# Issue 7 results

Implemented deterministic pre-expansion ancestry registry, cross-split exact/structural checks, semantic text-overlap flags with recorded adjudication, allowlisted agent metadata and training-only export guard. Private storage rejects repository roots, traversal and symlink writes and uses owner-only permissions. Documentation describes conservative fingerprint limitations and the distinction between tool visibility and process isolation.

Validation: `PYTHONPATH=src python -m unittest discover -s tests -p test_lineage.py -v` — 5 tests pass. Coverage includes shared ancestry and conflicting split joins, ID-renamed duplicates, numeric structural variants, non-overridable critical overlap, reviewer requirements, private path/symlink rejection, file permissions, metadata leakage and development/evaluation export rejection. Temporary private test data was created outside the repository and cleaned automatically.

No private evaluation cases or expected answers were added to the repository. No claim of general semantic deduplication or adversarial Python sandboxing is made.
