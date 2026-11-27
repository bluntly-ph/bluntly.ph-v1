# Full-system engineering QA report

Branch `feat/full-business-rules` (base `03c3490`). Engineering evidence only: independent QA owns the
verdict, and nothing here is a QA pass. Production was not touched (read-only queries only); `main` was
not merged; no money moved (PayPal sandbox only, mocked in tests).

The exact final SHA and its canonical CI run are recorded in `docs/QA_HANDOFF.md` and the release note:
a document cannot name the commit that contains it.

## Evidence runs

| Run | What | Result |
| --- | --- | --- |
| Fast lane 35913723662 | pytest on fresh Postgres 17, milestone verifier, migration round trip with data, real-stack browser journeys | 2194 passed · 59/59 claims · round trip OK · 13/13 journeys |
| Canonical 35883412818 (`2e8fbb0`) | full suite on the shared test project | 2099 passed, **1 failed** (test isolation — fixed, see D-CI1) · 59/59 claims |
| Mutation probe 35910145653 + 35910762777 | 11 rules deliberately broken on a throwaway branch (since deleted) | **11/11 caught** (the second run proves the receipt fix below) |

## Business rule coverage

Every settled rule has at least one row in `docs/FULL_SYSTEM_QA_MATRIX.md` with a named test.

| § | Rule | Verified by | Status |
| --- | --- | --- | --- |
| §1 | Link ban; one admin affiliate link to a product page | 68-case corpus (34 hostile, 34 ordinary); every free-text field refuses links; not_product_page | VERIFIED_AUTOMATED |
| §2 | Publish at once; weighted community gate; cold start audited | lifecycle suite; gate test; votes never reopen a decision | VERIFIED_AUTOMATED |
| §3 | "Photo provided"; forged proof cannot verify | API tests; review page | VERIFIED_AUTOMATED |
| §4 | Frozen text; 72h swap; 3-month updates; latest counts; delete rules; aggregate trace | exact boundaries (71:59/72:01, ±5 min), concurrency, browser thread controls | VERIFIED_DATABASE / BROWSER |
| §5 | Canonical product, attach listing | API + moderator browser journey | VERIFIED_BROWSER |
| §6 | Trigram + alias search | API + browser (alias and typo) | VERIFIED_BROWSER |
| §7 | Q&A; asker-only attributed Best Answer; sellers never win | API + authz + browser; Notify me | VERIFIED_BROWSER |
| §8 | Comment gates, new-account cap, collapse at −5, reported-thread Stage 2+ | API; collapse boundary (new); two-tap delete in browser | VERIFIED_DATABASE / BROWSER |
| §9 | DTI/SEC claim; claimed seller barred everywhere | API + browser claim → approval → vote refused | VERIFIED_BROWSER |
| §10 | Seller reviews; order ID private; appeal → substantiation; median | API + authz + browser; median (new) | VERIFIED_BROWSER / DATABASE |
| §11 | Weights: <30 days ½, investigation ½, probation 0, claimed seller 0 | exact 29.99/30 boundary; unit; browser investigation toggle | VERIFIED_AUTOMATED / BROWSER |
| §12 | Weighted escalation, urgent reasons, surge, unfounded pattern, origins | unit + API | VERIFIED_AUTOMATED |
| §13 | Roles | seller role enforced; admin/moderator separation | OPEN_DECISION |
| §14 | Flat 40/30/30; verdict routing; prospective flip; 2.5★ refused; fund off | unit + verifier | VERIFIED_AUTOMATED (+ OPEN_DECISION) |
| §15 | ₱300; no cooldown; batches; provider failure; remittance | exact boundary; open-batch; sandbox mocks | VERIFIED_DATABASE |
| §16 | Price tied to own review; baseline/outlier glance; one line per marketplace | API + verifier + browser | VERIFIED_BROWSER |
| §17 | Public profile, never reporters or earnings | API + browser | VERIFIED_BROWSER |
| §18 | Surge vs own baseline; trust excluded | unit | VERIFIED_AUTOMATED (see T1) |
| §19 | Cleared money only | API + concurrency + browser cashout | VERIFIED_DATABASE / BROWSER |
| §20 | Input security, ownership, receipts, uploads, XSS | authz sweep, receipt privacy, uploads, XSS journey | VERIFIED_DATABASE / BROWSER |

## QA tracker

All 61 items are mapped in `docs/FULL_SYSTEM_QA_MATRIX.md` (engineering status, rule, change, evidence,
whether the tester needs to retest). Superseded items say **SUPERSEDED BY BUSINESS RULE §X**: QA-004 (§2),
QA-031 (§2/§14), QA-035 (§16), QA-051 (§2). Tester-owned Retest Result fields were not touched.

## Role coverage

Anonymous (401s, sign-in redirect keeps its return path) · Stage 0/1/2+ (comment gates, vote weights) ·
account under 30 days and exactly 30 · mature account · under investigation (moderator-set, ½ weight) ·
probation (0) · unclaimed store (claim journey) · claimed seller (vote/review/earn refused everywhere,
responds and appeals, cannot read appeals or admin surfaces) · buyer/reviewer (substantiation) ·
asker/answerer/other (Best Answer) · moderator (claims, appeals, remittance, investigation, aliases,
receipt access passes authorization) · wrong user on every owner operation.

## API coverage

144 operations inventoried from the running app's dependency tree: 57 user-gated, 51 moderator-gated,
23 public, 13 optional-auth. The four "public" writes (internal cron, reading telemetry, traffic, Lazada
postback) check a secret inside the handler (`compare_digest`) or are deliberately unauthenticated and
bounded (traffic; see T1). Every user-gated mutation that takes another account's id is in the ownership
sweep (`tests/test_qa_authz.py`).

## Database invariants

Enforced by the database: one vote per voter per review; one pending seller claim per (store, user); one
seller review per (store, reviewer); one open appeal per seller review; one price per review; one
remittance per (platform, month); one payout per (user, batch); commission row uniqueness; active sub-id
uniqueness; wallet ≥ 0. Serialised by locks (this QA): thread creation and updates per (author, product);
cashout per reviewer.

## Concurrency cases

| Case | Protection | Evidence |
| --- | --- | --- |
| Duplicate first review | advisory lock per (author, product) — **D1** | race test, exactly one root |
| Concurrent updates in one cooldown | same lock — **D1** | race test, exactly one entry |
| Double cashout over cleared funds | user row `FOR UPDATE` — **D2** | race test, ₱300 uncleared stays |
| Duplicate vote | unique index + IntegrityError retry | existing vote suites |
| Duplicate seller claim / seller review / appeal / price / remittance / payout per batch | unique (partial) indexes | existing suites |
| Resubmitting a sent batch | open-batch keys (earlier fix) | sender-id test |

## Migration verification

Production is at `0049_report_resolution`. Head is `0051_product_median_column`. Fast lane, every push:
upgrade blank → head; downgrade two revisions and back; **round trip with real rows** (at head the rating
column holds the median; at 0049 the mean again with nothing lost; back at head the median is recomputed,
threads and backfills in place). The dry-run guard and single-head check are updated for 0051.

## Defects found and fixed in this QA pass: 7 product defects, all fixed

| | Defect | Fix | Regression evidence |
| --- | --- | --- | --- |
| D1 | Concurrent submits created competing threads / two updates in one cooldown | advisory lock | `test_qa_concurrency` (2) |
| D2 | Concurrent cashouts could spend uncleared money | row lock | `test_qa_concurrency` |
| D3 | After 0050 every product showed its old average as the §4 median | 0051 recomputes | migration round trip |
| D4 | 0050 renamed a column the deployed build reads (migrate-before-deploy would 500) | no rename; model maps the attribute | 0051; round trip |
| D5 | Link ban missed `mailto:` and bare IPv4 hosts | two patterns | corpus |
| D6 | Seller page served a stale copy after the owner's own write | signed-in reads uncached | browser journey |
| D7 | Dashboard screens had no `<main>` landmark | `<main>` | width sweep |

Also fixed: the canonical run's only failure (**D-CI1**, a fixed remittance month colliding with an
earlier run's row in the shared test database); a regression test that could not catch a receipt
authorization bypass (M9); two rules with no test at all (comment collapse, seller median); and the
single slowest canonical test's cause (an N+1 in Honesty Fund scoring, 815 s — arithmetic unchanged,
distribution still off).

## Selective mutation testing

| Mutation | Caught by |
| --- | --- |
| 40/30/30 → 35% reviewer | unit, commission import, verifier |
| 30-day age → 29 | new boundary test only |
| claimed-seller vote bar removed | claimed-seller API test |
| frozen text allowed | 4 API tests + verifier |
| 72h → 73h | new boundary test only |
| 3 → 2 months | new boundary test only |
| cleared-only cashout removed | API, concurrency, browser cashout |
| report threshold 1.0 → 0.5 | 5 priority tests |
| receipt authorization bypassed | strengthened ownership sweep (first run: missed — fixed) |
| thread lock removed | 2 concurrency tests |
| cashout lock removed | concurrency test |

## Browser journeys (real API + Postgres, production build)

Sign-in redirect keeps its return path · vote + reload, author cannot vote · comment + two-tap delete ·
thread update opens after 3 months, root delete needs the typed word · cashout on cleared money only ·
Best Answer + Notify me · store owner responds and flags → admin asks → buyer answers, order ID never
public · DTI claim → moderator approval → claimed account's vote refused · investigation / remittance /
alias tools · alias and typo search · price report from the author's own review → admin glance · 11 pages
× 6 widths (320–1440) with no overflow, no page errors, keyboard fields ≥ 16px · stored XSS inert.

## Security cases

Ownership sweep (reviews, comments, notifications, Best Answer, request board, seller ops, admin
surfaces) · receipt privacy (anonymous 401, other 404 `review_not_found`, moderator passes, locator never
public, audited moderator views) · uploads (magic bytes over declared type, size limit, key ownership) ·
link-ban bypasses (encodings, confusables, zero-width, fullwidth, markdown, anchors, schemes, IPs) ·
stored XSS · injection-shaped search · open redirects · session isolation (QA-061 harness; tester to
confirm their setup) · CSRF: the session cookie is httpOnly SameSite=Lax and every write goes through the
same-origin BFF or a Server Action (Next checks Origin), so a cross-site POST carries no session.

## Open product decisions (asserted to stay open)

2.5★ "it depends" earning track · Honesty Fund distribution formula · answer monetisation · automatic
under-investigation trigger · admin vs moderator separation · §21 trust naming · multi-marketplace buy
buttons (data model only).

## Manual QA still required

- The independent retest of QA-001..061 per the matrix, on the tester's own devices.
- QA-061: confirm the two browsers are separate profiles/processes.
- Figma-dependent parity: QA-017, 020, 027, 032, 050, 052, 053 (Figma quota).
- A live PayPal **sandbox** payout end to end (all tests mock the adapter).
- Owner confirmations before the production migration: T2 below, and the rollout order.

## Known technical debt

- **T1** — the §18 view surge reads unauthenticated traffic beacons, so view counts (and therefore a
  review's moderation priority) can be inflated. Bounded: rate-limited, fixed contribution, only raises
  attention. Needs authenticated or sampled view signals.
- **T2** — 0050 treats every legacy commission as cleared (continuity). Production has 0 commissions
  today; strict §19 would leave legacy commissions pending until a remittance. Owner to confirm.
- **T3** — thread uniqueness is lock-enforced, not index-enforced, because production holds 2
  author/product pairs with several pre-§4 reviews. A unique index is possible after those are merged.
- **T4** — canonical CI took 3h02m of pytest (3h08m step) against a 210-minute cap. See the plan below.
- **T5** — `distribute` still adjusts wallets one UPDATE per recipient (scoring is batched now).
- **T6** — login with an unknown address answers 404 `account_not_found` (a deliberate flow decision
  since 4b825ba); it confirms whether an address has an account.

## Suite performance plan (T4)

Measured on 35883412818: the five slowest tests took ~30 minutes; the slowest (815 s) and two more
(~300 s) ran the fund distribution over every fund-routed review ever left in the shared database —
fixed. The review-queue tests (90–166 s) scan the whole accumulated backlog by design. Plan, in order:

1. **Now (done):** remove N+1 paths; fast lane (fresh Postgres) runs the full suite, the verifier, the
   migration round trip and the browser journeys in ~5 minutes on every push.
2. **Next:** a keep-set-validated cleanup of the shared test project's accumulated fixtures (the defense
   population is the keep set), run as a reviewed script — never ad hoc.
3. **Then:** run most DB-backed tests only on ephemeral Postgres, and keep a small canonical suite for
   what truly needs Supabase (storage, receipts, the session pooler, RLS).
