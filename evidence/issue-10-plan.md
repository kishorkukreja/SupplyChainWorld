# Issue 10 implementation plan

Scope: spec §§4–6, 8 and 11. Dependencies #7 lineage, #8 generation and #9 runner are under concurrent implementation; provisional interfaces are being agreed directly with their owners before integration.

Admission will reconstruct the environment from typed world/task inputs, replay every observable action/result, independently check the actual terminal submission and reject diverging observations, hashes, split assignments or hidden metadata. Accepted train-only records serialize user observation, assistant tool calls and tool results with explicit loss masks. Export provenance stays outside model messages. Private expected outcome is checker input only.

Task validity and agent failure remain separate: diagnosis distinguishes task/environment defects, grader defects, agent errors and legitimate uncertainty. Repair is bounded, preserves task type and lineage/split, revalidates premises and requires a clean fresh probe; agent mistakes do not authorize task changes.

Evidence: targeted tests will inject private keys, altered replay, invalid solutions, protected splits and duplicate lineage leakage. Full integration will be run once dependency APIs land. No remote publication or schema changes are in scope.
