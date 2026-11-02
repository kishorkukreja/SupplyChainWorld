# SupplyChainWorld implementation specification

Version: 0.1 — initial implementation baseline  
Date: 2026-11-02  
Status: Specification and backlog only; no environment or dataset implemented.

## 1. Purpose and relationship to the PRD

SupplyChainWorld will create verified supply-chain training experiences and independently held-out model evaluations. The [vision](vision.md) describes the objective; the [PRD](PRD.md) describes the broader product. This specification narrows the first executable milestone to supplier award allocation for discrete manufacturing and distribution.

The original four-family pilot remains the broader direction. Its proposed 40 reference cases and 1,000 training instances are downstream targets. The first milestone uses ten supplier-allocation reference cases followed by a roughly 100-instance smoke experiment, not a four-family implementation or proof of fine-tuning value. Dataset sizes are adjustable planning defaults.

## 2. First milestone: one verified procurement episode

Given a synthetic manufacturer's component requirements, usable inventory, supplier quotations, qualification records, and purchasing policies, an agent must produce a feasible, costed award recommendation or correctly request clarification/escalation. An independent checker must explain why the result passes or fails.

Completion means a new contributor can reproduce a task with an offline scripted agent, inspect its trajectory, verify its result, and export an accepted training record without paid model access. A subsequent budgeted experiment adds real model adapters.

### Included

- One planning period with explicit requirement dates, multiple items, suppliers, and one receiving facility.
- Integral component units; one declared currency; fixed quoted unit prices.
- Usable on-hand stock, explicitly dated inbound commitments, supplier eligibility and capacity.
- Supplier-item minimum order quantities and order multiples.
- Quoted variable freight and supplier-level fixed award charges with explicit application rules.
- Budget, lead-time eligibility, and an explicitly defined supplier-concentration policy.
- Three task types: feasible allocation, clarification required, and operationally infeasible.
- Files plus typed query/compute/submission tools; isolated state and audit logs.

### Deferred

- Binding orders, live ERP integration, negotiation, foreign exchange, taxes, price tiers, multi-period inventory dynamics, production scheduling, and browser interaction.
- Full reinforcement learning, public leaderboard, and large-scale generation.
- Other workflows: replenishment, purchase-to-pay exceptions, and disruption replanning.

These restrictions must be visible in task metadata. Unsupported features must be rejected, not silently approximated.

## 3. Business semantics

The family playbook must resolve the following before implementing the schema and grader. These are proposed defaults, not assertions about every real business:

1. Net requirement equals requested component demand less usable stock and qualifying committed inbound supply. Held, reserved, or late inventory is excluded. Clamp negative net requirements to zero.
2. Awards are nonnegative integral quantities. A zero award is permitted; a positive award must meet its minimum and order multiple.
3. Supplier qualification, quote effective dates, arrival deadlines, and supplier-item capacity are hard constraints.
4. Overbuying is permitted only up to the task's explicit excess allowance; MOQ-driven excess is not automatically acceptable.
5. Costs include awarded units times quoted unit and variable freight costs, plus each selected supplier's applicable fixed charge exactly once. Use exact decimal monetary arithmetic and explicit rounding rules.
6. Concentration limits specify their denominator and scope, such as supplier spend divided by total procurement spend. Do not add quantities across unlike items. Zero-spend handling must be defined.
7. Budget is a hard constraint. Among feasible allocations, minimize declared landed cost. Ties are acceptable; no requirement to reproduce a particular award vector.
8. Clarification tasks supply an allowed information-request mechanism and a defined response policy. Missing information must never be guessed for grading purposes.
9. Infeasible tasks require a supported diagnosis or escalation. A solver timeout is not evidence of infeasibility.

The reference-case issue owns finalizing these rules, recording tradeoffs, and identifying which cases require practitioner signoff. No reviewer endorsement may be claimed without evidence.

## 4. System boundaries and trust model

Use a local-first Python package with a pinned supported Python version, typed validated schemas, a command-line interface, and an automated test suite. Select the precise schema library and optimization solver through a short decision record. Prefer a solver usable without a commercial license. AgentGym is an integration candidate, not a prerequisite for this milestone.

Suggested modules:

| Module | Responsibility |
|---|---|
| `schemas` | World, task, action, trajectory, verification and export contracts |
| `worlds` | Deterministic state loading, generation and artifact rendering |
| `envs/procurement` | Tool dispatch, reset, observations, submission and event log |
| `solvers` | Reference optimizer and conventional heuristic |
| `verification` | Independent cost, constraint, policy and evidence checks |
| `generation` | Variant construction, probes, repairs and admission |
| `agents` | Scripted agent and provider adapters |
| `evaluation` | Run manifests, metrics, comparisons and reports |
| `exports` | Verified training export and dataset manifest |

Keep public task input, private construction truth, and private grading data separate. The agent adapter receives only a sanitized observation/tool interface. Hidden files must not be readable through its tools. Export and logging code must not expose answer keys or credentials.

This repository is public. Commit only source code, synthetic public fixtures, schemas, specifications, and sanitized aggregate reports. Store sealed evaluation instances, answers, teacher logs containing restricted evidence, and paid-run credentials outside the public repository. Gitignore rules are a convenience, not an access-control boundary.

## 5. Required data contracts

Every contract has a version and validation rules. Unknown schema versions fail explicitly.

| Contract | Required fields |
|---|---|
| World | World ID, seed, units/currency/calendar, items, requirements, stock, inbound, suppliers, qualifications, quotes, constraints, visibility metadata |
| Task | Task ID, family/version, world ID, lineage, split, request, visible artifact references, permitted tools/actions, expected outcome type, policy and runtime versions |
| Action/result | Tool name, schema-valid arguments, request ID, observation or typed error, simulated time if applicable, state version |
| Trajectory | Run/task/model IDs, configuration, ordered observations/actions/results, final submission, termination reason, artifact hashes, usage and cost |
| Verification | Checker version, task status, per-constraint results, independent cost, reference status/bound, objective gap if defined, critical failures, evidence |
| Export manifest | Dataset version, accepted task IDs, lineage/split, trajectory hashes, schema/runtime versions, source-use status, filtering reasons and counts |

A training record is a verified observable interaction, not a fabricated account of how a known answer was found. Do not require provider-private chain-of-thought.

## 6. Environment and solver interface

Proposed external operations:

- `reset(task_id, seed)` creates isolated episode state.
- `observe()` returns the request and accessible resource catalog.
- Typed read tools expose requirements, inventory, suppliers, quotes and policy.
- A restricted calculation/optimization tool may be available under an explicitly versioned tool profile. It must use only agent-visible inputs.
- `request_clarification(field, reason)` records the request and returns the task-defined response or escalation status.
- `submit_award(allocations, cost_breakdown, evidence)` terminates a recommendation task without issuing a real PO.
- `submit_exception(kind, evidence)` submits a clarification/escalation/infeasibility outcome.

Tool names can change during schema design, but their behavior must be documented and versioned. Invalid actions return typed errors without partial mutation. Reset must remove all prior run state. The same initial state and recorded actions must replay identically.

The private reference solver is separate from any solver tool exposed to the agent. Record optimal/feasible/infeasible/timeout/error statuses and bounds. The feasibility checker must independently calculate business constraints rather than reuse the solver's model-building code as its sole truth.

## 7. Ten reference cases and grading

Create cases covering: basic valid award, fixed-freight tradeoff, MOQ/order multiples, deadline eligibility, supplier qualification, concentration limit, binding budget, permitted excess, missing commercial term, and infeasible capacity. Combine additional constraints where needed but retain a clearly stated diagnostic purpose for each case.

For every case include a visible request, source records, private expected behavior, independently checked calculation, valid alternative where applicable, known wrong submission, and review status. Hand-check small instances or enumerate possibilities to establish the reference solver's behavior.

Task success requires all hard constraints and the expected outcome type to pass. Report economic quality separately; feasible but suboptimal results are not the same as invalid results. If optimality is required for a task, state its tolerance explicitly. Report objective gaps only with a valid reference and defined zero-cost behavior.

Test the grader with incorrect units, doubled fixed fees, rounding edge cases, ineligible suppliers, missing/duplicate items, concentration breaches, fake infeasibility claims, and prohibited hidden-data access. Relabeling IDs must not change business scores. Valid ties must pass.

## 8. Generation and admission

Generate structured business state first, render artifacts second, and author the task around those premises. Vary constraints and business structure, not just names. Tag each instance's meaningful variation and task type.

Assign lineages to training/development/sealed evaluation before expansion. A lineage groups closely related source cases, world templates and scenario ancestry. Prevent instances from one lineage appearing across protected splits. Maintain exact, structural, and semantic-overlap checks with adjudication records for flagged pairs.

Probe only with agent-visible data. Classify failures as environment defect, grader defect, agent error, or legitimate uncertainty. Repairs must preserve intended work and task type. Revalidate and use a clean run after repair; cap retries and retain rejection reasons.

Admission requires valid schema, consistent state/artifacts, correct split assignment, no unresolved critical defect, verified final behavior, and replayable trajectory. A task can be valid even if a particular agent fails it; preserve that distinction in the report. Do not silently remove hard evaluation tasks based on model failure.

## 9. Evaluation and initial experiment

Run an offline scripted agent and an optimization/heuristic baseline first. Then add model-backed runs under a declared cost ceiling. The roughly 100-instance smoke experiment must allocate training/development/evaluation cases by disjoint lineages, with counts and seeds fixed in its manifest before model attempts. Private cases are stored outside this public repository.

Record task completion, hard violations, feasible awards, independent landed cost, optimality/baseline gap, justified exception handling, tool failures, model failures, infrastructure failures, latency and cost. Use repeat runs where affordable and report sample sizes; this experiment is too small to establish broad supply-chain capability.

The primary comparison fixes tools, budgets, instructions, memory and retry policy. Report unavailable model/provider information rather than guessing. Paid runs require configured credentials and a concrete budget; offline work must remain possible without them.

Deliver a report recommending expand, repair, or stop, with failure examples and cost per accepted trajectory. This milestone does not include fine-tuning. A subsequent issue defines the training experiment after the smoke evidence is available.

## 10. Workflow and definition of done

Use [GitHub issues](https://github.com/kishorkukreja/SupplyChainWorld/issues) as the execution backlog. The dependency map in [roadmap.md](roadmap.md) records prerequisites. An unchecked prerequisite blocks dependent execution unless its interface has been explicitly agreed and the provisional work is documented.

Each implementation issue must link its specification sections, identify dependencies, contain acceptance criteria, and name its expected artifacts. Work on issue-specific branches and reference the issue in the PR. Close an issue only when its acceptance evidence exists; a file's existence alone is insufficient. Update [progress.md](progress.md) after substantive milestones.

No arbitrary deadlines or assignees are set. Domain-review capacity, exact pilot budgets, source rights, and distribution decisions remain open. The spec can evolve through documented changes rather than silently widening issue scope.

## 11. Milestone acceptance

- Ten synthetic reference cases exist with explicit validation and domain-review status.
- Offline environment reset, tool execution and replay work from documented commands.
- Independent checker and reference solver agree on hand-verified small cases; known wrong solutions fail and valid alternatives pass.
- Generation produces meaningful variations with split/lineage controls.
- A provider-neutral runner can record and verify observable actions; an offline adapter demonstrates it without API costs.
- Accepted trajectories export with provenance and without hidden evaluation information.
- Smoke experiment has a reproducible manifest, documented budget when paid models are used, and an honest limitations/cost report.
- No claim of practitioner validation, measured training improvement, or broad benchmark coverage is made without the corresponding evidence.
