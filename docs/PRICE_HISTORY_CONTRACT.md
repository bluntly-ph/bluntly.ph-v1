# Price History read contract

Owner: RESEARCH (data/API). Consumer: PIM (Price History visual). No Figma here.
Status: the existing endpoint is sufficient; no new endpoint was added (2026-10-05).

## Endpoint — `GET /api/v1/products/{product_id}/prices` (public)

Returns `PricePanelOut` (`app/schemas/product.py`), built by
`price_service.panel_from` from the product's observations:

| Field | Meaning |
|---|---|
| `series` | `{ "<marketplace>": [{ "observed_at": "YYYY-MM-DD", "price": "1234.00" }, …] }` — one line per marketplace (`shopee`, `lazada`, …), **never blended**; one point per day = that day's median on that marketplace; points in **ascending date order**. A marketplace with no approved price is absent (no toggle). |
| `currency` | `"PHP"` |
| `sufficient` | true once any approved observation exists; `low/high/median` are null before |
| `low`, `high`, `median` | over approved observations (strings, 2 dp) |
| `latest_observed_at` | most recent approved day |
| `platforms` | marketplaces that have a series, sorted |
| `observation_count`, `independent_count`, `required_independent` | counts (approved; distinct submitters; baseline size for admin glance) |
| `pending_count` | observations waiting for a moderator — counted, never priced |

Unknown product → 404. Rules: only `approved` rows are priced; `pending` and
`rejected` never appear in `series`/`low`/`high`/`median` (§16). Observations
are community-submitted (manual form or a review's "Let's talk money"), never
scraped. Dates are calendar days (`observed_at` is a DATE), no time of day.

Not supported (not built, ask RESEARCH if the design needs it): range
filtering/pagination of points, per-point source or submitter, other currencies.

## Edge cases (tested, `tests/test_price_panel_rule.py`, `test_price_and_compare.py`)

0 observations → `sufficient: false`, `series: {}` · 1 approved → one point ·
many → one point per day at the median, date order · several marketplaces →
separate series · pending/held → `pending_count` only · rejected → nowhere.

## Data reality

- Production (Supabase read-only, 2026-10-05): **2 approved** observations
  (1 product, one day) and **176 pending** across 156 products. Production
  charts will show the no-data / one-point states until moderators work the
  Prices queue — nothing is invented to fill them.
- Defense/TEST seed: approved series with 2–5 days per marketplace, including a
  product on both Shopee and Lazada (Jisulife Life9 fan), from Mar to Oct 2026.
