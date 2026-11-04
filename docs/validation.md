# Validation of the controls

!!! warning "Signals, never accusations"
    An alert means *"this deserves a review"*, not *"there is an irregularity"*.

Without a known truth there is no real precision, so a control has to be validated twice:
against **patterns we planted on purpose**, and through **a case-by-case review** of a sample of
its alerts. The review is what turns a list of alarms into a control.


## 1. Detection of injected patterns

The synthetic generator plants known risk patterns in an otherwise neutral background and
records them in a ground-truth file. **Background processes were generated with no risk intent**,
so every alert on them is, by construction, a false positive. These background alerts stand
in for the legitimate causes listed in the catalog: thin markets, recurring consumables, appeals.

* **recall** - share of injected cases the control catches.
* **precision_vs_target** - share of the control's alerts that hit its own injected pattern.
* **on_other_injected_pattern** - alerts on processes carrying a *different* injected pattern.
  For example, the entity with fabricated amounts also produces price outliers.
* **background_fp_share** - share of alerts on neutral background processes (false positives).
* **background_alert_rate_pct** - how often the control fires on a neutral process.

| control_id | injected_pattern | injected | detected | recall | alerts | on_target_pattern | on_other_injected_pattern | on_background | precision_vs_target | background_fp_share | background_alert_rate_pct |
|---|---|---|---|---|---|---|---|---|---|---|---|
| C01 | split_purchase | 102 | 102 | 1.0 | 113 | 102 | 3 | 8 | 0.903 | 0.071 | 0.07 |
| C02 | single_bid | 60 | 60 | 1.0 | 810 | 60 | 89 | 661 | 0.074 | 0.816 | 5.95 |
| C03 | short_submission_period | 50 | 50 | 1.0 | 134 | 50 | 14 | 70 | 0.373 | 0.522 | 0.63 |
| C04 | supplier_concentration | 143 | 143 | 1.0 | 572 | 143 | 37 | 392 | 0.25 | 0.685 | 3.53 |
| C05 | repeated_winner | 89 | 89 | 1.0 | 201 | 89 | 74 | 38 | 0.443 | 0.189 | 0.34 |
| C06 | amendment_increase | 30 | 30 | 1.0 | 72 | 30 | 7 | 35 | 0.417 | 0.486 | 0.32 |
| C07 | price_outlier | 40 | 38 | 0.95 | 218 | 38 | 170 | 10 | 0.174 | 0.046 | 0.09 |
| C09 | award_signature_delay | 30 | 30 | 1.0 | 53 | 30 | 1 | 22 | 0.566 | 0.415 | 0.2 |

**Reading the table.** All controls recover (nearly) every planted case. Precision is the
real story. Single-bid alerts (C02) are mostly background, because 8-18% of competitive
processes have one bidder in the background as well, which is realistic for public procurement.
That is why C02 carries the lowest weight and is worth reading only in combination. Precision
against injected cases is a *lower bound* of usefulness on real data, where some of the
"background" would be real risk. It is also an *upper bound* of how cleanly the rules separate
signal from noise, because the injected patterns are deliberately clean.

### Benford (aggregate test)

| scope | scopes_tested | nigrini_nonconformity | flagged_beyond_noise | mean_mad | mean_mad_null |
|---|---|---|---|---|---|
| all awards | 1 | 0 | 1 | 0.0077 | 0.0021 |
| injected entity | 1 | 1 | 1 | 0.0293 | 0.0078 |
| other entities | 15 | 7 | 0 | 0.0154 | 0.012 |

Nigrini's fixed ranges call many entities "nonconforming" that are not: at a few hundred
amounts, sampling noise alone produces that MAD. The sampling-noise correction (D20) keeps the
entity with fabricated amounts and drops most of the noise. One background entity still exceeds
the corrected bound, and that is the structural false positive the catalog anticipates: the
8 UIT limit piles minor purchases into leading digits 3-4.

### Data-quality checks

| defect | check_id | injected | detected | flagged_total |
|---|---|---|---|---|
| duplicate_ocid | DQ01 | 15 | 15 | 15 |
| missing_buyer_id | DQ02 | 8 | 8 | 8 |
| negative_award_amount | DQ04 | 10 | 10 | 10 |
| absurd_award_amount | DQ05 | 5 | 5 | 5 |
| non_pen_currency | DQ06 | 6 | 6 | 6 |
| tender_end_before_start | DQ07 | 3 | 3 | 3 |
| contract_signed_before_award | DQ09 | 10 | 10 | 10 |


## 2. Case review (20 alerts, 20 judged)

**Protocol.** Two alerts per process control are drawn at random, plus the highest-scored
processes overall. For each alert the worksheet pulls the context a reviewer would ask for:
the evidence, the entity's single-bid rate for that method against the national rate, the
supplier's number of minor purchases at the entity, and the entity's median price ratio. Each
case gets a verdict *before* looking at the ground truth:

* **worth review** - the context does not explain the signal away;
* **likely false positive** - the context offers a legitimate explanation.

The verdicts and their reasons are kept in `docs/validation/review_judgments.yaml`. The last
column reveals the ground truth afterwards. On real data the same worksheet and protocol apply,
without the reveal, and the worksheet stays internal because it is alert-level.

| case | control_id | method_details | segment | score | evidence | verdict | blind | reason | ground_truth | truly_positive |
|---|---|---|---|---|---|---|---|---|---|---|
| R01 | C01 | Contratación menor | 78 | 55.0 | n_purchases=5, cluster_total=192207.13, limit_pen=41200.0, total_vs_limit=4.67, window_start=2024-05-17, segment=78 | worth review | True | 5 transport-service purchases at 89-98% of the limit inside the window (4.7x the limit in total); 5 of the supplier's 6 minor purchases at the entity that year sit in this cluster. Transport is not a fixed monthly consumable. | split_purchase | True |
| R02 | C01 | Contratación menor | 43 | 44.0 | n_purchases=4, cluster_total=144919.22, limit_pen=41200.0, total_vs_limit=3.52, window_start=2024-05-07, segment=43 | worth review | True | 4 IT-equipment purchases at 85-94% of the limit, 3.5x the limit in total; they are all of the supplier's minor purchases at the entity. Equipment is a one-off need, not a recurring one. | split_purchase | True |
| R03 | C02 | Adjudicación simplificada | 72 | 72.5 | method=Adjudicación simplificada, procurement_method=open, n_bidders=1, award_amount=1758141.93 | worth review | True | The single bid alone is unremarkable (entity single-bid rate 16% vs 19% national for the method), but the process also carries concentration, repeated-winner and price-outlier signals. | background (no injected pattern) | False |
| R04 | C02 | Adjudicación simplificada | 15 | 35.0 | method=Adjudicación simplificada, procurement_method=open, n_bidders=1, award_amount=67441.33 | likely false positive | True | Fuel purchase; the entity's single-bid rate (14%) is below the national rate (19%) and there is no other signal. Consistent with a structural thin market. | background (no injected pattern) | False |
| R05 | C02 | Adjudicación simplificada | 14 | 35.0 | method=Adjudicación simplificada, procurement_method=open, n_bidders=1, award_amount=167874.68 | worth review | True | Paper is a commodity with many suppliers, yet the entity's single-bid rate for this method is 30% against 19% nationally (44 processes). Review the entity's specifications and publicity. | background (no injected pattern) | False |
| R06 | C03 | Comparación de precios | 15 | 20.0 | method=Comparación de precios, start=2024-02-05 10:11:00, end=2024-02-08 13:11:00, days=3, min_days=5 | likely false positive | True | 3 days against a 5-day placeholder minimum for a price comparison, a fast-track method. The shortfall is small, the minimum is still to verify (business vs calendar days) and there is no other signal. | short_submission_period | True |
| R07 | C03 | Subasta inversa electrónica | 50 | 20.0 | method=Subasta inversa electrónica, start=2024-10-20 17:55:00, end=2024-10-23 17:55:00, days=3, min_days=5 | likely false positive | True | Same situation for a reverse auction: 3 vs 5 days on a placeholder minimum, entity with low single-bid rate (4%), no other signal. | background (no injected pattern) | False |
| R08 | C04 | Contratación menor | 78 | 23.8 | segment=78, hhi=8456.0, n_awards=33, n_suppliers=5, top_supplier_share=0.916, top_supplier_awards=29, cell_total=43333108.1 | worth review | True | Transport cell with HHI 8,456: one supplier holds 29 of 33 awards and 92% of the amount. | supplier_concentration | True |
| R09 | C04 | Contratación menor | 80 | 2.3 | segment=80, hhi=3063.0, n_awards=53, n_suppliers=23, top_supplier_share=0.523, top_supplier_awards=3, cell_total=27958070.34 | likely false positive | True | HHI 3,063 with 23 suppliers; the top supplier reaches 52% of the amount with only 3 awards, so one or two large consulting contracts drive the index. This is the known 'one large contract' cause. | background (no injected pattern) | False |
| R10 | C05 | Licitación pública | 43 | 41.7 | wins=10, bids=10, win_rate=1.0 | worth review | True | 10 public tenders won out of 10 bid at the same entity in one year. | repeated_winner | True |
| R11 | C05 | Subasta inversa electrónica | 15 | 74.0 | wins=22, bids=22, win_rate=1.0 | worth review | True | 22 of 22 reverse auctions won at one entity, together with concentration and a single-bid signal. | supplier_concentration | True |
| R12 | C05 | Concurso público | 78 | 72.8 | wins=14, bids=14, win_rate=1.0 | worth review | True | 14 of 14 public competitions won, together with concentration and a single bid. | supplier_concentration | True |
| R13 | C05 | Subasta inversa electrónica | 43 | 38.6 | wins=12, bids=14, win_rate=0.857 | worth review | True | 12 wins out of 14 bids in reverse auctions; no other signal, so it could be an efficient incumbent, but the win count is high enough to check the losing bids. | background (no injected pattern) | False |
| R14 | C06 | Adjudicación simplificada | 80 | 74.0 | contract_id=ocds-synthpe-005132-contract-1, original_amount=233964.0, amended_amount=499683.74, increase_pct=113.6, n_amendments=2 | worth review | True | Amended total +114% over two amendments, on a process that also had a single bidder. | amendment_increase | True |
| R15 | C06 | Adjudicación simplificada | 50 | 8.6 | contract_id=ocds-synthpe-011934-contract-1, original_amount=205639.55, amended_amount=279030.47, increase_pct=35.7, n_amendments=1 | likely false positive | True | One amendment of +36% on a food-supply contract, 11 points over a cap that is itself still to verify, low score and no other signal. Consistent with an approved quantity addition; check the approval resolution. | benford_fabricated_amounts | False |
| R16 | C06 | Adjudicación simplificada | 78 | 30.1 | contract_id=ocds-synthpe-012141-contract-1, original_amount=1103399.71, amended_amount=1729970.77, increase_pct=56.8, n_amendments=2 | worth review | True | +57% over two amendments on a contract that also had a short submission period. | amendment_increase | True |
| R17 | C07 | Subasta inversa electrónica | 50 | 34.3 | item_id=2, class=50130000, unit_price=81.6, class_median=16.82, ratio=4.85, class_n=325 | worth review | True | Unit price 4.9x the class median (325 items). The entity pays 28% above class medians across all its items, which points to an entity-level pricing or data issue worth one review. | benford_fabricated_amounts | True |
| R18 | C07 | Adjudicación simplificada | 50 | 39.3 | item_id=1, class=50130000, unit_price=102.6, class_median=16.82, ratio=6.1, class_n=325 | worth review | True | Unit price 6.1x the median of the same class, at the same entity with prices above medians overall. | benford_fabricated_amounts | True |
| R19 | C09 | Adjudicación simplificada | 81 | 22.0 | award_date=2024-08-25, signed=2024-12-29, days=126, max_days=60 | worth review | True | 126 days from award to signature for engineering services. An appeal would explain it, but no appeal data is published, so the check is cheap and needed. | award_signature_delay | True |
| R20 | C09 | Subasta inversa electrónica | 14 | 23.7 | award_date=2025-09-09, signed=2026-01-18, days=131, max_days=60 | worth review | False | 131 days from award to signature in a reverse auction for paper, a simple commodity contract where appeals are rare. Same reasoning as the other C09 case: cheap to check the appeal record. | award_signature_delay | True |


`truly_positive` is true when the case carries the control's own injected pattern, or a pattern
that mechanically produces what the control measures. The fabricated-amounts pattern counts for
the amount-based controls (C01, C04, C07), because it rewrites amounts, not dates or bidder
counts. Concentration and repeated winning count for each other's control (C04 and C05).

**Outcome.** The blind verdicts agree with the ground truth in **15 of 19** cases
(case(s) R20 were judged after their ground truth was displayed and are left
out of this count).
Of the 7 sampled alerts that were in fact false positives, the review set aside
**4** from context alone. The others had co-occurring signals or entity-level context
that justified a look, as they would in a real audit. The review dismissed
**1** truly positive case(s): R06. This is the
cost of a blind review that leans on placeholder thresholds. A 3-day submission period against a
5-day minimum that is still `to_verify` looked benign, and it was a planted short period.

**What the review changed in the control design** (logged in DECISIONS.md, D25):

* **Applied:** C09 now excludes minor/direct purchases (`excluded_methods`). In the first review
  round a 91-day "delay" on a minor purchase order (an earlier R20) was dismissed, because a
  purchase order has no signing step and the amount was immaterial. The sample above was redrawn
  after the change, and new cases were judged blind in the same way.
* C03 needs the verified business-day minimums before its alerts can be dismissed or
  escalated on the size of the shortfall.
* C02 alone is too weak to review: about 6% of neutral processes trigger it. It should be
  reviewed only when the entity's single-bid rate is above the national rate for the method,
  or when another control co-fires.
