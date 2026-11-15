# Alignment audit: original ask, backlog and implementation

Date: 2026-11-15
Type: Requirements-alignment and repository-evidence audit, not a new business-validation study.
Finding: Useful static procurement infrastructure exists, but the dynamic world/situation lifecycle clarified by the user has not been implemented. Existing downstream collection and model-testing issues do not resolve that omission.

## 1. Evidence boundaries

Inspected main at commit `18c28632934af4246d8ebd4000c4d25bde23136e` and open PR #16 at head `451788d1a2527256c8abd67b34467bbabb2cd0ff`, repository documents, relevant implementation files, existing experiment reports, and all 18 actual issue bodies (#1–#14, #17–#20). PR #15 is merged; PR #16 is open and unmerged. [Issue/PR snapshot](2026-11-15-issue-snapshot.json) preserves the audit-time state, bodies and commit IDs.

The original request and subsequent clarifications are available in this conversation. They were not originally preserved as a verbatim requirements contract in the repository. The requirements below distinguish those sources from assistant-authored design decisions.

This audit inspects source and existing evidence; it does not claim a fresh rerun of the historical 100-case experiment or 57-test suite. The original private 60-record export and sealed case data were not available in this restarted workspace. A separate public reference-case record was regenerated earlier in this conversation; it is not proof of recovery of that original export.

## 2. What the user asked for

### Original request
- Research WorkFactory and related papers/methods, including environment/solver-based approaches.
- Determine how to produce solid, valid, realistic synthetic supply-chain examples across many functions for fine-tuning; approximately 500,000 was a possible target, not a fixed initial quota.
- Establish a separate supply-chain evaluation dataset/benchmark where new models run in configured environments and are graded.
- Research first, then plan next steps; do not immediately generate the full dataset.

### Later user confirmations and clarifications
- Initial industry: discrete manufacturing and distribution.
- Preserve research/vision/progress, write the specification, and create dependent GitHub issues.
- Use GPT-6.1 Sol subagents and provide plans, implementation, verification and screenshots.
- The intended mechanism is to create a world, define its environment, simulate/run a situation within it, and derive verified experience from that process.

### Assistant-origin choices
The static single-period supplier-allocation milestone, the ten-case reference set, the 100-case smoke size and its 60/20/20 allocation, three split-specific templates, and the next-step LLM/teacher-collection sequence were assistant design decisions. They must not be attributed to the original request. The user authorized work against the issue backlog; that does not establish that every narrowing decision fulfilled the broader goal.

The initial prompt did not specify that every task must be dynamic, a simulator architecture, a time horizon or an exact disruption scenario. The later clarification makes a dynamic demonstration an essential alignment requirement now. Both statements can be true; this audit does not invent requirements retroactively.

## 3. Requirement-to-evidence matrix

“Partial” means useful evidence exists, but not enough to satisfy the user-level outcome. “Missing” means no implementing evidence was found in the inspected scope.

| ID | Requirement | Status | Evidence and practical limit |
|---|---|---|---|
| R1 | Research WorkFactory and similar environment/solver methods before implementation | Partial | [Research synthesis](https://github.com/kishorkukreja/SupplyChainWorld/blob/18c28632934af4246d8ebd4000c4d25bde23136e/research/2026-11-02-research-summary.md) compares methods and supply-chain benchmarks. No independent reproduction or complete feasibility validation of those methods was established. |
| R2 | Durable research, vision, PRD, spec and dependent issues | Met as artifacts; alignment defective | Files and issue bodies exist. Their presence did not ensure the implementation preserved the intended mechanism. |
| R3 | Initial discrete-manufacturing/distribution context | Partial | Supplier/component procurement is represented; no executing manufacturing/distribution network exists. |
| R4 | Coherent world grounded in reality | Partial | [World schema](https://github.com/kishorkukreja/SupplyChainWorld/blob/18c28632934af4246d8ebd4000c4d25bde23136e/src/supplychainworld/schemas.py#L76) contains supplier/item/stock/inbound/quote records with validation. It is a synthetic procurement snapshot, not a validated operational world; practitioner review is pending. |
| R5 | Executable agent environment | Partial | [Environment](https://github.com/kishorkukreja/SupplyChainWorld/blob/18c28632934af4246d8ebd4000c4d25bde23136e/src/supplychainworld/environment.py#L9) implements reset, queries, clarification and submission. Recommendation submission is not purchasing execution. |
| R6 | Time and consequential business-state transitions | Missing | [Spec](https://github.com/kishorkukreja/SupplyChainWorld/blob/18c28632934af4246d8ebd4000c4d25bde23136e/spec.md#L21) restricts the milestone to one period; line 32 defers multi-period dynamics. [Environment](https://github.com/kishorkukreja/SupplyChainWorld/blob/18c28632934af4246d8ebd4000c4d25bde23136e/src/supplychainworld/environment.py#L133) returns the unchanged as_of date. |
| R7 | Introduce and run situations/disruptions over time | Missing | No scheduled delay injection, event processing, material consumption, rescheduling or downstream consequence engine was found. Varied static constraints are not an evolving disruption. |
| R8 | Agent acts, observes consequences and adapts | Partial | Query/submission interaction and replay exist. No operational action effects or subsequent business observations drive replanning. |
| R9 | Independent valid-task and outcome verification | Partial | Static allocation checks, small exact solver and replay provide engineering evidence. No dynamic mass-balance, event-order, trajectory-outcome or practitioner-validity evidence exists. |
| R10 | High-quality supply-chain training corpus | Partial infrastructure; product missing | PR #16 can export checked static demonstrations. It reports 60 train-split engineering records from a scripted optimizer. No accepted domain corpus, teacher-LLM collection or learning improvement is established. |
| R11 | Broad functional task coverage | Missing beyond procurement prototype | Other functions are named in documents but not implemented as full workflows. This is acceptable initial breadth reduction only if reported accurately; it is not broad coverage. |
| R12 | Independent runnable model benchmark | Partial infrastructure; product missing | Split/replay/report code exists in PR #16. No real-LLM experiment, validated domain benchmark, multi-release comparison or broad independent holdout evidence is recorded. |
| R13 | Separation of training and evaluation | Partial | PR #16 implements lineage/export checks and reports 60/20/20. [Smoke report](https://github.com/kishorkukreja/SupplyChainWorld/blob/451788d1a2527256c8abd67b34467bbabb2cd0ff/evidence/issue-11-results.md) discloses three templates with split-specific item cardinalities. This is narrow synthetic separation, not demonstrated generalization. |
| R14 | Possible 500,000 useful examples | Not attempted; appropriately uncommitted | No quality or economic basis yet supports scaling. The 60 records are not evidence toward that quota. |
| R15 | Plans, agents, tests and screenshot proof | Met within narrow prototype | [Batch evidence](https://github.com/kishorkukreja/SupplyChainWorld/blob/451788d1a2527256c8abd67b34467bbabb2cd0ff/evidence/batch2.md) records the work and historical checks. Screenshots and tests validate the scoped implementation, not R6–R7 or domain realism. |

## 4. Where scope drift entered

1. The [PRD operational simulator and F04](https://github.com/kishorkukreja/SupplyChainWorld/blob/18c28632934af4246d8ebd4000c4d25bde23136e/PRD.md#L66) explicitly describe time advancement, demand/arrivals/capacity/disruptions and delayed consequences.
2. The [implementation spec](https://github.com/kishorkukreja/SupplyChainWorld/blob/18c28632934af4246d8ebd4000c4d25bde23136e/spec.md#L17) redefined first completion around a replayable, exportable procurement recommendation. It explicitly deferred the dynamics needed for the intended world demonstration.
3. Issues #2–#11 decomposed that narrow spec. They were implemented and verified against it; no acceptance gate required a complete dynamic situation.
4. PR #16 emphasized record generation/export and a 100-case software smoke experiment before an observable world/simulation demonstration existed.
5. Later additions #17–#20 improved practitioner and model validation but still placed teacher collection ahead of filling the missing dynamics.
6. Status reporting highlighted test counts and exported records without consistently stating that business state and time were static. The conversation and some evidence files disclosed the limitations, but that did not repair the milestone misalignment.
7. Documentation drift compounded the problem. Main's [progress file](https://github.com/kishorkukreja/SupplyChainWorld/blob/18c28632934af4246d8ebd4000c4d25bde23136e/progress.md) contains mutually inconsistent historical status statements, including both implemented code and “No environments…implemented.” The stored roadmap omitted later #17–#20 changes.

Responsibility: the assistant selected and promoted the narrower implementation scope without adequately validating that it met the user's goal. The user did not introduce a new objective when asking about simulation.

## 5. What the code actually does

The environment documents that submissions are recorded, not executed. Available tools read requirements, inventory, suppliers, quotes and policy, request clarification, and submit a recommendation/exception. Its state_version increments track accepted interactions; they do not represent inventory consumption, new purchase-order arrivals or production execution. Its simulated_time is copied from world.as_of and never advanced by an event engine.

PR #16's [OfflineVisibleAgent](https://github.com/kishorkukreja/SupplyChainWorld/blob/451788d1a2527256c8abd67b34467bbabb2cd0ff/src/supplychainworld/runner.py#L146) reconstructs a World from returned records and invokes solve_reference. There is no teacher LLM in that experiment. The [generator](https://github.com/kishorkukreja/SupplyChainWorld/blob/451788d1a2527256c8abd67b34467bbabb2cd0ff/src/supplychainworld/generation.py) constructs constrained snapshots; it does not evolve a common operational world over multiple decision periods.

These are legitimate prototypes. Calling them a complete dynamic supply-chain environment would be inaccurate.

## 6. The 60-record result: correct interpretation

The [recorded report](https://github.com/kishorkukreja/SupplyChainWorld/blob/451788d1a2527256c8abd67b34467bbabb2cd0ff/evidence/issue-11-results.md) states:
- 100 static cases:60 train,20 development,20 evaluation.
- 634 tool actions;100 accepted/replayed scripted-agent episodes.
- 60 training-format records exported;40 protected records excluded.
- Zero provider calls, tokens and provider cost.
- Three lineage templates; limited generalization.
- Historical combined suite:57 tests passed.

This checks recording, verification, replay, split filtering and export serialization. It does not prove dynamic simulation, practitioner approval, LLM performance, teacher quality, scale readiness or fine-tuning improvement. “Training-format engineering demonstrations” is the appropriate current label. The original private records' present availability is not established.

## 7. Issue-by-issue disposition proposal

This section is an audit recommendation, not a silently applied replacement backlog. Issue bodies/states and PRs are preserved. Do not auto-resume the previous sequence from this table.

| Issue | Current state | Audit assessment | Proposed disposition after review |
|---|---|---|---|
| #1 Epic | Open | Describes static procurement completion and jumps to model/teacher work | Reconcile around the agreed dynamic acceptance demonstration; do not declare overall world complete. |
| #2 Rules/reference cases | Closed | Useful static cases; no practitioner endorsement | Keep historical completion and relabel static scope; extend scenarios only after dynamic rules are agreed. |
| #3 Schemas/CI | Closed | Reusable validation/testing scaffolding | Keep; inventory event, clock, resources and commitment schema gaps. |
| #4 Checker | Closed | Useful static business checker | Keep; add conservation/event/trajectory-outcome verification under a new agreed spec. |
| #5 Solver | Closed | Small-instance allocation baseline | Keep; separate static optimizer from information-equivalent sequential policy baseline. |
| #6 Environment | Closed | Query/submission interface, not operational simulator | Keep as static prototype; define executing transitions before representing dynamic completion. |
| #7 Lineage/boundaries | Open, PR #16 | Useful separation machinery | Review/retain with static scope stated; extend lineage to scenario/event ancestry before dynamic collection. |
| #8 Generator | Open, PR #16 | Generates constrained snapshots | Preserve; do not treat as dynamic world/situation generator. |
| #9 Runner | Open, PR #16 | Records observable actions/replay | Preserve; extend only against agreed clock/event/action semantics. |
| #10 Admission/export | Open, PR #16 | Useful serialization and tamper checks | Keep as engineering work; dynamic outcome admission remains missing. |
| #11 Smoke | Open, PR #16 | Software pipeline smoke, not model/world validation | Relabel result accurately; it cannot unlock broad collection by itself. |
| #12 Fine-tuning plan | Open | Premature without aligned simulator and audited demonstrations | Defer execution-oriented planning until the dynamic demonstration and validation gates are agreed. |
| #13 Other workflow specs | Open | Lists missing dynamics as later expansion | Reconcile: minimum dynamics needed for the first demonstration are core, not optional breadth. |
| #14 Benchmark/scaling | Open | Goal retained but prerequisite evidence insufficient | Keep long-term aim; no scale authorization from static scores. |
| #17 Practitioner review | Open | Needed, but current packet covers static procurement | Prepare an honest current-state packet; extend to proposed dynamic assumptions. A real reviewer must provide signoff. |
| #18 Real-LLM adapter | Open | Potentially reusable but does not close dynamics gap | Defer implementation priority during audit; later tie to aligned environment and budgets. |
| #19 Real-LLM evaluation | Open | Evaluates static development tasks | Do not present as the primary next milestone until an aligned environment is demonstrated. Static diagnostic use requires explicit labeling. |
| #20 Teacher collection | Open | Risks producing more static records | Hold further collection until the agreed dynamic demonstration and validity checks pass. |

No code should be discarded solely because of this finding. Preserve PR #16 as reviewable engineering work; merging or rejecting it is a separate user decision.

## 8. Proposed recovery gate

Next action is to review this audit and agree on ONE observable dynamic acceptance scenario before rewriting technical scope or launching more agents.

A candidate, not yet approved: a small manufacturer with suppliers, components, inventory and customer commitments runs for a short horizon; a supplier delay becomes visible; an agent acts; scheduled events and material/resource constraints determine consequences; the agent can react again. Compare a declared baseline under the same exogenous events.

Acceptance evidence must show:
1. Initial entity state, rules, visibility boundaries and assumptions.
2. Clock advancement and event order.
3. The disruption's occurrence and what the agent actually observes.
4. Operational actions changing future state rather than merely recording recommendations.
5. Before/after inventory, arrivals, resource/production or commitment state.
6. At least two meaningfully different action policies with verifiably different consequences where the situation permits.
7. Conservation and constraint checks, reproducible replay and a correctly labeled outcome scorecard.
8. A traceable training/evaluation experience from the episode, with hidden answers excluded.

Exact counts, horizons, action sets, metrics and review method remain proposals. “All tests pass” alone does not accept this gate.

## 9. Safeguards and artifact changes

Published with this audit:
- Updated vision.md states user intent, mechanism, current limitations and alignment rules.
- README links to the audit and warns that the historical spec/sequence is unreconciled.
- progress.md records the verified repository status and pause while preserving historical detail.
- spec.md and roadmap.md receive a visible audit notice; their technical content is not silently rewritten.
- This issue/PR snapshot and pinned source links make the finding reviewable.

Not performed: implementation, new dataset collection, new issue creation, issue closure/reopening, PR merge, simulator architecture selection, paid calls or renewed claims about training value. The user must be able to assess the correction before substantial work resumes.

## 10. Audit verification record

Checked that the snapshot contains 18 issues, the report covers all 18 dispositions and 15 requirement mappings, and PR #16 was unmerged at capture. These are document-consistency checks, not product tests. Source inspection used the pinned commits above. No historical test run was rerun for this audit.

Document HTML previews were prepared locally. Screenshot capture was attempted, but Chromium navigation to the local document was blocked by administrator policy; no screenshot was captured or claimed for this audit. The published Markdown and pinned evidence are the reviewable proof.
