# Proposed issue reconciliation and PR16 disposition

Date:2026-11-15
Status: **Proposal for review; no issue bodies, issue states, implementation branches or PR merges changed by this document.**

Read the [vision](../../vision.md), [alignment audit](../audits/2026-11-15-alignment-audit.md) and [dynamic acceptance scenario](../acceptance/dynamic-supplier-delay-v0.1.md). The latest instruction authorizes preparing this review package, not implementing another milestone.

## Scenario hierarchy and technical work

The [scenario map](../acceptance/scenario-map.md) links end-to-end business scenarios to their subscenarios. S01 supplier delay is the first detailed proposal. The user additionally requested S02 direct-material buying, S03 S&OP plan-to-action and S04 production-plan-to-schedule-to-manufacture-to-plan-comparison coverage; those are outlines to refine. DYN01–DYN05 below enable S01 and are mapped to S01.1–S01.6 there. They do not claim to implement S02–S04.

Preserve the broader scenario hierarchy when editing issues: technical completion alone cannot accept a parent scenario, and future upstream/downstream chains must share actual business state.

## 1. Decision sequence

1. Review and revise the concrete acceptance scenario.
2. Accept its behavior and assumptions as the planning baseline.
3. Apply the issue revisions below and create only the missing dynamic work packages.
4. Reconcile PR16 with current main, preserving vision/audit notices and accurately labeling static work; review its retained components and rerun checks.
5. Merge reconciled reusable infrastructure if acceptable; this does not close the dynamic milestone.
6. Build and demonstrate the dynamic episode against the accepted gates.
7. Perform business validity review and model evaluation before further teacher-corpus collection.

Do not merge PR16 automatically because historical tests passed, and do not discard useful code solely because its scope was narrower.

## 2. Existing issue-by-issue proposal

| Issue | Preserve | Proposed revision / priority | Required evidence or dependency |
|---|---|---|---|
| #1 Epic | Historical progress and original links | Revise objective to first dynamic situation demonstration; separate static foundations from missing dynamics | All G1–G9 in accepted scenario; dynamic completion cannot be inferred from #2–#11 closure |
| #2 Reference cases, closed | Static rules/fixtures/review status | Keep closed for historical static scope; label explicitly | New dynamic fixture expectations belong in DYN02, not a retroactive claim that #2 covered them |
| #3 Package/schemas, closed | Validation/package/CI | Keep closed; reuse contract conventions | Event, clock, PO, production and service contracts designed under DYN01 |
| #4 Checker, closed | Static allocation checks | Keep closed for static scope | Dynamic invariants and trajectory checks under DYN04 |
| #5 Solver, closed | Static solver/heuristic | Keep as a scoped auxiliary baseline | Three sequential fixture policies belong in DYN02; no perfect-future-information advantage |
| #6 Environment, closed | Reset/query/logging interface | Keep closed with explicit “static recommendation environment” description | Operational transitions under DYN01/DYN03 |
| #7 Lineage boundaries, open | Private/public separation and regression tests in PR16 | Accept only its static infrastructure scope after PR review; retain future event/scenario ancestry extension | No claims that three static templates validate broad holdout generalization |
| #8 Generator, open | Snapshot generator and public fixtures | Rename/describe as static procurement instance generator; exclude from dynamic completion | Dynamic variation comes after deterministic episode proof, not before |
| #9 Runner, open | Action/observation capture and replay code | Retain as runner infrastructure; defer real-adapter priority until tools are aligned | DYN03 extends time/event integration without exposing hidden state |
| #10 Admission/export, open | Serialization, tamper checks and split filters | Retain engineering scope; static exports are test demonstrations | DYN04/DYN05 add dynamic outcome admission |
| #11 Smoke, open | Recorded100-case experiment and costs | Clarify title to “Run static procurement pipeline integration smoke”; remove implied scale-readiness conclusion | Historical100/60 results remain unchanged; not a dynamic or LLM acceptance gate |
| #12 Fine-tuning plan, open | Long-term experiment intent | Defer behind accepted dynamic demonstration, practitioner review and actual teacher-pilot evidence | DYN05 →#17/#19 →#20 →#12; no fine-tuning execution automatically authorized |
| #13 Workflow expansion specs, open | Broader replenishment/P2P/disruption ambition | Defer breadth expansion; minimum time/disruption behavior moves into core DYN work | Do not keep first-world dynamics as optional later expansion |
| #14 Benchmark/scaling, open | Independent benchmark and scale goals | Defer production decisions until domain/model/learning evidence exists | DYN05, #17, #19, #20, #12; actual completed training results still required before scale claims |
| #17 Practitioner review, open | Need for real business review | Start with honest current-state and proposed dynamic rules packet; require review of material assumptions | Review packet can be prepared during planning; signoff requires a real reviewer, not an agent |
| #18 Real-LLM adapter, open | Provider integration/budget controls | Defer implementation priority during reconciliation; retarget to accepted dynamic tools | DYN03 interface and DYN05 offline demonstration; no paid call without model/credentials/spend envelope |
| #19 Real-LLM evaluation, open | Small diagnostic development evaluation | Retarget from static snapshots to accepted dynamic scenarios; label any auxiliary static testing | DYN05 plus #17 and #18; sealed cases remain untouched |
| #20 Teacher collection, open | Verified collection and cost/yield audit | Hold collection until dynamic pipeline and domain/model readiness are established | DYN05, #17, #19; exact pilot size and budget separately recorded |

The proposed new issue IDs below are planning identifiers, not already-created GitHub numbers. Closed issues remain closed for their actual historical scope; their old evidence is not erased.

## 3. Missing dynamic work packages, proposed only

### DYN01 — Specify and implement the deterministic operational state kernel
- Prerequisite: user-accepted DYN-ACCEPT-01; review PR16 reuse/interface decision.
- Plan first: version initial world, event calendar/order, clock, PO lifecycle, production reservations/completions, shipping, budget and penalties.
- Build: reset and advance-day transitions with exact-once receipt/commitment execution, coherent inventory and customer order state.
- Verify: hand-worked state checkpoints, event ordering, idempotence and invalid-action nonmutation.
- Evidence: G1–G4 and G7; state/event logs and tests. This package does not claim full domain realism.

### DYN02 — Add the public situation fixture and three sequential baseline policies
- Prerequisite: DYN01 contracts and scenario tables fixed.
- Build: five-day supplier-delay fixture; maintain/expedite/alternate policies; independent hand-calculated expected ledgers.
- Verify: all table quantities and costs, nonidentical consequences under the same event conditions, equal visibility rules.
- Evidence: G3/G5; policy traces and scorecards. No LLM or general optimal-policy claim.

### DYN03 — Integrate operational tools, observations and multi-day runner
- Prerequisite: DYN01 and reviewed reuse of PR16 runner.
- Build: recovery commitments, daily production release, closing/advancing the day, sanitized notices and state observations.
- Verify: no hidden event answers, duplicate action protection, partial/error histories, replay, and observable action consequences.
- Evidence: G2–G4/G7/G8; actual tool transcript and state progression.

### DYN04 — Implement independent dynamic outcome and invariant checking
- Prerequisite: DYN01 contracts plus DYN02 expected ledger specification.
- Build: independent component/finished-goods balance, receipts, capacity, shipment/order, budget/penalty accounting and timing checks.
- Verify: inject impossible states, incorrect costs, premature receipts and tampered trajectories; valid alternative policies pass feasibility even when more costly.
- Evidence: G5–G8; independent verdicts against the simulator output, not the simulator's self-reported success.

### DYN05 — Demonstrate one complete dynamic episode and publish its evidence
- Prerequisites: DYN02, DYN03 and DYN04 completed and reconciled.
- Run: all three policies through actual operational tools and five-day execution.
- Verify: match accepted tables; replay full traces; show at least one readable episode and correct outcome admission.
- Evidence: all G1–G9, timeline/ledger/scorecard/raw checks and actual screenshots where available.
- Completion means one checked engineering demonstration. Practitioner validation, real-model ability and data usefulness remain separate gates.

These contracts allow DYN02/DYN03/DYN04 to proceed independently only after their respective prerequisite contracts are stable. Do not start parallel implementation against unreviewed invented interfaces.

### Gate-to-work mapping

| Gate | Primary proposed owner |
|---|---|
| G1 Initial world | DYN01 |
| G2 Time progression | DYN01, DYN03 |
| G3 Disruption/recovery | DYN01, DYN02, DYN03 |
| G4 State consequences | DYN01, DYN03 |
| G5 Policy differences | DYN02, DYN04 |
| G6 Independent checking | DYN04 |
| G7 Invalid actions | DYN01, DYN03, DYN04 |
| G8 Replay/episode data | DYN03, DYN04, DYN05 |
| G9 Honest demonstration | DYN05 |

## 4. PR16 review checklist before merge

PR16 currently contains static lineage/generation/runner/admission infrastructure and historical evidence. It does not implement DYN01–DYN05.

- Update/rebase or merge current main into the branch without overwriting vision.md, audit notices or the status correction.
- Label the generator, tests, records and smoke report as static engineering artifacts.
- Review runner, lineage, export and admission for reuse; preserve small prototype modules rather than pretending they are dynamic implementations.
- Reconcile README/progress contradictions and the old “next work” sequence.
- Clarify auto-close references: #7–#11 may close only for their explicit static engineering scope; closing them cannot close the dynamic acceptance milestone or validate the corpus.
- Retain raw historical results and limitations; do not rewrite them as simulated business outcomes.
- Rerun relevant tests on the reconciled head, observe CI, and inspect the resulting diff.
- Obtain explicit merge acceptance. Neither this proposal nor scenario approval automatically merges PR16.

## 5. How to keep future work aligned

Each issue should link its requirement/gate, intended observable behavior, prerequisite, assumptions, artifact, negative cases and exact completion evidence. Its result must separately state implemented, tested, practitioner-reviewed and demonstrated model value.

Before expanding volume or breadth, inspect an actual episode rather than only counts or screenshots. If a gate is changed or deferred, record it as a scope decision for user review.

## 6. Review requested

The concrete decision is whether DYN-ACCEPT-01 represents the intended first demonstration and which assumptions should change. After that decision, apply a single coherent issue revision and review PR16 accordingly.

No new technical work, paid calls, corpus collection or GitHub issue mutations are performed by this documentation proposal.

