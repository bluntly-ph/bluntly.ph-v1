# Defense demo — admin upvote → earnings Review Queue

Rule (owner, 2026-10-07: "Keep PR #17 nomination"): an administrator's or super admin's upvote
nominates the review into the existing earnings Review Queue at once (`earn_eligible_status`
none → pending). Members' votes still go through the community gate (Wilson LB ≥ 0.65 on effective
n, ≥ 3 Stage 2+ voters). Queueing is not approval and creates no commission or payout.

## Reserved review: CAPSTONE-DEMO-EARN-001

| | |
|---|---|
| Review | "Laptop-ready, but it's a brick" — Anker 737 Power Bank (24000mAh) |
| Id | `ae1d62d1-10bc-4064-97ed-88878e182178` |
| URL | https://www.bluntly.ph/reviews/ae1d62d1-10bc-4064-97ed-88878e182178 |
| Reviewer | zienxt (team account) |
| Admin | bluntly.ph@gmail.com (super admin, signs in by emailed code) |
| State checked 2026-10-07 04:46 UTC | published, thread original, earning `none`, NOT in the queue, admin has not voted ("Helpful, 5" unpressed) |

Do not upvote it before the defense. If it gets used, pick any published review whose earning
state is `none` and that the admin did not write (Admin → All Reviews, Earning: None).

## Click path

1. Admin → Queue (`/admin/review-queue`), Reviews tab: the review is not listed.
2. Open the review URL above → press **Helpful** (thumb/arrow up). The count goes 5 → 6 and the
   button reads pressed.
3. Back to Admin → Queue → Reviews: the review is listed once, earning "Commission", waiting for a
   decision.
4. (Optional, separate decision) Open it → Approve earnings / Reject. Approval is the admin's own
   action; no money moves until the existing commission import and payout steps.

Pressing Helpful again does not add a second vote or a second queue entry. Taking the vote back
leaves the review in the queue (a nomination is never pulled back by votes).

## Already-verified live (2026-10-06)

"lakas neto" (`352cc629…`): admin upvote → queue 8 → 9, listed once, status `pending`; re-press no
change. Backfill `reconcile_admin_upvotes` queued the 3 reviews admins had upvoted before.
