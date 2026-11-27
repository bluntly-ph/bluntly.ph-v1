# Business Rules — engineering implementation record

Source of truth: *Bluntly.ph — Business Rules (Full Record)* (2026-09-23), sections §1–§21.
Change map: *Old Code vs New Business Rules*. Branch: `feat/full-business-rules`, built on the
public-on-submit candidate `03c3490`. Schema: Alembic `0050_business_rules` (reversible; the
downgrade leaves added Postgres enum values in place, which Postgres cannot drop).

Status language: **engineering implementation complete, ready for independent QA retest.** Nothing here
says QA passed. Production is untouched: no merge, no production migration, no backfill.

## Rule by rule

| § | Rule | Where it lives | Notes |
| --- | --- | --- | --- |
| 1 | No links anywhere except the admin-attached affiliate link, which must be a product page | `app/core/link_policy.py` (normalise → detect: NFKC, invisible characters, confusables, `hxxp`, "dot com", schemes); validators on reviews, comments, questions, answers, seller reviews, seller responses, appeals, requests, display names; `referral_service.validate_affiliate_url` (`not_product_page`) | Multi-market buy buttons: **data model only** (listings per platform under one product). Showing them together waits on Shopee/Lazada written confirmation. |
| 2 | Publish at once; the community gate (trust-weighted Wilson) queues for admin; admin approval attaches the link and earning | `earn_gate.gate_state` / `maybe_queue`: Wilson lower bound ≥ 0.65 with ≥ 3 Stage-2+ voters, over stored vote weights | Cold-start substitution is audited separately (`_audit_cold_start`), never counted as a vote. |
| 3 | Earning needs an ownership photo; badge says "Photo provided" | `_require_ownership_evidence`; `ReviewOut.photo_provided`; UI copy | No purchase-verification claim anywhere. |
| 4 | Text/rating/verdict frozen; one photo swap in 72h; updates are dated thread entries every 3 calendar months; latest counts; delete an entry, root deletes the thread with explicit confirmation; post-payout deletions shown only in aggregate | `review_service` (`add_thread_update`, `update_review`, `delete_entry`, `removed_after_payout_count`); product rating = median of each thread's latest entry; UI: `ReviewThreadPanel`, composer `?update=` mode, product note on the review page | Root deletion needs `?confirm=delete-thread`; the UI also asks for the word "delete". |
| 5 | One canonical product, many platform listings; submissions canonicalised or attached | `canonical_service.attach_listing` / `add_aliases`; moderator Products page | |
| 6 | Trigram typo tolerance + alias library, built together | `product_search.py`: exact → alias → word prefix → trigram, ranked in explainable tiers | Typo search and fraud fuzzy matching stay separate systems (owner decision). |
| 7 | Q&A on products or stores; sellers comment/report only — never vote, compete, win or earn | `qa_service` (`seller_cannot_answer` unless a store answer, `seller_cannot_win`); Best Answer is asker-only, attributed and audited; question subscriptions ("Notify me") | **Answer monetisation: not built** (parked with the Honesty Fund). |
| 8 | Stage 1 to comment; new-account badge and rate cap; auto-collapse; Stage 2+ on reported threads; sellers may comment | `comment_service._may_comment` (30/h cap for accounts under 30 days), `is_collapsed` (net ≤ −5) | |
| 9 | Claim by DTI/SEC cross-checked to the shop name; claims grant only response + analytics; claimed sellers barred from voting, reviewing and earning, permanently | `seller_service` claim fields and `shop_name_matches`; `bar_claimed_seller` zeroes weights and revokes links | |
| 10 | Seller reviews: optional self-reported order ID; seller appeal → admin asks reviewer to substantiate; median aggregate | `SellerReviewAppeal`; `/sellers/reviews/{id}/appeal`, `/admin/seller-review-appeals/*`, reviewer page `/sellers/appeals/[id]` | Order ID is never public; admins see it on an appeal only. |
| 11 | Visible counts + backend weight; <30 days halves; probation zeroes; under investigation halves; claimed sellers zero | `trust.gate_vote_weight` / `weight_of`; `ReviewVote.vote_weight` snapshot | **"Under investigation" trigger: manual moderator action only** (`PUT /admin/users/{id}/investigation`, audited) until the rule is written. |
| 12 | Reports as weighted escalation votes to one threshold; urgent reasons escalate at once; bursts count; unfounded reports reduce the reporter's weight | `report_service` (threshold 1.0, `URGENT_REASONS` = safety threat and personal information, surge, unfounded penalty 3→0.5 and 6→0.25); `moderation_priority` v2 with `origins` | Every card and report says User report / System detected. |
| 13 | Roles | Seller role fully enforced as above | **Admin/Moderator separation: open**, one moderator role as before. |
| 14 | Flat 40/30/30; track by verdict, stars break the tie on "it depends"; track flips going forward on an update | `earnings.split_for_review`; `earning_track.track_for` | **2.5-star boundary: `PRODUCT_RULE_PENDING_2_5 = True`** — a 2.5★ "it depends" review is refused a decision (`earning_track_pending_owner_rule`) rather than guessed. **Honesty Fund distribution formula: not invented** — distribution is off (`honesty_fund_distribution_enabled = False`, `honesty_fund_formula_pending`). |
| 15 | Pay only reconciled money; ₱300 minimum; no cooldown; batched processing | `payout_service.withdrawable`, `request_cashout` (tops up the batch), `record_remittance` clears a platform-month; Transfer page | PayPal remains sandbox-only. Nothing in this work calls a real payout. |
| 16 | Line graph per marketplace, never blended; reports attached to the reporter's own review; outliers held for a glance | price series in `PricePanelOut.series`; `submit_observation` requires the caller's own published review; `PriceHistoryChart` | |
| 17 | Public profile shows stage, score, reviews, people helped, comments, interactions both ways; never reporters or earnings | `profile_service`; `PublicProfileOut`; `/u/[handle]` | |
| 18 | Activity feeds priority only as surge vs own baseline; reputation/trust/verification never in priority | `activity_surge.py`; the priority policy's facts exclude trust | |
| 19 | Dashboard cashout only against cleared, reconciled funds | `GET /payouts/balance` (withdrawable vs pending clearance); `CashoutButton` | |
| 20 | Input security checklist; link ban platform-wide | as §1, plus existing upload validation and rate limits | |
| 21 | Trust naming | unchanged labels | **Open: naming only.** The Honesty Score search filter (QA-049) waits on this. |

## Owner decisions carried

Dark Mode removed. Recent Reads / Bookmarks stay omitted. Figma 1:1 remains the target. The avatar is the
navigation entry; no mobile bottom nav. `/dashboard/insights` is intentional. Typo search and fraud
fuzzy matching are separate systems. Contracts (the old review-contract feature) are retired, with their
routes, pages and site-map entry.

## Verification

- Backend: `pytest` (fast CI job *DB fast feedback*, postgres:17: `alembic upgrade head → downgrade -2 →
  upgrade head`, the full suite, the milestone verifier, and a migration round trip with data), `ruff`.
  The same workflow runs the real-stack browser journeys (`e2e/br-journeys.spec.ts`). Business-rule suites: `tests/test_business_rules_unit.py`,
  `tests/test_business_rules_api.py`, `tests/test_link_policy.py`.
- Canonical CI: `gh workflow run CI --ref feat/full-business-rules` (the isolated-database job).
- Frontend: `npx tsc --noEmit`, `npx eslint`, `npm run test:frontend`, `npm run build`.
- A signed-in render check of every changed page at 320/390/1440 against a fixture API (production build)
  covered: no page errors, no horizontal overflow, the expected copy, Notify me, cashout, the avatar
  cropper (2.5 MB PNG → 512×512 JPEG), and the typed confirmation on thread deletion.

## Production follow-ups (not done here — production is read-only for this work)

- Apply migrations `0050_business_rules` and `0051_product_median_column` and deploy, after independent
  QA retest and owner sign-off (and the owner's call on legacy commission clearing — QA report T2).
- `PRODUCTION_MODERATION_ACTION_REQUIRED`: a slur comment by account `zienxt` on showcase review
  `00000000-0000-0000-0000-0000000e0001`, and a profane seller review on seller
  `6481f788-e4cd-482b-b121-ea744ee662ad`.

## Full-system QA amendments (2026-09-24)

Found and fixed while testing the implementation end to end (`docs/FULL_SYSTEM_QA_REPORT.md`):

- **§4 — one thread under concurrency.** Thread creation and updates take a transaction-scoped advisory
  lock per (author, product); a unique index is not possible while production holds 2 legacy
  author/product pairs with several pre-§4 reviews.
- **§19 — cleared money under concurrency.** A cashout re-reads the reviewer's row `FOR UPDATE` before
  computing what is withdrawable.
- **§4 rating column.** `products.avg_rating` keeps its name (the model attribute is `median_rating`) so a
  migrate-before-deploy rollout cannot break the running build; 0051 recomputes every median.
- **§1 — link ban.** `mailto:` and bare IPv4 hosts are links too; a 68-case corpus pins detection and
  false positives. Plain email addresses stay allowed (personal-information reports cover them).
- **Sellers.** Signed-in reads of a store are uncached, so an owner's response or appeal is on the page
  it refreshes to.
- **Head revision:** `0051_product_median_column`.

