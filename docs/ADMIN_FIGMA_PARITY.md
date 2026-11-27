# Admin console: Figma parity

File `lso4Ri4hDaZxvCebhUqlY5`. Owner decisions A–D (2026-09-28): the console is
the **Administrator** console at `/admin` (`/moderate` redirects), with a Super
Admin section.

**How this was checked.** The file's full node metadata was read through the
Figma connector on 2026-09-28 at 10:46 UTC, together with renders of the two
admin frames. It was searched for Admin, Administrator, Dashboard, Panel,
moderation, users, sellers, products, reports, payouts, earnings, analytics,
support and the sidebar. At 14:00 the connector asked to be signed in again
(`/mcp`), so a second pass against the live file could not run. The table
below stands on the 10:46 reading. **If frames were added since, re-run the
check** after re-authorizing Figma. Only one admin page frame and one admin
component exist in the file.

Status legend: **MATCH** built to the frame · **DEVIATION** built to the frame
with a documented difference · **NO FRAME** no frame exists (built from the
console's own vocabulary) · **BLOCKED_BY_PRODUCT_DEFINITION** the frame draws
something the product has not defined, so nothing fake is shown.

| Figma node | Screen | Current route | Target route | Status | Mismatch | Implementation | Backend support | Done? |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 5017:2225 `Admin/Sidebar` (collapsed + expanded) | Console rail | `/admin` (all) | same | DEVIATION | Items the frame does not draw:<br>• Prices<br>• Payouts, Reports, QA Payments (owner-directed)<br>• Analytics<br>• the **Super Admin** group (User management, Special Routing), shown to a Super Admin only<br>The frame's user card reads "Admin"; ours shows the role, *Administrator* or *Super Admin*. | `components/admin/AdminNav.tsx` (`navFor(role)`) | n/a | ✅ |
| 6922:837 `Admin Page - Review Queue` | Review queue: table + detail, tabs Review / Answer / Report / Support | `/admin/review-queue` | same | DEVIATION | Built to the frame's columns, order, tabs, detail stack and pagination. Headers were tracked-out uppercase and wrapped mid-word at 1280; now sentence case and unwrapped, as drawn (fixed 2026-09-28). The decision panel (Approve earnings / Take down / Reject) is not in the frame: owner ruling 2026-09-16. | `components/admin/ReviewQueueScreen.tsx` | ✅ | ✅ |
| 6922:837 → Support tab | Support tab | `/admin/review-queue?tab=support` | same | DEVIATION | The frame draws the tab only. Its body reuses the Answers tab's list + detail layout, now backed by seller support requests (assign, reply, status, internal note). | `components/admin/SupportQueue.tsx` | ✅ `/admin/support-requests…` | ✅ |
| 6922:837 → Views / Shares / Comments, Voting Distribution globe + city bars, Flagged voters / High / Low trust, voter table (pattern, rate, risk level), Recent Report, reverse image search / plagiarism | detail panel sections | `/admin/review-queue` | same | BLOCKED_BY_PRODUCT_DEFINITION (plagiarism: DEVIATION since 2026-09-29) | Drawn in the frame. Most have no read path or no methodology: no per-voter risk model. **Plagiarism** (QA patch 2026-09-29): copied text and reused photos are now real signals, shown as system reports with their evidence under **Why was this reported?**, not as a score in this panel. **Reverse image search** stays BLOCKED — PROVIDER/API CREDENTIAL REQUIRED, and the panel says so. Shared-network votes are a report on the member, never a per-voter IP column. | Each says so in place; no fake numbers. See [ANTI_FARMING_AND_PLAGIARISM.md](ANTI_FARMING_AND_PLAGIARISM.md). | partial: text and photo ✅, reverse image ❌ | ✅ (as documented) |
| 6922:837 → (no tab drawn) | **All reviews** tab (QA 2026-09-29) | `/admin/review-queue?tab=all` | same | NO FRAME | The frame draws Review / Answer / Report / Support. QA asked for every review with its Wilson, because the queue holds only reviews awaiting an earnings decision. Built from the queue's own vocabulary: the search pill, compact selects, the same table type and row rhythm, the pager. Two Wilson columns (public and gate) and a "why not queued" line. The page title reads "All Reviews". Administrator and Super Admin only. | `components/admin/AllReviewsTab.tsx`, `all-reviews-model.ts` | ✅ `GET /admin/reviews` | ✅ |
| 6922:837 → queue header | Review tab membership line, Refresh and "Updated" time (QA 2026-09-29) | `/admin/review-queue` | same | DEVIATION | Not in the frame. One line above the table says what the queue holds and, under Post-Seeding, why a new review may not be in it, with a link to All reviews. It exists because QA read the gate as a fetch bug. | `ReviewQueueScreen.tsx` | ✅ `earn_gate_phase` | ✅ |
| 6922:969 / 973 / 976 / 1460 / 1463 / 1466 `Admin Review Photo` | photo tiles in the detail panel | `/admin/review-queue` | same | MATCH | — | detail panel photo grid | ✅ | ✅ |
| 5017:1738 Overview (**deleted from the file** before 2026-09-16) | Overview | `/admin` | same | NO FRAME | Stands on its last reading. | `components/admin/AdminOverview.tsx` | ✅ | ✅ |
| 6532:278 Answers tab (**deleted**) | Q&A tab | `/admin/review-queue?tab=answers` | same | NO FRAME | Stands on its last reading. | `components/admin/QaAnswersTab.tsx` | ✅ | ✅ |
| — | **User management** (Super Admin) | `/admin/users` | same | NO FRAME | The frame's MANAGE group has "Reviewers", not user management. Under decision C user management is a Super Admin's, so it lives in the Super Admin group. Built from the console's panel, table and pill vocabulary; role changes go through a confirmation dialog. | `components/admin/UserManagement.tsx` | ✅ `/admin/users`, `PATCH …/role` | ✅ |
| 8178:20045 `Screen/Admin/SpecialRouting` + 8178:20344 `Overlay/Routing/Track` | **Special routing** (Super Admin) | `/admin/special-routing` | same | DEVIATION | Earnings track drawn (cards, table, pager, Route earnings overlay with a log note). Destinations are decision A's Honesty Fund / Platform, not the frame's "Commission". Not drawn: Escalated reports / Escalated reviews tabs, Set a rule, "Use this for every…" (no escalation flow, no routing rules). Recent decisions kept under the table. | `components/admin/SpecialRoutingQueue.tsx`, `components/admin/routing/routing-model.ts` | ✅ `/admin/super/special-routing…` | ✅ |
| — | Reviewers (+ investigation flag) | `/admin/reviewers` | same | NO FRAME | The sidebar names it; no page frame. The investigation toggle moved here from User management so Administrators keep it. | `app/admin/reviewers/page.tsx`, `InvestigationToggle.tsx` | ✅ | ✅ |
| — | Products, Prices, Sellers (claims, appeals), Affiliate Links, Honesty Fund, Payouts, Reports, QA Payments, Analytics, Activity Log | `/admin/<section>` | same | NO FRAME | The sidebar names these; the file has no page frames for them. | existing pages | ✅ | ✅ |
| — | Settings | rail item | — | BLOCKED_BY_PRODUCT_DEFINITION | No console settings have been specified. Shown as "Not configured", not clickable. | rail | ❌ | ✅ (as documented) |

## Responsive

The file has no tablet or mobile admin frames. Below `xl` the queue's table
and detail stack. Below `lg` the rail becomes a drawer ("Open admin
navigation"). `e2e/admin-journeys.spec.ts` journey 16 checks 390px, including
no sideways scroll and the drawer reaching Special Routing.

## Screens compared on 2026-09-28

Rendered from the real stack at 1280 × 832 (the frame's width): `/admin`,
`/admin/review-queue`, `/admin/special-routing`. Against the frame:
- the rail order and grouping match;
- the queue's table columns, tabs and detail stack match;
- the header wrapping above was the one visual defect, and it is fixed.

## Re-check requested on 2026-09-29: BLOCKED

The QA patch of 2026-09-29 asked for 6922:837 (`Admin Page - Review Queue`) and 5017:2225
(`Admin/Sidebar`) to be re-read against the live file.

**BLOCKED: EXTERNAL AUTHORIZATION.** The Figma connector still reports that it needs
authentication, and this session cannot run the sign-in. Nothing was read from the file
today. The rows above stand on the 2026-09-28 10:46 UTC reading.

The QA patch did not change the queue's drawn table, tabs, detail stack or pager, or the rail.
It added two things the frame does not draw: the **All reviews** tab and the queue's
membership line. Both are NO FRAME or DEVIATION rows above.

**To close:** re-authorize Figma and re-read both nodes. If the frame now draws an all-reviews
view or a Wilson treatment, rebuild these two rows to it.

Browser evidence of the added screens is the journeys Q and R in
`e2e/review-queue-wilson-journeys.spec.ts` on a local real stack.

