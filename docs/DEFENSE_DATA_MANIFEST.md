# Defense data manifest

What the defense dataset contains, why each part exists, and which screen shows
it. Source of truth: `backend/scripts/defense/dataset.py` (content) and
`seed.py` (how it is written). Counts are from the seed run of 2026-09-25 on a
local Postgres; the seed is deterministic, so TEST receives the same.

**How it is written.** Through the application's own API, as the real actors
would: members register and onboard, reviewers submit products and reviews,
moderators canonicalize, decide, attach links, import marketplace reports.
Only time is rewritten afterwards (`stamp`, `audit`): the API stamps "now", and
the story spans seven months. Derived state (trust stages, Wilson scores,
product aggregates) is then *recomputed by the platform*, never written by hand.

**What it never contains.** No password, code or credential (accounts get a
random password nobody records; sign-in is by emailed code). No real person's
data: every member and store is fictional; persona addresses are "+" aliases of
the team inbox, community addresses are `@demo.bluntly.ph` (never delivered).
No placeholder text: `verify` sweeps every visible field and
`tests/test_defense_scripts.py` sweeps the dataset source. No hateful, sexual or
personal content in the moderation examples.

## Accounts — 32

| Account | Role / state | Purpose | Screens |
|---|---|---|---|
| `mariareyes` (Maria Reyes) | Stage 2 *Verified Buyer*, joined 7 months ago; wallet ₱814.80 (₱368.40 cleared, ₱446.40 clearing); one paid cashout | established reviewer: earnings, cashout, asks a question | `/dashboard`, `/dashboard/transfer`, `/dashboard/history`, `/u/mariareyes` |
| `paolo_mendoza` (Paolo Mendoza) | Stage 1 *Contributor*, joined 6 days ago (vote weight halved) | new reviewer: first votes, first full review | `/reviews/new`, `/dashboard` |
| `kristinev` (Kristine Villanueva) | Stage 3 *Established Reviewer* from 5+ verified counted reviews, helpfulness ≥ 49.5, 20+ distinct eligible voters | advanced reviewer, Best Answers | `/u/kristinev`, question pages |
| `rico_powerhub` (Rico Tan) | claimed seller of PowerHub PH (cannot vote or earn) | seller owner | `/sellers/{id}/dashboard`, store page |
| `mod_joanna` (Joanna Lim) | moderator | every queue | `/moderate/*` |
| `jomar_deals` (Jomar Aquino) | under investigation; generic reviews up-voted by a five-account ring | fraud detection | report tab, `/moderate/users` |
| 26 community members | Stages 1–3, joined 4–8 months ago | reviews, votes, comments, answers, orders | everywhere |

Ring members: `gio_salazar`, `raf_villareal`, `amiel_sy`, `ivan_dizon`,
`kathleen_go` (they also write ordinary reviews; only their votes on Jomar are
the pattern).

## Catalogue — 15 products, 2 submissions, 5 stores

| Product | Category | Reviews | Real affiliate listing | Image source (official maker) |
|---|---|---|---|---|
| Anker 737 Power Bank 24,000mAh, 140W | electronics-tech | 4 | — | anker.com |
| Anker Nano Power Bank 10,000mAh, 30W | electronics-tech | 5 | — | anker.com |
| Jisulife Life9 Handheld Fan 4,800mAh | electronics-tech | 5 | — | jisulife.com |
| Soundcore P20i | audio | 4 | — | soundcore.com |
| Soundcore Liberty 4 NC | audio | 3 | — | soundcore.com |
| UGREEN Nexode Charger 65W | electronics-tech | 4 | — | ugreen.com |
| Apple iPhone 17 | electronics-tech | 4 | Shopee | apple.com |
| Apple iPad 11th Gen, A16 | electronics-tech | 2 | Shopee | apple.com |
| DJI Osmo Action 6 | electronics-tech | 3 | Shopee | dji.com |
| Valve Steam Deck OLED | gaming | 2 | Lazada | steamdeck.com |
| Sony PlayStation 5 Digital | gaming | 3 | Lazada | playstation.com |
| Akko 5075B Plus | office-productivity | 2 | — | akkogear.com |
| Apple MacBook Air M2, 13-inch | electronics-tech | 2 | — | apple.com |
| CeraVe Foaming Facial Cleanser 473mL | beauty | 2 | — | cerave.com |
| Uratex Classic Mattress 6 inches | home-living | 2 | Shopee | uratex.com.ph |

- **Images**: the maker's own product image, downloaded at seed time and
  uploaded through `POST /products/{id}/image` (TEST only; not stored in Git).
  Review photos on TEST are the same image uploaded under each reviewer.
- **Listings**: the six real affiliate links are the owner's, verbatim from
  `seed_showcase.py`; a product without one has none (no dead buy buttons).
  Each is recorded as the product's listing (the migration 0054 behaviour).
- **Aliases**: 36 (e.g. `powercore` → Anker 737).
- **Submissions**: "xiaomi power bank 20000mah 22.5w" (to be *named* live) and
  "anker nano powerbank 10k w/ built in cable" (to be *attached* live).
- **Stores**: PowerHub PH (Shopee, claimed by Rico, DTI-3318207), Cebu Gadget
  Hub (Shopee, claim pending, DTI-5902144), Gadget Galaxy Manila (Lazada),
  Tahanan Home Finds (Lazada), GlowUp Skin Hub (Shopee) — all fictional.

## Reviews — 48 (+1 thread update)

| State | Count | Example | Shows |
|---|---|---|---|
| Monetized (affiliate link live) | 7 | Maria's Uratex, iPhone 17; Steph's iPhone | earning path end to end |
| Approved, awaiting a link | 27 (5 on products with a listing) | the DJI Osmo Action 6 reviews | affiliate-link queue |
| Honesty Fund track (≤ 2★) | 4 | Maria's CeraVe "Hard pass" | fund routing |
| In the earnings queue (passed the gate by real votes) | 2 | Maria's Jisulife (19 votes), Mark's iPhone (18) | review queue |
| Rejected, with a reason | 1 | Ken's Life9 (photo is the listing image) | rejection |
| Unverified (no photo; never earns) | 7 | Paolo's fan; Jomar's PS5 near-copy (3 days old) | verification, copied-text detection |
| Removed by its author | 1 | Kathleen's iPhone | author delete |
| Thread update | 1 | Maria's Anker 737, five months later | §2 threads |

Verdicts cover *Yes, absolutely* / *It depends* / *Hard pass*; no review sits
on the unresolved 2.5-star *It depends* earning rule. Text is English,
Filipino and Taglish ("Sulit na sulit", "brownout", "MRT"), written per
reviewer.

## Community

| Entity | Count | Notes |
|---|---|---|
| Helpfulness votes | ~255 | deterministic per voter; the ring's votes on Jomar, and Jomar's up-votes back on one review by each ring member (the reciprocity the collusion check reads) |
| Comments and replies | 37 | 13 threads; one review with 9 |
| Questions / answers | 11 / 17 | open, answered, Best Answer (asker-picked), 2 store-directed (one answered by Rico, one unanswered) |
| Store reviews | 16 | four dimensions; Rico's responses; one appealed as suspected fake, substantiation requested |
| Review requests | 3 | each names a catalogue product (2026-09-29): Anker Nano (3 answers; Hazel picked Kristine's as the Best Answer, so it is off the board but on its page), iPhone 17 (2 answers, waiting for Joshua to pick; his "2 people answered your request" notice links to it), Akko 5075B (asked after its last review: unanswered) |
| Review opens | ~4,100 in 554 hourly buckets, 13 Philippine cities | dashboard views, momentum, analytics map; "times opened", nothing identifies a reader |
| Notifications | 116 | dated to what they announce; older than two weeks read |

## Prices — 54 observations

| Scenario | Product |
|---|---|
| Shopee only | Anker 737, DJI Osmo Action 6 |
| Lazada only | Steam Deck OLED, PS5, Liberty 4 NC |
| Both marketplaces | iPhone 17, Jisulife Life9, UGREEN 65W |
| Outlier held (< 0.5× the median) | iPhone 17 at ₱24,999 (Steph) |
| Held, no baseline yet | Uratex on Lazada (Dennis) |

## Money (PayPal **sandbox** references only)

| Entity | Count | Notes |
|---|---|---|
| Click sessions | 20 | through each review's `/r/{id}` redirect |
| Marketplace report rows | 20 | a real-format Shopee export (16) and Lazada export (4), imported through `admin/affiliate/import`: 17 completed, 2 pending, 1 cancelled |
| Commissions | 17 | flat 40/30/30; only completed/delivered orders |
| Remittances | 4 | Shopee May–Jul, Lazada Jun 2026 (months that ended 30+ days ago) |
| Payouts | 2 | Maria ₱369.60 paid (`PAYPAL-SANDBOX-8K2Q4471`), Steph ₱690.00 scheduled |

Wallets: Maria ₱814.80, Kristine ₱483.00 (₱186 cleared: below the ₱300
minimum), Ivan, Rina (cleared, below minimum), Carla (clearing).

## Moderation

| Item | State |
|---|---|
| Report: "Contains a phone number and an offer to sell a unit outside the platform." | open, **urgent** (personal information), 7 hours old |
| Report: "Possible copied review: …" (Kristine on Jomar's P20i) | open, normal, 2 days old |
| Report: "Incorrect product listing? …" | resolved — dismissed with a note |
| System report: vote concentration on Jomar | open, system-detected, with the cohort facts |
| Report: "The photo looks like the store's own listing image…" (Vince on Jomar's UGREEN) | **escalated**: left the open queue, shown as "Escalated" in the Overview's activity |
| System reports from the integrity sweep (run once by the seed, 2026-09-29) | open, system-detected, with stored evidence: **copied text** on Jomar's PS5 review (0.875 similar to Carla's, linked), and **vote collusion** on each of Jomar's six reviews (5 of 8 up-voters up-voted back) |
| Investigation: "Suspected coordinated voting: …" | Jomar, set by Joanna |
| Audit log | 114 entries dated across seven months |
