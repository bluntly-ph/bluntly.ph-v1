# Claimed seller dashboard and support requests

Owner decision patch, 2026-09-28. A store's **approved** owner gets:
- a dashboard of their store's reviews and engagement;
- a way to write to the administrators.

Claiming never suppresses criticism (§9). Nothing here can hide, change or rank
a review; a request asks, and an administrator decides.

## Where

| Route | What |
| --- | --- |
| `/seller/dashboard` | The way in. It opens the store's dashboard when the account runs one store, lists the stores when it runs several, and says how to claim when it runs none. |
| `/sellers/{id}/dashboard` | The dashboard. Only the approved owner sees it; anyone else is told how claiming works. |
| `/sellers/{id}/support/new` | Write to the administrators, optionally about one of the store's reviews. |
| `/sellers/{id}/support/{requestId}` | One request: the message, its status and the administrator's reply. |
| `/admin/review-queue?tab=support` | The administrators' queue. |

API: `GET /sellers/{id}/dashboard`; `/sellers/{id}/support-requests[/{rid}]`
(owner); `/admin/support-requests[/{rid}[/assign|/respond|/status]]` (staff).
Ownership is re-derived from the database on every call:
- another store's owner gets **403** (`not_store_owner`);
- another store's request asked for through your own store's path gets **404**.

## What the dashboard shows

Counts from data the platform already stores. Nothing is modelled or
predicted. `backend/app/services/seller_dashboard.py` computes it all with a
fixed handful of grouped queries (no per-review query).

| Figure | Definition |
| --- | --- |
| Reviews | visible reviews of the store (not taken down by an administrator) |
| Median rating | the median overall rating of those reviews (`seller_service.summarize_reviews`) |
| Response rate | reviews carrying the store's one public response ÷ reviews |
| Replies | members' replies under the store's reviews (not removed) |
| Helpful votes | "helpful" votes on the store's reviews |
| Questions | store questions (not removed); "answered by you" counts those with an answer from the store |
| Open flags | the store's "suspected fake" flags still open or awaiting substantiation |
| Open support requests | the store's requests still `open` or `in_review` |
| Months | the last six Manila months, zero-filled: new reviews, new replies, new questions |
| **Engagement** (one review) | **helpful votes + replies** |
| Most engaged review | the visible review with the highest engagement; ties go to the newer |
| Most discussed review | the visible review with the most replies; ties go to the newer |
| Recent activity | the newest 15 events: new reviews, the store's responses, replies, questions, support-request updates |

The dashboard never shows moderation priority. It is an internal triage signal
for staff, not a ranking to show a seller.

## Support requests

Categories:
- report a review;
- a takedown investigation;
- a review the seller believes is fake;
- their account or store claim;
- a listing or product;
- general.

Lifecycle: `open → in_review → resolved | rejected`.
- An administrator **takes** a request (assigned to them, `in_review`).
- They **reply**; the seller sees the reply, optionally with a new status.
- They **set a status** with a staff-only **internal note**, which the
  seller's API schema has no field for.

Every change is audited (`moderation_logs`, action `support_request`, with the
event in the context), and the seller is notified. Messages refuse links
(Business Rules §1). A request may name one of the store's own reviews; another
store's review is refused (404).

Tests:
- `backend/tests/test_support_requests_api.py`: lifecycle, isolation between
  stores, who may use it, queue order.
- `backend/tests/test_seller_dashboard_analytics.py`.
- `e2e/owner-patch-journeys.spec.ts` journeys 5–10 and 15.
