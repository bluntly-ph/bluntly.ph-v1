# Figma verification — Round 2 blocked items (cloud continuation)

| | |
|---|---|
| Source | Figma file `lso4Ri4hDaZxvCebhUqlY5` ("Page 1", `0:1`), read through the official remote Figma connector as account `Zienxt` (pro team, admin) on **2026-09-24** |
| Method | `get_metadata` for the page tree (170 top-level nodes), then `get_screenshot` and node geometry for each frame below. The frames were compared against the implementation on `fix/cloud-round2-security-design`. |
| Authority | Business Rules (Full Record, 2026-09-23) and owner decisions come before Figma, and Figma comes before the QA expectation (task precedence). A Figma control with no behaviour behind it is not drawn. |
| Currency | The file's last-modified date is not exposed by the connector. These are the frames present on the page on 2026-09-24. The ones Round 1 recorded on 2026-09-14 (`3481:1776`, `3481:1894`, `3954:650`, `7158:4877`, `7159:4873`, `1587:4658`, `1591:5408`, `4218:2148`) are unchanged in structure. |

Classifications used: **functional** (the product lacked behaviour the frame shows), **visual** (layout or
type only), **stale QA expectation** (the tester expected something neither the rules nor the frame ask
for), **no backend capability** (the frame shows a control nothing in the product defines).

## Frames read

| Frame | Node | Used for |
|---|---|---|
| Review page (comment blocks) | `4218:1196` → `4305:2114`, `4305:2113` | QA-020 |
| Share to | `1731:1571` | QA-024 |
| All filters | `1587:4658` | QA-025, QA-053 |
| Sort (hidden in the file) | `1591:5408` | QA-053, QA-057 |
| Categories / Subcategory / Tags | `2355:939` / `2355:2267` / `2355:1317` | QA-025 (confirms Category is navigation, not a filter group) |
| Mobile Search Page for Buyers (Reviews tab) | `3481:1776` | QA-053 pills and chips |
| Mobile Search Page for Reviewers (Questions tab) | `3481:1894` (card `7158:4877`) | QA-050 |
| Mobile Search Page for Sellers | `3954:650` (card `7159:4873`) | QA-052 |
| Seller Page - Review | `4218:2148` (pills `4281:870`, rating card `4271:674`, Top mentions `4295:1223`) | QA-043, QA-057 |
| Question Page | `4218:1856` | QA-050 context |

## Per item

### QA-020 — comment spacing and thread hierarchy
- **Frame** (`4305:2114`, `4305:2113`):
  - a 36px avatar, with the byline 8px after it: name · HonestyScore · level, each split by a 16px
    DotOutline;
  - the age below, and a 24px DotsThree at the header's right;
  - body 12px under the header, then a 20px action row 12px under the body: VoteBar, Reply and Share,
    36px apart;
  - replies indented 36px and starting 20px under the parent's row; threads 40px apart.
- **Compared:** the existing spacing already matched every one of these values. The difference was
  **functional and visual**: the author's own **Delete** sat inside the action row, so rows differed
  between comments. The frame puts per-comment actions under the header's DotsThree. The byline also
  lacked the Honesty Score.
- **Implemented:**
  - one action row for every comment and reply;
  - the author's Delete moved into a ⋯ menu at the header's right, still followed by the "Yes, delete"
    confirmation (QA-039);
  - `reputation_score` added to comment authors (public on every profile, §17), and the HonestyScore
    placed in the byline.
- **Not drawn:** a ⋯ for other people's comments. Comments have no report path, so it would be empty.
- **Tests:** journey *QA-020* (phone); *QA-039* and the business-rule delete journey (through ⋯).

### QA-024 — share sheet destinations
- **Frame** (`1731:1571`):
  - ShareFat + "Share to…" + X;
  - a preview card (title, excerpt, image, author, score, rating);
  - a rule, then "Share your post on other platforms to get more views and boost your commission.";
  - a scrolling row of 48px tiles on a 65px pitch: Facebook, Messenger, Instagram, Add to Story,
    Reddit, X, Viber, Telegram, WhatsApp;
  - then Copy link, Bookmark, More.
- **Classification:** functional.
- **Implemented:**
  - the frame's header, a preview card (title and the review's own words) and the rule;
  - destination tiles: Facebook, Reddit, X, Telegram and WhatsApp on every device, plus Messenger and
    Viber on touch devices, because their share addresses are app links;
  - Copy link, and More (the system sheet, where one exists).
  - Every destination link is built from this site's own URL, encoded, to a fixed host, and opened with
    `noopener noreferrer`.
- **Not drawn:**
  - Instagram and Add to Story have no web share address. A phone reaches them through More.
  - Bookmark: Recent Reads and Bookmarks are omitted by owner decision.
- **Caption:** shown only to the review's author. It mentions commission only when the review carries
  its admin-attached shop link, so no reader is told to "boost your commission".
- **Tests:** `share-model.test.mjs` (the list, encoding, hostile path); journeys *QA-024* on desktop
  and phone, and for the author.

### QA-025 — multiple categories
- **Frame:** All filters (`1587:4658`) has no Category group. Categories (`2355:939`) is a navigation
  list with ➕ expanders, not a filter.
- **Classification:** stale QA expectation relative to Figma. But the live sheet's Category group was
  engineering's addition, and choosing several categories is well defined and servable, so it is
  implemented rather than refused.
- **Implemented:**
  - the API's `category` parameter may repeat (a review in any chosen category is shown);
  - Category checkboxes in the sheet, with one applied chip per category;
  - the desktop rail's categories toggle membership instead of replacing the choice.
- **Tests:** `test_figma_search_filters.py`; `search-tabs.test.mjs`; journeys *QA-025/053 (phone)* and
  *QA-025 (desktop)*.

### QA-053 — All filters structure
- **Frame** (`1587:4658`):
  - Review score (Most Helpful / Hidden Gems / Controversial / Trending, one of);
  - Trust rating (All / 0–70 / 80–100);
  - Budget (a Thrifty ↔ Balanced slider);
  - Time (All time / Past year / Past month);
  - Reset and "Filter Reviews".
- The **Sort** frame (`1591:5408`, hidden in the file) has By date (Latest / Oldest) and Reviewer
  credibility (Highest / Lowest).

| Control | Classification | Outcome |
|---|---|---|
| Time | functional | **Implemented** (`period=year|month`, one definition in `listing_filters.py`) |
| Most Helpful | already served | kept, in Sort (the feed's `wilson` order) |
| Latest / Oldest | functional | **Oldest implemented**; Latest existed |
| Hidden Gems, Controversial, Trending | no backend capability | **not drawn** — nothing in the Business Rules, ADRs or code defines them; inventing a ranking would be inventing product |
| Budget | no backend capability | **not drawn** — "Thrifty/Balanced" brackets are undefined; the only price brackets in code are the Honesty Fund's multipliers, which are not a shopper budget |
| Trust rating, Reviewer credibility | product decision | **not drawn** — ranking people by the trust number waits on §21 (naming and display parked) |

- **Tests:** `test_figma_search_filters.py` (period in and out, oldest order, route bounds);
  journeys *QA-025/053* and *QA-053 Sort*.

### QA-050 — Questions interface
- **Frame** (`3481:1894`, card `7158:4877`): All filters and Sort pills. The row shows "3 active ·
  3s ago", the product, the quoted question, "? 4 Unanswered · 4 Best Answers", "Topics:" chips and a
  100px product image.
- **Classification:** functional (pills, image); no backend capability ("3 active", Topics).
- **Implemented:**
  - pills whose sheets hold Time and Sort by date (Latest / Oldest), both served by the API;
  - `product_image_url` on questions, shown in the frame's 100px tile when an image is stored.
- **Not drawn:**
  - "3 active": nothing counts participants.
  - Topics: questions carry no topics.
  - The per-product "4 Unanswered / 4 Best Answers" summary: the tab lists questions, not products.
    The row keeps its own answer count and Best-answer mark.
- **Tests:** `test_figma_search_filters.py`; journey *QA-050*.

### QA-052 — Seller search interface
- **Frame** (`3954:650`, card `7159:4873`): All filters and Sort pills. The row shows "Claimed
  Profile", the name, "128 reviews · 39 questions answered", stars and a logo.
- **Classification:** functional.
- **Implemented:**
  - `answered_question_count` (the store's live questions with an answer);
  - Marketplace and "Claimed profiles only" filters;
  - Sort by name or most reviews.
  - The row now reads "N reviews · N questions answered · Marketplace". The marketplace is kept
    because two stores can share a name.
- **Not drawn:** a logo. Stores carry none, so the tile shows initials, as before.
- **Tests:** `test_figma_search_filters.py`; journey *QA-052* (UI and API agree).

### QA-057 — seller-review filter and sort
- **Frame** (`4218:2148`): the rating card with star checkboxes (`4271:674`), keyword search,
  Reviews/Questions tabs, then All filters and Sort pills (`4281:870`), "Top mentions" chips
  (`4295:1223`), and the list.
- **Classification:** functional. The page had a native `<select>` instead of the pills.
- **Implemented:**
  - All filters: Rating, the same ticks as the card and one state, plus Time;
  - Sort: By date (Latest / Oldest), Rating (Highest / Lowest), With photos first;
  - an applied Time chip.
- **Defect found:** the list filter compared each review's exact rating with the ticked whole stars.
  Ratings are half steps since 0048, so a 4.5-star review matched nothing and was missing from the
  list even with every star ticked, while the bars above counted it. It now uses the summary's own
  bar rule.
- **Not drawn:** Top mentions. Seller reviews carry no topics.
- **Tests:** `seller-page-model.test.mjs` (half stars, Time); `seller-model.test.mjs` (Oldest);
  journeys *QA-057* on phone and desktop.

### QA-043 — seller-review controls
- **Frame** (`4218:2148`): the seller-review cards draw a vote bar, a comment count, Share and ⋯, and
  a threaded store reply with its own votes and Reply.
- **Rules:** the Seller Account clarification (owner, 2026-09-24) and Business Rules §9–§10:
  - Everyone can Share.
  - The claimed owner gets one public, editable response, and "flag as suspected fake", which starts
    the substantiation and appeal path.
  - Claiming never grants suppression, votes or earnings.
- **Not added:**
  - helpful/unhelpful votes on seller reviews;
  - public threaded replies;
  - an ordinary viewer's report or ⋯.

  The newer business documents do not define any of these. The frame draws them, but Figma ranks below
  the Business Rules, and adding them would invent behaviour: who may vote, what a vote on a
  seller review does, how replies are moderated, and what a viewer's report triggers. No empty ⋯ is
  drawn.
- **Remaining decision (owner):** should seller reviews get (a) votes, (b) threaded public discussion,
  or (c) a viewer report path? And if so, what does each one affect?

## Mobile and desktop

Every implemented change is exercised on a 390px phone and at 1280px desktop, in
`e2e/figma-parity-journeys.spec.ts` or the existing specs. All run against the production build, the
API and Postgres 17, and every journey also asserts there is no sideways scroll. Local run:
**37/37 journeys** (13 business-rule, 13 QA round 2, 11 Figma parity).

## What is still Figma-dependent or decision-dependent

| Item | What remains | Owner of the next step |
|---|---|---|
| QA-053 | Hidden Gems / Controversial / Trending / Budget definitions; Trust rating (§21) | Product owner |
| QA-043 | Seller-review votes, threaded replies, viewer report | Product owner |
| QA-050 | "3 active" and Topics need data models (participants, topics) if wanted | Product owner |
| QA-057 | "Top mentions" needs a topic model for seller reviews if wanted | Product owner |
| QA-024 | Instagram / Add to Story as direct buttons need a native app share path | Product owner (platform) |
