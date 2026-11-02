# ADR 0001: Python contracts and reference optimizer

Status: accepted for the first offline milestone, 2026-11-02.

Use Python 3.12 and Pydantic 2.13.4 for typed JSON validation, unknown-field rejection, precise Decimal fields and generated JSON Schema. JSON money uses decimal strings; binary float inputs are rejected. Currency is USD and item units are integral `each` in this schema version. Commercial price/freight fields may be null only to represent missing terms requiring clarification. Validation enforces structural integrity; independent verification enforces business feasibility.

Use exhaustive bounded enumeration as the initial license-free reference optimizer for the deliberately small reference cases. It gives an exact, inspectable oracle without a commercial or network dependency. Explicit search limits must report timeout rather than infeasible. Reconsider a permissively licensed MILP solver when larger cases justify it; do not claim enumeration scales to production procurement.

The agreed #2 interface embeds supplier qualification in each supplier-item quote; separate qualification records are deferred because there is exactly one quote per supplier-item pair. Calendar is Gregorian, one receiving facility is implicit, and currency conversions and fractional units are unsupported.
