# Reporting module — the four system reports

Status: **engineering complete, ready for product review and independent QA.** Nothing here says QA
passed. Production is untouched: no migration, no deploy, no data.

| # | Report | Audience | Screen | API |
|---|---|---|---|---|
| 1 | Honesty Fund Distribution Report | Staff | `/admin/reports/honesty-fund` | `GET /api/v1/admin/reports/honesty-fund` |
| 2 | Commission and Payout Report | Staff | `/admin/reports/commissions` | `GET /api/v1/admin/reports/commissions-payouts` |
| 3 | Seller Rating Summary | The store's approved owner; staff | `/sellers/{id}/reports` (from the store dashboard; staff pick a store at `/admin/reports/seller-ratings`) | `GET /api/v1/sellers/{seller_id}/reports/rating-summary` |
| 4 | Reviewer Earnings Statement | The reviewer (own only); staff | `/dashboard/statement` (from Dashboard → Payment history) | `GET /api/v1/reports/earnings-statement` (own); `GET /api/v1/admin/reports/earnings-statement/{user_id}` (staff) |
| 5 | Financial Report (screen + branded PDF) | Staff | `/admin/reports` (tab *Reports*; the others above are its sibling tabs) | `GET /api/v1/admin/reports/financial`; `POST …/financial/generate`; `GET …/financial/history`; `GET …/financial/history/{id}/pdf` |

> **HONESTY FUND DISTRIBUTION FORMULA: NOT YET DEFINED.** Report 1 lists every input a formula
> would need, and computes no share. The holding period is also undefined. See
> [Report 1](#report-1--honesty-fund-distribution-report).

## Common behaviour

**Period.** Every report takes one of:

| Parameters | Covers |
|---|---|
| `month` + `year` | one calendar month |
| `year` | one calendar year |
| `start_date` + `end_date` | a custom range of whole days, both inclusive, at most 366 days |
| nothing | the current month |

Days are **Asia/Manila** days; the API converts each boundary to a UTC instant. Commissions are
dated by their **cycle month** (the importers store `cycle_month`, the first of the month, which is
also the Honesty Fund's and the remittance's cycle), so a financial report over a custom range
covers every cycle month the range touches, and says so in `meta.period.cycle_months` and in the
report's notes. Mixing a month/year with a range, a month without a year, an inverted range or a
range over 366 days is refused with 422 (`period_*` codes) rather than widened.

**Shape.** Every response carries `meta` (title, period, `generated_at`, currency, notes), the
entity it is about, summary figures, detailed rows and an explicit empty state. Money is `Decimal`
end to end and is serialised as a string (`"1234.50"`). The UI formats that string; it never parses
it into a float and never adds anything up (`components/reports/report-model.ts`, `formatPeso`).

**Exports.** `format=csv` returns `text/csv; charset=utf-8` with
`Content-Disposition: attachment; filename="bluntly-<report>-<period>[-<section>].csv"`, e.g.
`bluntly-commission-payout-2026-09.csv`. `section` picks the table where a report has several.
CSV rules (`app/services/reporting/common.py`):

- columns come from each table's declaration, in order — a field added to a row can never reach an
  export by accident;
- money is written exactly, to the centavo, with no sign or separators (`1234.50`, `-12.50`);
- UTF-8 with a byte-order mark, so spreadsheet software reads `₱` and `é`;
- a text cell beginning with `=`, `+`, `-` or `@` is prefixed with `'`, so a review titled
  `=HYPERLINK(...)` is shown, not executed (numbers are exempt).

**Print / PDF.** Each report page has a *Print / PDF* button and a print stylesheet
(`app/globals.css`, `.report-*`): the console rail, the site header and the controls drop out and
tables print whole. No PDF library was added.

**Loading, empty, error.** Each page has a `loading.tsx` skeleton; each table states its empty case
("No earnings in this period."); an API failure renders *Report unavailable*, a 403 renders *Not
available*, a 422 renders *Invalid period*.

## Authorization

Decided server-side, in `app/api/v1/routes/reporting.py`, by three guards:

| Guard | Used by | Today |
|---|---|---|
| `get_current_user` + session identity | Report 4 (own) | the statement is always the caller's — there is no user id in the path, and a `user_id` query parameter is ignored |
| `require_report_staff` | Reports 1, 2, staff Report 4 | `require_staff` — an Administrator or a Super Admin (owner decisions B–D) |
| owner **or** staff | Report 3 | `seller_service.require_store_owner` (an APPROVED claim by this account) unless `is_report_staff` |

The coming Administrator / Super Admin split changes `require_report_staff` and `is_report_staff`,
not the reports.

| Caller | R1 fund | R2 commissions | R3 store A | R3 store B | R4 own | R4 someone else |
|---|---|---|---|---|---|---|
| Anonymous | 401 | 401 | 401 | 401 | 401 | 401 |
| Member | 403 | 403 | 403 | 403 | 200 (own) | 403 |
| Pending claimant of A | 403 | 403 | 403 | 403 | 200 (own) | 403 |
| Owner of A | 403 | 403 | **200** | 403 `not_store_owner` | 200 (own) | 403 |
| Staff (Administrator / Super Admin) | 200 | 200 | 200 | 200 | 200 (own) | 200 |

All of these are exercised against the real API: `backend/tests/test_reporting_api.py` and
`e2e/reporting-journeys.spec.ts`.

## Report 4 — Reviewer Earnings Statement

`app/services/reporting/earnings_statement.py`

| Figure | Source |
|---|---|
| Earned, all time | `SUM(commissions.reviewer_share)` + `SUM(honesty_fund_distributions.payout_amount)` for the reviewer, net of reversals |
| Earned this period | the same over the period's cycle months |
| Clearing | `payout_service.uncleared_share` — credited, marketplace has not paid Bluntly for that cycle |
| Cleared, withdrawable | `payout_service.withdrawable_from(wallet, clearing)` — the rule a cashout is checked against |
| Paid | payouts in `paid` (all time; and by paid date within the period) |
| Requested, not paid yet | payouts `scheduled` + `processing` |
| Per review | commissions grouped by review: sales, gross commission, reviewer earning, cleared, clearing, marketplaces |
| Line items | one row per commission (a return shows as a negative *reversal* line) |
| Payouts | payouts requested in the period: amount, method, **masked** destination (`j***@gmail.com`), batch, reference, status, processed date |

Never exposed: another reviewer's figures, the full payout address, marketplace credentials.

## Report 3 — Seller Rating Summary

`app/services/reporting/seller_rating.py`

**Dimensions found in the schema (`seller_reviews`): four**, matching FR-4 — no dimension was
invented and none is missing:

| Dimension | Type | Reported as |
|---|---|---|
| `accuracy` (item matched the listing) | yes/no | share of yes |
| `order_completeness` (nothing missing) | yes/no | share of yes |
| `customer_service` | 1–5 | median (approved) and mean (reference) |
| `packaging_quality` | 1–5 | median (approved) and mean (reference) |

Plus `overall_rating` (0–5 in half steps): **median** (the approved aggregate, Business Rules §10),
mean shown for reference; and **recommendation rate from the stored `would_recommend` answer —
YES, the field exists**, so the rate is never inferred from stars. Medians and rates come from
`seller_service.summarize_reviews`, the same function the public store page uses. Removed reviews
are excluded; the reviewer's self-reported order ID is never in the report.

## Report 2 — Commission and Payout Report

`app/services/reporting/commission_payout.py`

| Section | Source |
|---|---|
| Totals and by marketplace | two grouped queries over `commissions` for the period's cycle months |
| Commission rows | `commissions` joined to the review, product, reviewer and the attributing link's sub-ID (`referral_links`, one `DISTINCT ON` subquery) |
| Remittances | per marketplace and cycle: gross the imports attributed vs `marketplace_remittances.amount_received`, with the difference |
| Reviewer payout readiness | every reviewer with a commission in the period or an open payout: wallet, clearing, withdrawable, ₱300 threshold, eligible Yes/No, payout account on file, requested, paid in period, latest payout |
| Payouts | payouts requested in the period |

**No second formula.** The 40/30/30 split and the fund-track redirect of the reviewer's 30% are
applied once, by `earnings.split_for_review`, when a commission is recognised; the report reads the
stored shares. `tests/test_reporting_units.py::test_reports_do_not_reimplement_the_split` fails if
the reporting package ever contains the split constants.

**Reconciliation.** A marketplace pays per platform and cycle, so a commission is *cleared* when its
platform-cycle remittance is recorded (`cleared_at`), *awaiting remittance* until then. Only
cleared money is withdrawable; pending money is never counted as withdrawable. ₱299.99 is not
eligible; ₱300.00 is (`test_the_300_peso_threshold`). No reviewer cooldown. The same-month batch
protections (`open_batch_for`, `uq_payout_user_batch`, PayPal `sender_batch_id`) are untouched.

## Report 1 — Honesty Fund Distribution Report

`app/services/reporting/honesty_fund.py`

**Layer A — fund inputs (complete):**

- Pool by cycle: the ledger's `honesty_fund_share` on real (non-test) commissions, the part that has
  cleared, and anything actually distributed (`honesty_fund_distributions`).
- Every review on the fund track (`earn_eligible_status = honesty_fund`, i.e. Hard pass, or "It
  depends" at ≤ 2 stars, decided by `earning_track.track_for`), with: routed-to-fund date (from the
  audit log), eligibility by `honesty_fund_service.eligible_reviews` and the exclusion reason
  (removed, not public, claimed seller, concentration hold), Photo provided, §11-weighted helpful
  votes, distinct-voter evidence against the floor (ADR-016), price paid, the Honesty Score
  (`honesty_fund_service.score_inputs`, the same arithmetic the distribution mechanism uses), its
  own sales' commission base and what they put into the pool.

**Layer B — computed distribution: BLOCKED on the owner.** `computed_share` is `null` with status
`pending_formula` on every row, and the CSV writes *Pending distribution formula*. This holds even
where `honesty_fund_distribution_enabled` is switched on (the test suite switches it on for its own
tests): that flag enables the existing mechanism, it does not approve a formula. The report's
`formula` block states `defined: false`, `holding_period_defined: false`.

**2.5★ "It depends".** Owner decision A: an administrator's approval escalates such a thread to a
Super Admin, who routes it to the Honesty Fund or the Platform (`/admin/special-routing`). The
report counts the threads still waiting (`pending_superadmin_routing`) as `pending_routing_count`
and leaves them out. A thread routed to the Honesty Fund is on the fund track like any other; one
routed to the Platform is not.

## Report 5 — Financial Report (meeting 2026-10-02)

`app/services/reporting/financial.py` (figures), `financial_pdf.py` (the PDF). Figma
Screen/Admin/Reports `8028:12886`, Overlay/Report/Generate `8028:13346`, PDF pages
`8029:12942` / `8029:13078`.

| Section | Source |
|---|---|
| Revenue & split | `commissions` for the period's cycle months, QA test money excluded: earned (forward entries), reversed (their reversal entries), net = earned − reversed; Bluntly / Reviewers / Honesty Fund = the stored shares summed (no second formula); *absorbed* = `affiliate_postbacks.unrecovered_amount` of the period's reversals — part of reversed, borne by Bluntly, never deducted twice |
| By marketplace | per marketplace: commissions recognised + affiliate orders recorded in the period that earned none (pending, cancelled, unattributed) = orders; commissions; earned |
| Money in | remittances received in the period beside what the imports attributed to that marketplace and cycle (shortfall when less); the period's own cycles listed as *Clearing* until paid |
| Money out | payouts marked sent in the period (= paid out); to send, failed and cancelled beside it; an Honesty Fund distribution is listed as *credited to wallets* and **not** added to paid out (it leaves Bluntly when those wallets are paid, so adding it would count the same peso twice) |
| Liabilities | **as of generation** (balances have no history): cleared money in wallets (the §19 rule), payouts to send, the rest of the wallets (still clearing), completed sales whose sub-ID matches no review |

**Periods.** Month, **quarter** (new: `quarter` + `year`, kind `quarter`, label `Q3 2026`), year,
or custom dates — the same Manila rules as above.

**PDF.** ReportLab canvas (new dependency, BSD), A4 = the Figma frame's 595 × 842 pt, so the
design's measurements are used as they are. Poppins (OFL) with a one-glyph DejaVu subset for ₱
(Poppins has none); the head carries the `bluntly` wordmark with the swoosh, as the owner asked
in the meeting, instead of the template's "b" tile. Fonts and wordmark: `backend/app/assets/report/`
(licences beside them). Tables continue on a new page under their section title and header row.

**History.** Each generated PDF is logged with its figures in `platform_settings`
(`financial_report_log`, newest 24) — no migration. *Download* re-renders from those logged
figures, so it is the same document, not today's numbers under an old date.

## Seeded marketplace reports (owner plan, 2026-09-28)

Real commissions need real buyers, and until then the marketplaces' exports come back empty. The
agreed plan: produce files in each marketplace's **real export shape**, pre-filled with the sub-IDs
of real active referral links, and import them through Bluntly's normal importer, so matching, the
split, the ledger, clearing, payouts and these reports all run exactly as they will on a real file.

| Mode | Endpoint | What it does |
|---|---|---|
| Synthesize | `GET /api/v1/admin/affiliate/seeded-report?platform=shopee\|lazada&month=&year=&rows_per_link=&seed=` | invents rows for every active link on that marketplace, deterministic amounts, plus up to two non-payable rows (Pending/Cancelled, Rejected/Returned) to exercise skipping |
| Fill | `POST /api/v1/admin/affiliate/seeded-report/fill?platform=` (upload a real export) | keeps every marketplace value and writes our sub-IDs into `Sub_id1` / `Aff Sub ID` — the owner's "fill those values" |

Both write the real 47-column headers (checked against the owner-supplied exports in
`backend/tests/fixtures/`). Then: **Admin → Affiliate Links → import** (preview first), record the
cycle's remittance to clear it, and open the reports.

**Safety.** Every seeded order reference starts `BLUNTLY-SEED-`. Generation is refused on
production (`seeded_reports_disabled_in_production`), and both importers refuse any file containing
a seeded row on production (`seeded_report_in_production`, 422, nothing written) — the net that
matters, because a seeded row imported there would credit real wallets with money no buyer paid.
"Production" is `APP_ENV=production` **or** any connection pointing at the production project
(`env_guard.production_signals`).

**Lazada** also has a signed API (`adapters.lazada.fetch_conversions`) returning the same data;
it can replace the file for Lazada once real conversions exist. Shopee has no API, so its export
stays the path.

## Query performance

Every report is a fixed number of grouped or joined queries whatever the row count — no per-row
query. Detail tables are bounded (Report 2 pages its commission rows, default 200, max 5000; other
tables cap at 2000 rows and say so). Checked with `EXPLAIN (ANALYZE)` against 200,000 synthetic
commissions over 2,000 reviewers (local Postgres 17, in a rolled-back transaction):

| Query | Without index | With `ix_commissions_reviewer_cycle` |
|---|---|---|
| Cashout check (`uncleared_share`, used by every cashout and by Reports 2 and 4) | parallel seq scan, 27.2 ms | bitmap index scan, 0.23 ms |
| Statement period sum (reviewer + cycle) | bitmap scan on `cycle_month`, 1.9 ms | index scan, 0.09 ms |
| Fund report, review IN list + cycle | — | 3.6 ms (existing `cycle_month` index; no `review_id` index added) |

So one index was added, and only it: migration **`0061_commission_reviewer_index`**
(`commissions(reviewer_id, cycle_month)`), additive, reversible. Today's tables are tiny (TEST: 48
commissions), so it is sized for growth rather than fixing a present problem. A `review_id` index
was not added: no measured query needs it yet.

## Files

| Layer | Files |
|---|---|
| Services | `backend/app/services/reporting/{periods,common,earnings_statement,seller_rating,commission_payout,honesty_fund}.py`; `seeded_affiliate_reports.py` |
| Shared refactors (behaviour-neutral) | `payout_service.uncleared_shares` / `withdrawable_from`; `honesty_fund_service.score_inputs`; `seller_service.require_store_owner` |
| API | `backend/app/api/v1/routes/reporting.py`; seeded-report routes in `admin_earnings.py`; schemas in `app/schemas/reporting.py` |
| Migration | `backend/alembic/versions/0061_commission_reviewer_index.py` |
| UI | `components/reports/*`, `lib/reports.ts`, `app/dashboard/statement`, `app/sellers/[id]/reports`, `app/admin/reports/*`, Admin rail *Reports* |
| Tests | `backend/tests/test_reporting_units.py`, `test_reporting_api.py`, `test_seeded_affiliate_reports.py`; `tests/frontend/report-model.test.mjs`; `e2e/reporting-journeys.spec.ts` |

## Figma

The file (`lso4Ri4hDaZxvCebhUqlY5`, page 0:1, read 2026-09-28) has **no report frames** — nothing
named report, statement, payout report or seller rating. The screens reuse the console's cards and
table and the dashboard's figures, in the existing tokens. Nearest frames for context: Admin/Sidebar
`5017:2225`, Admin Page - Review Queue `6922:837`, Reviewer Dashboard - History `5762:472`.

## Known open items (product)

- **Honesty Fund distribution formula — not defined.** Also its holding period.
- 2.5★ "It depends" routing: implemented (ADR-017). PLATFORM's arithmetic (the reviewer's 30% to
  the platform, the fund's 30% unchanged) awaits the owner's confirmation.
- Seller review dimensions: four exist; if the product wants a different set, that is a schema
  change, not a report change.
