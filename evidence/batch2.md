# Batch 2: generated episodes and verified training export

This batch implements issues #7–#11 after the user merged PR #15. Six GPT-6.1 Sol agents planned, implemented and independently reviewed the work. Plans preceded implementation; dependent modules used agreed contracts before integration tests.

| Issue | Plan | Results | Actual screenshot |
|---|---|---|---|
| #7 Lineage and boundaries | [Plan](issue-7-plan.md) | [Results](issue-7-results.md) | [Screenshot](screenshots/issue-7-lineage.png) |
| #8 Generation | [Plan](issue-8-plan.md) | [Results](issue-8-results.md) | [Screenshot](screenshots/issue-8-generation.png) |
| #9 Agent runner | [Plan](issue-9-plan.md) | [Results](issue-9-results.md) | [Screenshot](screenshots/issue-9-runner.png) |
| #10 Admission and export | [Plan](issue-10-plan.md) | [Results](issue-10-results.md) | [Screenshot](screenshots/issue-10-admission.png) |
| #11 Offline smoke | [Plan](issue-11-plan.md) | [Results](issue-11-results.md) | [Screenshot](screenshots/issue-11-smoke.png) |

See the [combined suite](screenshots/batch2-integrated.png), [independent review](review-batch2.md), and [independent review screenshot](screenshots/batch2-independent.png). Each capture has matching raw logs, HTML and JSON metadata in this directory. These are screenshots of actual recorded command results, not a product UI.

## Meaning of the experiment

The offline smoke generates 100 cases, runs a scripted visible-input optimizer through actual tools, independently checks submissions, replays trajectories and exports train-only demonstrations. Development and evaluation records remain outside the public repository. The experiment tests pipeline integration. It does not measure an LLM, fine-tuning gains, broad supply-chain competence or private benchmark validity.

Only a small set of synthetic world structures is represented. Practitioner review remains pending. The in-process adapter boundary is not a hostile-code sandbox, timeouts are cooperative, the exact solver is bounded enumeration, and infeasibility verification currently covers capacity certificates. Semantic overlap flags require explicit review rather than automatic acceptance.
