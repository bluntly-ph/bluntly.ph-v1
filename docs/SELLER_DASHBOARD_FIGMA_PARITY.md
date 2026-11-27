# Seller dashboard: Figma parity

File `lso4Ri4hDaZxvCebhUqlY5`, read on 2026-09-28 at 10:46 UTC. It was searched
for seller, store, dashboard, analytics, support and claim. A live recheck
after 14:00 was blocked: the Figma connector needs re-authorization.

**No frame in the file draws a seller dashboard, seller analytics or seller
support requests.** The frames that exist for sellers are the public store
page, the seller-review composer and the store search:

| Figma node | Screen | Route | Relation to the dashboard |
| --- | --- | --- | --- |
| `Seller Page - Review` | public store page, reviews | `/sellers/{id}` | The dashboard reuses its rating card (`SellerRatingSummary`) and figures (`SellerFigures`) unchanged. |
| `Seller Page - Questions` | public store page, questions | `/sellers/{id}?tab=questions` | The dashboard's "Waiting on the store" list links into these questions. |
| `SellerPreviewCard` | store card in search | `/search?tab=sellers` | Unchanged. |
| `Seller Review - Step 1 … All done` | seller-review composer | `/sellers/rate` | Unchanged. |
| `Question Page - Buyer or Seller` | the "who should answer?" choice | — | **Removed** by the owner decision (the Q&A audience simplification). The subject (product or store) stays. |

## What the dashboard is built from

With no frame, the dashboard uses the system's existing vocabulary: the
Reviewer Dashboard's cards (`Reviewer Dashboard` frames), the store page's
rating card, hairline lists and pill buttons. It follows the tokens used
everywhere else:
- `--surface-card` and `--shadow-card` for panels;
- `--accent-primary` for actions;
- tabular numerals for counts.

It adds no chart style the system does not already use: the month bars are the
existing volume bars, and the six-month table is plain rows.

| Section | Status |
| --- | --- |
| Overview line (marketplace, claimed, listing link) | NO FRAME — built |
| Rating card, figures | reused from `Seller Page - Review` |
| Reviews per month (bars) | NO FRAME — existing FR-4 component |
| Waiting on the store | NO FRAME — existing |
| At a glance (8 tiles), six-month table, most engaged / most discussed | NO FRAME — built |
| Reviews of your store (respond, flag, ask the administrators) | NO FRAME — built; the actions link to the store page, where they already live |
| Support requests (list, new, detail) | NO FRAME — built |
| Recent activity | NO FRAME — built |

**Phone.** Checked at 390px (`e2e/owner-patch-journeys.spec.ts` journey 15):
- every section stacks to one column with no sideways scroll;
- the six-month table fits without its own scroll (fixed 2026-09-28).

**Owner action.** If a seller dashboard frame is drawn later, add it here and
rebuild the dashboard to it.
