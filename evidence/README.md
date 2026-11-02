# Proof of work: first implementation batch

Six GPT-6.1 Sol subagents implemented and independently reviewed issues #2–#6. The root agent integrated the work, inspected code and a screenshot, reran the combined suite, and requested a boundary-validation fix before publication.

| Issue | Plan | Results | Actual screenshot |
|---|---|---|---|
| #2 Reference cases | [Plan](issue-2-plan.md) | [Results](issue-2-results.md) | [Screenshot](screenshots/issue-2-reference-cases.png) |
| #3 Contracts | [Plan](issue-3-plan.md) | [Results](issue-3-results.md) | [Screenshot](screenshots/issue-3-contracts.png) |
| #4 Checker | [Plan](issue-4-plan.md) | [Results](issue-4-results.md) | [Screenshot](screenshots/issue-4-verification.png) |
| #5 Solver | [Plan](issue-5-plan.md) | [Results](issue-5-results.md) | [Screenshot](screenshots/issue-5-solvers.png) |
| #6 Environment | [Plan](issue-6-plan.md) | [Results](issue-6-results.md) | [Screenshot](screenshots/issue-6-environment.png) |

- [Combined suite screenshot](screenshots/integrated-suite.png) and [raw test output](integrated-suite.log).
- [Independent review screenshot](screenshots/independent-review.png) and [raw output](independent-review.log).
- [Rendered evidence index](index.html), [capture script](../scripts/capture_evidence.py), and [execution plan](execution-plan.md).

Screenshots are real Chromium captures of rendered command-output reports. They show the command, captured exit status, UTC timestamp and output hash. They are evidence pages, not screenshots of a product UI or externally executed GitHub Actions. Matching JSON and raw log files are retained beside each HTML report.

## Current limits

All ten reference cases are synthetic and public. Practitioner signoff is pending. Schema validation and local tests establish specified behavior, not broad operational realism. The solver uses bounded exact enumeration and reports unresolved timeouts; it is unsuitable for large industrial instances. The checker currently certifies capacity-based infeasibility, conservatively rejecting unsupported broader claims. No model fine-tuning, paid teacher run, sealed benchmark release or measured learning gain is included.
