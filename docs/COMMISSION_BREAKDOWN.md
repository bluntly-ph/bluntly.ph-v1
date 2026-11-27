# Commission breakdown (Performance › "Where the commission went" › ⓘ)

Figma: Proposals › **35 · Commission breakdown** (9057:46463) — opened 9057:46788, full
content 9057:47088, prototype overlay 9177:53790 (move in from the bottom, 300 ms, ease out).

Code: `backend/app/services/commission_breakdown.py` (every figure),
`GET /api/v1/users/me/performance` → `commission`, `components/dashboard/CommissionBreakdownSheet.tsx`.
Tests: `backend/tests/test_commission_breakdown.py`, `tests/frontend/commission-breakdown-model.test.mjs`.

## What the sheet shows

| Line | Meaning |
|---|---|
| Gross sales · N orders · N items | Purchase value of every item whose **order** is completed |
| Gross commission | The marketplace's per-item commission on those items |
| Reversals · N cancelled · N refunded | Commission of items in a completed order that were then cancelled or returned (taken off). "cancelled" counts items of cancelled orders; "refunded" counts items with a refund amount |
| Net commission | Gross commission − Reversals |
| You / Honesty Fund / Bluntly | The flat 30 / 30 / 40 split of the net (`earnings.split_commission`; Bluntly absorbs the rounding) |
| Pending | Commission and orders the marketplace has not finalised; never counted |
| By marketplace | Shopee and Lazada tiles (always both): gross commission and orders |
| By product · net commission | Net per catalogue product, most first; top 5, then "See all N products" |

"Earned", the donut's centre and "Where they bought" read the same breakdown, so the cards
and the sheet always agree. The breakdown covers every credited sale (not the Weekly/Monthly
period); the subtitle names the span of the completed orders it counts.

## Data rules

- Source: `affiliate_postbacks` (one row per marketplace item) credited to the member
  (`reviewer_id`, or an attributed review they wrote), plus ledger entries with no report row
  behind them (counted as completed items with their stored gross, no sales figure).
- **Per-item commission** is Shopee's `Item Total Commission(₱)`. `Affiliate Net Commission` and
  `Total Order Commission` are order-level figures Shopee writes on one item of the order (0 on
  the rest), so they are only a fallback for exports without the item column. This also changes
  what the ledger import credits per item (the per-order total is unchanged).
- Amounts are kept at the report's precision (`item_commission`, `purchase_value`,
  Numeric(14,5), migration 0096), summed, and rounded once, half up — like the ledger.
- Products group by our catalogue product: Shopee `Item id` → the product carrying the listing
  `https://shopee.ph/product/{Shop id}/{Item id}` (or the attributed review's product); `Model id`
  is the variant. An item no product carries yet groups by itself under Shopee's title.
- Attribution: links Bluntly decorates already carry the review in `sub_id1` (and the click in
  `sub_id2`), so the reviewer is the review's author. The two sample reports have no Sub_id at
  all (links made outside Bluntly), so their rows are credited by the demo seed directly.

## Demo account

`python -m scripts.seed_commission_demo` (dry run) / `--replace-demo-commissions --apply`
seeds `perezgyber@gmail.com` from `backend/scripts/data/commission_demo_shopee_orders.csv`
and checks the sheet against `commission_demo_summary.json`. It creates or attaches the five
named catalogue products through the admin product CSV importer, stores the 134 report rows
(no wallet credit: a report row is evidence, never money), and with
`--replace-demo-commissions` removes the account's earlier `DEMO-seed-*` ledger entries and
takes their reviewer shares back off the wallet.

Known difference: Jisulife Handheld Fan Pro1 is ₱250.015 exactly (93.64 + 77.25 + 79.125). The
sheet shows **₱250.02** (half up); the summary file's ₱250.01 is a binary-float rounding.
