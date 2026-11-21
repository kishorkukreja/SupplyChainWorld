# Practitioner re-review, round 3, for issue #17

Date: 2026-11-21
Reviewer: Supply chain practitioner, project owner (role only). **Not independent.**
Format: interactive multiple-choice questions on the open items from round 2 and the v0.3 and v1.2 results. Selections are recorded as selected. "Accept" means the reviewer accepts the value as a provisional working value, not that it is confirmed as practice or checked against any data.

## Decisions

### Static supplier allocation v1.2 (PR #40)

The reviewer accepted these provisional values and rules as the working baseline:

| Item | Accepted value |
|---|---|
| Estimate path | Last-known price allowed only when the part is non-critical, a last-known price exists, and the likely order value is at or below the approval limit |
| Approval limit | 5,000 USD |
| MOQ-excess approval threshold | 500 USD |
| Safety stock service level | 95% |
| Late-inbound window | 3 days (credit 50%) |
| Cost tolerance tiers | 3% / 2% / 1% by order size |
| Salvage by part class | Standard 60%, custom 0% |

### S01 dynamic scenario

| Item | Reviewer answer | Consequence |
|---|---|---|
| Alternate versus expedite price basis | **Compare premiums only** (alternate costs only its premium over the primary, like expedite) | Replaces the v0.3 reading (alternate buys new units at 1.3x with the primary still paid). Needs a v0.4. Alternate can be cheaper than expedite per unit. |
| Penalty size | Raise the cap to **20%** of order value | v0.3 cap was 10%. |
| Small items (penalty on undelivered part only; expedite premiums rising to 50% and 60%; authored slow-lane scenario) | Accept all | Carry forward. |

## Open question this answer creates

If the alternate supplier is charged only its premium, the base cost of the alternate units and the surplus left from the primary lot are undefined. The reviewer has not said how to treat them. v0.4 uses an explicit placeholder convention (base purchase cost of any recovery lot treated as cost-neutral and excluded from comparison; no salvage credit for alternate-bought surplus, so the premium-only reading cannot create a salvage windfall). The reviewer must confirm or replace it.

## Status after this round

- **#35 (static rules):** the reviewer accepted the v1.2 values and rules above as the provisional baseline. This is owner acceptance, not independent validation. Per-case review of the 33 fixtures, solver outputs and graders was not performed.
- **#36 (S01 family):** v0.4 is being built for the price-basis and cap changes. Not accepted until reviewed.
- **#17:** stays open until the v0.4 review and an explicit go, repair or stop decision on both families.

## What this does not establish

No value is confirmed against real data. This is not an independent review. It does not review model behavior, and no model evaluation has been run on these families.
