# Parallel implementation plan

User requested GPT-6.1 Sol agents, issue planning, implementation, verification, and screenshots of proof.

## Work allocation

| Workstream | Issue | Prerequisite | Output |
|---|---|---|---|
| Business rules and fixtures | #2 | Specification | Playbook, ten synthetic cases, arithmetic checks |
| Package and contracts | #3 | Agreed #2 business fields | Validated schemas, package, offline CI |
| Independent grading | #4 | #3 contract | Independent business checker and fault tests |
| Reference optimization | #5 | #3 contract | Exact bounded solver, heuristic, status tests |
| Procurement environment | #6 | #3 contract | Sanitized tools, state reset, replay, artifact rendering |
| Independent evidence review | Cross-cutting | Actual outputs | Raw logs, command metadata, rendered HTML screenshots |

Agents may plan/scaffold before prerequisite completion. Dependent implementation uses explicitly agreed contracts and remains provisional until upstream tests pass. Integration review checks all outputs together. Practitioner review is pending and will not be fabricated.

## Evidence standard

Each issue records a plan and a result report. Screenshot pages render actual captured command output, with exit status, timestamp and log hash. Raw logs and executable checks remain the authoritative evidence. Screenshots do not establish business realism or substitute for practitioner review.

## Publication

Publish changes on a review branch and open a PR with evidence links. Preserve open issue status for acceptance review. Do not merge, pay for model runs, publish private benchmark data or claim training improvement in this implementation pass.

## Environment note

Shell access to the GitHub proxy failed. The local checkout was initialized from the previously saved planning files; publication uses the GitHub connector and preserves the remote base tree. No remote history is overwritten.
