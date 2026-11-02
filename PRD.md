# PRD: Supply-chain training data factory and evaluation benchmark

Version: 0.1 — discussion draft  
Date: 2026-11-02  
Status: Research saved; product requirements drafted; implementation has not started.  
Confirmed pilot context: Discrete manufacturing and distribution.  
Source: [Research summary](research/2026-11-02-research-summary.md)

## 1. Product objective

Create a system that produces realistic, executable, independently verifiable supply-chain work. Use it to deliver two separate products:

1. **Training corpus:** verified demonstrations suitable for supervised fine-tuning of a tool-using supply-chain model, with a possible eventual target of 500,000 accepted task instances.
2. **Evaluation benchmark:** a versioned suite of environments, private tasks, graders, baselines, and reports for evaluating each new model under controlled conditions.

The shared asset is the business environment and verification infrastructure. Training and evaluation content must have separate provenance, selection, and release controls. The benchmark must measure operational competence, not merely familiarity with generated wording.

The 500,000 target is provisional. This PRD defines an example as a unique accepted task instance with at least one verified demonstration; multiple rollouts and training chunks do not increase that count. This counting convention remains a decision for the product owner to ratify.

## 2. Users and intended outcomes

| User | Need | Deliverable |
|---|---|---|
| Model-training team | Reliable domain demonstrations with reproducible tool behavior | Versioned training export, environment snapshots, provenance, dataset card |
| Evaluation team | Fair comparisons across new model releases | Model adapter, locked run configuration, private task suite, scorecard |
| Supply-chain experts | Inspect realism and correctness without reading infrastructure code | Review packet with source evidence, business rules, task, solution, grading rationale |
| Product/research owner | Decide whether to scale and where capability is missing | Coverage, quality, learning-curve, and cost reports |

Success requires both useful training gains and credible evaluation. A large corpus alone is not success.

## 3. Scope and explicit exclusions

### Pilot scope

Use discrete manufacturing and distribution scenarios containing suppliers, components, finished goods, facilities, warehouses, bills of material, capacity, orders, shipments, inventory, and commercial terms. Begin with four task families:

| Family | Work to perform | Primary deliverables | Verification |
|---|---|---|---|
| Supplier award allocation | Compare qualified suppliers and allocate volume under cost, lead-time, capacity, MOQ, and concentration constraints | Award allocation and evidence-backed recommendation | Independent cost/constraint checker; optimization baseline |
| Inventory replenishment | Choose orders or transfers across locations over a defined horizon | Replenishment decisions and supporting analysis | Inventory balance, lead-time behavior, service and cost measures |
| Purchase-to-pay exceptions | Reconcile PO, receipt, invoice, and contract; resolve or route discrepancies | Correct business state and concise exception explanation | Matching rules, approval policy, event sequence, unchanged unrelated records |
| Disruption replanning | Respond to a supplier delay, facility outage, or transport interruption | Feasible revised supply/production/allocation plan | Material and capacity feasibility, customer priorities, recovery and cost |

Include contract terms, quality eligibility, production constraints, logistics, and customer commitments when needed by these workflows. This does not constitute full coverage of those functions.

### Later coverage

Expand to detailed manufacturing scheduling, quality containment and recalls, sustainability accounting, transport execution, customer service, contract administration, and additional sectors after the pilot gates pass. Maintain a coverage register for sourcing, procurement, planning, inventory, manufacturing, quality, sustainability, logistics, customer service, resilience, and contracts.

### Excluded from the first release

- Live writes to production ERP, WMS, TMS, or supplier systems.
- A complete enterprise digital twin or physical factory control.
- Exhaustive jurisdictional, commodity, or industry coverage.
- A commitment to generate 500,000 instances immediately.
- Reinforcement-learning training infrastructure; preserve compatible trajectories, but establish supervised fine-tuning value first.
- A public leaderboard or unrestricted dataset publication before quality and source-use review.
- A browser/UI interaction track; start with files and typed tools to reduce unrelated interface variance.

## 4. Product design

### Three environment types

1. **Analytical workspace:** files, tables, quotations, contracts, policies, and requested deliverables.
2. **Stateful business system:** controlled tools for querying and changing operational records.
3. **Operational simulator:** transitions through time with demand, arrivals, capacity, disruptions, and delayed consequences.

A structured world is authoritative. Render documents and tool observations from this world, recording any deliberate discrepancy separately. Do not generate related records independently without reconciliation.

The world model must capture identifiers, units, currencies, calendars, effective dates, entity relationships, inventory balances, capacities, commercial terms, and visibility rules. Model only the subset required by each task. Document simplifying assumptions, including event order, backorders versus lost sales, expiry, demand observability, and cost treatment.

Separate **world truth**, **agent-visible information**, and **private grading evidence**. Hidden future events can drive simulation, but hidden rules cannot impose obligations the agent was never told or able to discover.

### Task specification

Every task package must include:

| Component | Required content |
|---|---|
| Identity | Task ID, family, version, world ID, lineage ID, split |
| Business context | Role, objective, authorized actions, horizon, constraints |
| Environment | Initial snapshot, tool schemas, runtime version, event schedule/seed |
| Inputs | Visible files, source references, policies, evidence locations |
| Information requirements | Supplied, discoverable, intentionally unknown, and solver-derived facts |
| Expected behavior | Complete, clarify, escalate, or demonstrate infeasibility |
| Verification | Deterministic checks, tolerances, rubric, baseline, critical failures |
| Provenance | Source permissions, hashes, generator versions, edits, reviewer records |
| Difficulty/coverage | Cross-functional dependencies, horizon, ambiguity, network and constraint complexity |

Private reference solutions and graders must be inaccessible to the agent. Optimization tasks may have multiple valid answers; reference output equality is not the default grading method.

## 5. Functional requirements

| ID | Requirement | Acceptance evidence |
|---|---|---|
| F01 | Maintain a practitioner-reviewed task and capability taxonomy | Four pilot family specifications with intended skills, variants, assumptions, and baseline |
| F02 | Track real evidence and synthetic facts separately | Every admitted task has source/permission metadata and synthetic-data labels |
| F03 | Generate internally consistent states and supporting artifacts | Referential, unit, date, material-balance, and financial checks pass |
| F04 | Support reset, observation, action, and time advancement | Identical recorded actions replay to identical states under pinned configuration |
| F05 | Build tasks from objectives or authentic evidence | Every required output maps to available premises or explicitly expected clarification |
| F06 | Probe and repair defective tasks | Repairs recorded; objective and essential work preserved; fresh probe after repair |
| F07 | Verify business correctness independently | Feasibility and calculations checked independently of teacher output and solver formulation |
| F08 | Collect isolated teacher demonstrations | Teachers see only permitted inputs; logs include tool observations, actions, outputs, and checks |
| F09 | Export usable fine-tuning data | Target trainer can load sample export; role/tool serialization and loss masking inspected |
| F10 | Protect evaluation from training | Split manifests and lineage checks prevent training exports from including held-out content |
| F11 | Run multiple models with fixed configuration | At least three distinct model configurations complete the adapter smoke test |
| F12 | Produce reproducible diagnostic reports | Run ID links configuration, costs, failures, state evidence, grades, and task versions |
| F13 | Support expert adjudication and corrections | Reviewer can accept, reject, or revise a task/grader with reasons and version history |
| F14 | Track cost and stop limits | Stage-level usage, retries, acceptance yield, and configurable spend ceilings |

## 6. Validity and grading requirements

Verification has five layers: business realism, sufficient information, numerical consistency, execution fidelity, and grading reliability.

Use deterministic checks for calculations, hard constraints, permissions, and state changes. Use evidence-linked rubrics for judgment and explanation. LLM judges may assist qualitative grading, but cannot override failed hard constraints. Record judge versions, calibrate against experts, and audit style bias.

For optimization, report feasibility first, then objective value and gap to a certified optimum or documented best-known solution. If a solver times out, retain its bound/status and avoid labeling the result optimal. For sequential decisions, compare against policies with the same available information; label perfect-foresight solutions only as upper bounds.

Final state checks must be supplemented by event-history checks where sequence matters. Releasing a quality-held lot and later restoring the hold must not pass simply because the final state looks correct.

Intentional ambiguity and infeasibility require explicit task types. A correct request for missing freight terms, justified escalation, or demonstrated infeasibility can be successful behavior. Accidental missing evidence is a generator defect.

Validate the graders with deliberately incorrect outputs, alternative valid solutions, and metamorphic checks—for example, relabeling supplier IDs must not change the economic result. Do not rely only on tests generated by the same model that wrote the task.

## 7. Training product requirements

The production pipeline is:

`reviewed family → split assignment → world and evidence → task and verifier → probe/repair → independent teacher → replay/verification → admission → export`

Each admitted demonstration includes its original context, observations, tool actions, final artifact/state, and checks. Store failed runs for diagnosis separately. Verified recovery trajectories are eligible; imitation targets must not present failed behavior as a successful answer.

Track unique families, worlds, task instances, demonstrations, sequences, and tokens separately. Apply exact and semantic deduplication and lineage caps to avoid flooding the dataset with near-identical variants. Report the distribution after filtering, because acceptance can skew the planned mix toward easy tasks.

Keep answer keys, construction notes, and private verification signals out of teacher-visible context and training exports. Do not require unavailable private reasoning from teacher providers. Store observable explanations and tool actions in a format supported by the chosen training stack; verify provider and source terms before production collection.

Training experiments must compare the same base model, trainer, budget accounting, and evaluation configuration. Measure learning curves, per-family transfer, and general capability regressions. Use development evaluation for iteration and a sealed final holdout for the release decision.

## 8. Benchmark product requirements

### Evaluation tracks

- **Primary:** fixed harness, instructions, memory policy, tool access, and budgets; replace only the model adapter and necessary API serialization.
- **Secondary, later:** best supported agent configuration per model. Label this as a system comparison and disclose configuration differences.

### Data partitions

Maintain separate training, development, public example, private stable test, and private challenge partitions. Assign source/world/scenario lineages before expansion. Hold out workflow compositions and operating regimes as well as individual instances. Shared environment code is allowed; hidden case content and answers are not.

The stable test supports comparisons across releases. Challenge sets test new regimes and refresh exposure-sensitive cases. Independently authored expert cases must be included; same-generator performance alone cannot establish realism or transfer. Check source overlap, hashes, semantic similarity, and generator ancestry.

### Scorecard

Report completion, critical-violation rate, feasible-solution rate, business outcomes, evidence quality, uncertainty handling, repeatability, token cost, tool calls, and latency. Publish per-family results alongside any preregistered aggregate. Never let high profit compensate for a critical policy failure in task success.

For stochastic environments, use matched exogenous seeds and confidence intervals. For uncertain model behavior, repeat runs. Define the reliability estimator and sample count explicitly. Cluster uncertainty estimates by underlying world/scenario family when instances are correlated.

Version task sets, graders, runtimes, adapters, model IDs, prompts, seeds, and budgets. Mark infrastructure failures separately from model failures, preserving logs and using a fixed retry policy. Regrade affected historical runs or label results non-comparable after substantive benchmark changes.

## 9. Delivery phases and gates

All counts and thresholds below are proposed planning defaults, not approved budgets or measured results. Owners are roles to assign; no individual or delivery date is committed.

| Phase | Work and output | Dependency | Exit gate | Accountable role |
|---|---|---|---|---|
| 0. Frame the pilot | Confirm outcomes, four families, users, data access, model/training assumptions, spend envelope; maintain decision log | This PRD | Scope and measurable success criteria agreed; owners assigned | Product/research lead |
| 1. Specify business truth | Create four family playbooks, coverage matrix, source register, data dictionary, rules, and grading specifications; author 10 cases per family | Phase 0 | 40 reference cases reviewed; missing information and valid alternatives resolved | Supply-chain domain lead |
| 2. Prove the environment | Implement minimal worlds, file renderers, tools, simulator, independent verifiers and baselines; run reference cases | Phase 1 | Replay, isolation, baseline, and grader fault tests pass | Environment/evaluation leads |
| 3. Generate a pilot corpus | Target 1,000 accepted training instances, 200 development cases, and 200 independently reviewed sealed test cases from disjoint lineages | Phase 2 | Quality, coverage, leakage, and cost gates pass; failed/repaired task audit complete | Data-generation lead |
| 4. Test learning and evaluation | Run conventional baselines and at least three model configurations; fine-tune one selected open model at nested 250/500/1,000-instance sizes; report performance and cost | Phase 3 | Useful transfer demonstrated on development; one preregistered final test confirms proposed improvement without critical regressions | Training/evaluation leads |
| 5. Expand controlled production | Expand toward 10k then 50k accepted instances; add families and fresh evaluation cases as needed | Phase 4 | Marginal gains, diversity, quality, and costs justify each increase | Product/research lead |
| 6. Decide scale and release | Evaluate 100k–500k scale, benchmark v1 packaging, distribution rights, support and release policy | Phase 5 | Evidence-based scale decision; versioned, reproducible deliverables | Product/research lead |

Do not implement all three environment types at full depth before the reference cases exist. Build only what is required to execute and grade the agreed cases.

The first benchmark release should use a sample size justified by desired precision and scenario diversity. The 200-case sealed pilot is an initial validation instrument, not sufficient evidence for universal supply-chain capability or fine-grained model rankings.

## 10. Proposed pilot quality gates

| Measure | Proposed gate | Interpretation |
|---|---|---|
| Structural and hard-rule checks | 100% pass for admitted instances | Any known critical issue blocks that instance |
| Replay | 100% of admitted demonstrations replay under pinned environment state and actions | Does not require new model sampling to reproduce identical actions |
| Expert review | All 40 reference cases and 200 sealed test cases; at least 25% of accepted training pilot, stratified by family, difficulty, and repair status | Review disagreements adjudicated and linked to affected lineages |
| Known critical task defects | Zero unresolved defects in a released partition | A discovered systemic defect quarantines the affected family for repair and reaudit |
| Grader calibration | At least 95% agreement on expert-adjudicated task success; zero missed critical failures in the designed fault suite | Report sample sizes and uncertainty; this is not proof of zero unseen errors |
| Leakage | Zero known cross-split case/answer leakage; all flagged similarities reviewed | Public pretraining contamination cannot be completely ruled out |
| Training usefulness | Provisional target: at least +5 percentage points in macro task success over the base model, with positive lower bound of a paired 95% interval | Freeze the target before the final test; insufficient power means inconclusive |
| Critical regressions | No newly introduced critical failure type; preregister an acceptable non-inferiority margin for violation rate before training | Do not infer equivalence from a nonsignificant result |
| Cost | Measured cost per accepted task and successful evaluation run stays within an agreed envelope | Budget is currently TBD |

Teacher success rate, acceptance yield, and benchmark difficulty must be reported but are not optimization targets on their own. Rejecting all hard tasks would make those figures look better while reducing product value.

## 11. Cost and scale decision

Track research/source acquisition, generator calls, probing, repair, teacher collection, verification, expert review, environment compute, storage, training, and evaluation separately. Preserve cached/uncached usage and model-specific prices.

Estimate production spend from measured pilot distributions, including rejected candidates and long-tail retries:

`production cost ≈ attempted candidates × measured all-in cost per attempt + training + benchmark operations`

`attempted candidates ≈ target accepted instances / measured acceptance rate`

Avoid double counting teacher/probe costs already included in per-attempt figures. Report uncertainty and at least conservative/base/optimistic estimates. Set run-level spend ceilings before launching production.

The scale decision must consider incremental held-out improvement per additional accepted task and dollar, not only whether generation throughput can reach 500,000.

## 12. Risks and responses

| Risk | Response |
|---|---|
| Plausible but incorrect synthetic work | Authoritative structured facts, independent calculators/checkers, expert audits |
| Correct solver result for the wrong formulation | Check candidate decisions against business constraints independently; verify tiny cases exhaustively where practical |
| Generator, teacher, and judge share a blind spot | Independent roles and implementations, model diversity where useful, expert-adjudicated fault cases |
| Benchmark mostly measures the generator’s conventions | Independently authored cases and held-out source/world/workflow lineages |
| Agent exploits simulator or grader | Audit state transitions, prohibited effects, reward accounting, and adversarial solutions |
| Filtering removes difficult but valuable work | Inspect rejected cases and report post-filter difficulty and coverage |
| Too much implementation before requirements stabilize | Forty reviewed cases before substantial environment expansion |
| Research repository is unavailable or unreleased | Treat methods as references; verify code, license, and compatibility in Phase 0 before selecting dependencies |
| Benchmark exposure or repeated tuning | Private partitions, evaluation access logs, preregistered final tests, separately versioned refreshes |
| Public materials are unsuitable for redistribution | Record rights and intended use per source; replace or exclude restricted artifacts |

## 13. Decisions and unresolved questions

| Topic | Status / working position |
|---|---|
| Initial industry | **Confirmed by user:** discrete manufacturing and distribution |
| Two product outcomes | **Confirmed:** supply-chain fine-tuning examples and repeatable model evaluation |
| Initial four task families | Proposed in this PRD; not yet confirmed |
| 500,000 meaning and scale | Potential eventual target; unique accepted task-instance convention proposed |
| Real source material | Access to anonymized SOPs, quotations, contracts, transaction records, and demand data is unknown |
| Experts and ownership | Reviewers, responsible owners, and available review capacity TBD |
| Model and infrastructure | Base model, teacher models, hosting, trainer, and orchestration framework TBD |
| Language and geography | English-first pilot proposed; currency, calendars, and jurisdiction assumptions must be explicit |
| Budget and dates | TBD; no committed launch schedule |
| Distribution | Internal pilot proposed; public benchmark/data release to be decided later |

## 14. First execution package

The next work package is Phase 0 and the specification portion of Phase 1:

1. Ratify pilot families and user outcomes.
2. Inventory available evidence and identify domain reviewers.
3. Define the minimal world model and task-package schema.
4. Write one family playbook per pilot workflow, including business rules, valid exceptions, and grading criteria.
5. Author and independently review ten reference cases per family.
6. Select framework components against those requirements, recording reuse versus custom work.
7. Estimate pilot budget and sequence implementation dependencies.

Its deliverables are specifications, reviewed reference cases, a component decision record, and a costed pilot plan. Large-scale generation follows only after executable environments and graders pass Phase 2.

## 15. Research basis

The [saved research summary](research/2026-11-02-research-summary.md) contains the paper comparisons and source links. WorkFactory informs backward information planning and isolated probing; GraphForge and WorkGenesis inform evidence grounding and defect attribution; AgentGym informs environment interfaces; OR-Gym and InventoryBench inform simulations and operational baselines; τ-bench and AppWorld inform state and trajectory verification; SupChain-Bench and CSCBench inform domain coverage and comparison.

These are candidate building blocks, not selected dependencies. Reported results have not been independently reproduced. Requirements, quantities, and quality gates in this PRD are our proposed design rather than claims established by those papers.
