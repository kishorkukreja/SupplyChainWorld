# Practitioner re-review, round 2, for issue #17

Date: 2026-11-17
Reviewer: Supply chain practitioner, project owner (role only). **Not independent.**
Format: interactive multiple-choice questions answered in the working session, based on the provisional-values tables [dynamic-v0.2](../acceptance/dynamic-v0.2-provisional-values.md) and [static-v1.1](../acceptance/static-v1.1-provisional-values.md). Fixture dollar amounts are toy scale, so the questions asked for realistic relative values (premiums, percentages). Answers below are the reviewer's selections, not measured data or sourced benchmarks.

## Status

The reviewer gave directional guidance on most open values. Several answers are **ranges or leave a parameter open**, so the repairs must carry them as provisional and the values stay unconfirmed until the reviewer approves specific numbers. The structural rules were reviewed; two were changed. #17, #35 and #36 remain open until the changes below are implemented and the reviewer accepts them.

## Dynamic scenario S01 v0.2

| Topic | Reviewer answer | Implication |
|---|---|---|
| Expedite premium | 30 to 50% over normal unit cost | Re-base the expedite rate card as a percent premium on a stated base unit cost. |
| Alternate supplier premium | 20 to 40% over the primary unit cost | **Conflicts with the current fixture**, where alternate (5 per unit) costs about 1.7x expedite (3 per unit). On the reviewer's numbers alternate can be cheaper than expedite. Re-base and re-derive the baselines. Not a typo to ignore: it changes which recovery looks cheapest. |
| Late penalty | 1 to 2% of order value per day, capped | Replace the 10% per assessed close. Needs a cap (the question text suggested 5 to 10% total, which the reviewer did not confirm). |
| Salvage | "Depends on part" | Salvage rate varies by part type (standard versus custom). No rate given. Needs a per-part-class rate. |
| Standard-tier cancellation | 5 to 7 days after due date; key tier keeps backlog | Replace cancel day 5 of horizon with days after each order's due date. |
| Tier weights | 5 to 1 (key to standard) | Replaces 3 to 1. |
| Warned-signal hint | Qualitative level (low, medium, high) | Replaces the stated 60%. Must remain identical in delayed and no-delay variants. |
| Metric proxies (OTIF, downstream impact, supply risk, tier impact) | Match | Definitions in dynamic-v0.2 section 1, item 10 accepted as written. |

## Static supplier allocation v1.1

| Topic | Reviewer answer | Implication |
|---|---|---|
| Safety stock | Service-level based | Set from demand variability and a target service level. Needs a target service level and a demand variability input per item. Neither was given. |
| Late-inbound credit | 50% within 2 to 3 days | Matches the current fixture. Exact window (2 or 3) unconfirmed. |
| Cost tolerance | Scales with order size | Tighter for large orders, looser for small. Shape and constants not given. |
| Approval limit | 1,000 to 10,000 USD | A range, not a point. Choose a provisional value inside it. |
| Approval limit boundary | Estimate up to and including the limit | **Changes** the rule from strictly under to at or under. |
| MOQ excess | Needs approval | **Changes** the rule: MOQ excess requires approval. The approval threshold was not given. |
| Missing term where other quotes can cover | Ask clarification first | **Changes** v1.1 solver behavior back to the v1.0 behavior: always request clarification before awarding. |
| Concentration measure | Spend share by default | Other measures only when a task asks for them. |

## Not changed by this round

The ten re-tuned and twelve new reference cases were not reviewed individually. The generated development sample, solver outputs and graders were not reviewed. Nothing here is independent validation. The reviewer did not confirm any specific dollar figure, so every number remains provisional.

## Open items

1. S01: alternate versus expedite cost ordering needs a decision after re-basing (see the conflict above).
2. S01: penalty cap value, salvage rate by part class, qualitative hint wording.
3. Static: target service level, demand variability input, tolerance scaling shape, the exact approval limit, the MOQ approval threshold.
4. Re-review of the updated tables and fixtures after the changes are made.
