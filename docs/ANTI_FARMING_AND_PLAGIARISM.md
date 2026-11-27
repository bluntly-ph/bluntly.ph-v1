# Anti-farming and plagiarism signals

QA item (2026-09-29): *"The system should include IP detection to identify possible anomalous
voting or vote farming, together with fuzzy word matching for suspicious/duplicated text and
Reverse Image Search for possible image plagiarism. These checks should support moderation and
help identify suspicious or duplicated submissions."*

Every check here is a **moderation signal**. A match files one SYSTEM_DETECTED report into the
same Administrator queue as members' reports (Business Rules §12), labelled by origin, with the
evidence the check saw. A match never:
- removes, hides or unpublishes anything;
- bans, strikes, suspends or puts anyone on probation;
- holds, reverses or confiscates earnings;
- tells the public, or the person flagged, that they were flagged;
- shows anyone an IP address or a network hash.

Every check runs **after** the submission or vote is committed. A check that fails is logged and
rolled back, and the published content stands.

| Signal (`context.signal`) | What it compares | Target | Status |
|---|---|---|---|
| `duplicate_content` | text of reviews, dated updates, answers, comments | the later item | **IMPLEMENTED** |
| `duplicate_image` | review photos, by fingerprint | the later review | **IMPLEMENTED** (internal) |
| reverse image search | review photos against the web | — | **BLOCKED: no provider or API credential** |
| `shared_network_votes` | up-votes' networks, by keyed hash | the member voted for | **IMPLEMENTED**; the BFF path needs `CLIENT_IP_SIGNING_SECRET` (owner action) |
| `collusion`, `vote_velocity`, `vote_concentration`, `verdict_star_mismatch` | pre-existing (ADR-004, ADR-016) | review / member | unchanged |

An Administrator or Super Admin sees each report on Admin → Review queue → **Report**. Its
**Why was this reported?** panel is written from the stored evidence only (`report_explainer`).

## 1. Copied text (`duplicate_content`)

Code: `backend/app/services/text_similarity.py` (pure) and `duplicate_text.py` (finding, filing).
There is one detector. The Review Queue's `duplicate_content` signal, the daily integrity sweep
and submission all use it, so there is no second fraud system.

This is separate from product search on purpose (Business Rules §6). Search forgives typos to
**find** a product; this measures how much of one text another reproduces. They share no code.

**Normalisation.** Unicode NFKC (full-width letters, ligatures), then:
- drop accents and invisible format characters (zero-width spaces);
- casefold;
- turn punctuation and symbols into spaces, and collapse whitespace.

**Meaningful text only.** Below 12 words or 60 characters, a text is never flagged. Two people's
"Good product. Fast delivery. Sulit!" is a coincidence. Before this change, such a pair on one
product scored 1.0 and was flagged.

**Two measures; the higher counts:**

| Measure | Definition | Flags at |
|---|---|---|
| near-identical | Jaccard similarity of the normalised texts' character trigrams | ≥ `DUPLICATE_SIMILARITY_THRESHOLD` (0.85, unchanged) |
| copied passage | share of the shorter text's three-word phrases found in the other | ≥ 0.70 **and** ≥ 8 shared phrases |

The second measure catches a copy with a paragraph added or a few words swapped, which moves
the first. The eight-phrase floor stops a common idiom from counting as a "passage".

Measured on the tests' corpus (`tests/test_duplicate_text.py`):

| Case | Result |
|---|---|
| exact copy | 1.00 / 1.00 |
| light edits | 0.74 / 0.74, flagged as a passage |
| full-width letters, accents, zero-width spaces, curly quotes | ≥ 0.97 |
| unrelated review on the same topic | 0.13 / 0.00, not flagged |

**Where it runs:**

| Surface | When | Candidates |
|---|---|---|
| review, dated update (§4) | after submission is committed | 200 newest of the same product + 200 newest by the same author; best 8 by `pg_trgm` similarity compared in full |
| answer | after posting | same question + same responder (200 newest) |
| comment | after posting | same review + same author (200 newest) |
| reviews in the daily sweep | 05:00 Manila | as for a review; **plus** a platform-wide search (the `%` operator over the existing GIN index `ix_reviews_discussion_trgm`, floor 0.3, capped at 200) for reviews written in the last 2 days, at most 50 a run |

**Rules applied to candidates:**
- Only an **earlier** item can be the source: the later text is flagged, never the honest original.
- A dated update is never compared with its own thread; restating yourself is not copying.
- Text too short to be flagged is never searched for.

**Measured cost** (copy of the test database at 50,472 reviews and 200,259 votes):

| Path | Cost |
|---|---|
| a submission or a queue read (same product and author) | about 10 ms a review, against 8.7 ms for the check it replaced |
| the platform-wide search | about 120 ms a review. That is why only the sweep runs it, and only for new reviews: the sweep is one request inside the scheduler's 8-second budget on Vercel Hobby |
| worst case: 50,000 near-identical long reviews | 90 ms for one submission. Every branch is capped, so a spam wave cannot make a check scan the table |

**Evidence stored.** The matched id and kind, the score and both measures, the shared-phrase
count, a one-sentence reason, up to two further matches, the thresholds, the algorithm version
(`text-dup-v1`) and the detection time. **Never the texts.**

**A template reused by its own author is flagged too.** Re-seeding the defense dataset
(`scripts.defense.seed`, local database, 2026-09-29) produced the intended copied-review
scenario, and one more report. One persona's two reviews of different products share the
paragraph "Compact and the quality is great. Highly recommended to everyone! Sulit na sulit":
11 of the shorter review's 15 three-word phrases (73%). That is the passage rule working as
designed. Pasting one review across products is a known farming pattern, and an Administrator
can dismiss it in one click. It stays a signal, and nothing is hidden or penalised.
`verify --scenarios`: 12 of 12 pass.

## 2. Reused photos (`duplicate_image`): layer 1, internal

Code: `backend/app/services/image_fingerprint.py` (pure), `duplicate_images.py`, migration
`0069_image_fingerprints`.

**At upload** (`POST /reviews/photo`):
- The existing size and magic-byte checks stay.
- The image is then **decoded in full** with a pixel ceiling (50 megapixels). A file whose header
  claims JPEG but whose body does not decode, or a decompression bomb, is refused with
  `415 unreadable_image` before it is stored.
- Each accepted photo gets a fingerprint row with:
  - its SHA-256, for exact copies;
  - a 64-bit **difference hash (dHash)**: greyscale, EXIF-upright, shrunk to 9 × 8, one bit per
    horizontal brightness gradient.

**When a review is published with a photo, or makes its one 72-hour photo swap (§4):**
- its fingerprint is compared with the photo of every **earlier** review, excluding its own thread;
- a match is the same SHA-256, or a Hamming distance ≤ 12 of 64 bits.

Measured (`tests/test_duplicate_images.py`):

| Variant of the same photo | Distance (bits) |
|---|---|
| half size, JPEG quality 30, PNG re-save, 25% brighter | 0 |
| 10% crop | 11 |
| forty unrelated photos | 23 to 41 |

SHA-256 alone would miss every row but an identical file.

**Measured cost** (test-database copy with 50,000 fingerprinted photos, 2026-09-29):
- The first version joined reviews to fingerprints in one query. Postgres cannot estimate how
  few fingerprints pass the Hamming filter, so it hashed all 50,457 reviews first: **141 ms**
  per publication.
- The check is now two short queries:
  - one pass over the fingerprints for the nearest (up to 50; about 11 ms);
  - then the few matching reviews through a partial index `ix_reviews_photo_url` (0069), in
    under 1 ms instead of a 34 ms scan.
- Through the real code: median **12.5 ms**, p90 18 ms, max 21.6 ms; 3 queries per check, no
  N+1.
- The index was added because EXPLAIN showed that sequential scan.

**Honest limits:**
- Two buyers photographing the same boxed product against a white wall can match; that is why
  this is evidence, not a verdict.
- Photos uploaded before migration 0069 have no fingerprint and are not compared. Nothing is
  invented for them, and the migration fetches nothing from Storage. A backfill would need a
  script run with the owner's approval.
- A heavy crop or a mirror image moves the hash beyond the threshold.

Evidence: matched review id, distance, whether the file is identical, other matches, threshold,
algorithm (`dhash64-v1`), detection time.

## 3. Reverse image search: layer 2, external — BLOCKED

**EXTERNAL REVERSE IMAGE SEARCH: BLOCKED — PROVIDER/API CREDENTIAL REQUIRED.**

The PRD names no provider (FR-8 layer 3, ADR-007), and none is procured. The provider seam
already exists: `app/services/integrity_checks.py` has an `ImageCheckProvider` protocol and an
empty `IMAGE_ADAPTERS` registry.
- `GET /admin/integrity-providers` reports `configured: false`.
- Queue cards report `reverse_image_status: "not_configured"`, deliberately never "clear".

Nothing scrapes a consumer search engine, and nothing pretends to have searched. Publication
never waits on it.

**To unblock** (owner):
1. Choose a provider whose terms permit automated lookup (for example, a paid reverse-image API).
2. Provide its credential as an environment variable.
3. Engineering then adds an adapter to `IMAGE_ADAPTERS`, called from the daily sweep (async,
   with a timeout and one retry), whose result becomes a report like the others.

## 4. Vote farming from one network (`shared_network_votes`)

Code: `backend/app/core/client_ip.py`, `backend/app/services/vote_network.py`,
`lib/client-ip-signature.ts`, the BFF (`app/api/bff/[...path]/route.ts`), migration
`0070_vote_network_fingerprints`.

**Which address is believed.** No header a client can write is trusted.

| Path | Believed address |
|---|---|
| browser → Vercel edge → Next.js BFF → API (every vote from the site) | The API sees the **BFF's** address, shared by every voter. The BFF signs the voter's address, which it got from the edge: HMAC-SHA256 of `ip|unix time` under `CLIENT_IP_SIGNING_SECRET`, valid for 120 s. The API believes a valid signature only. |
| a direct call to the API through the edge | on Vercel (`TRUSTED_PROXY` empty + `VERCEL=1`, or `vercel`), the address the edge wrote in `x-vercel-forwarded-for` / `X-Forwarded-For` |
| anywhere else (local, tests, an unknown proxy) | none: every forwarding header is ignored |
| a BFF call **without** a signing secret configured | none. Never the BFF's shared address, which would make every voter look like one network. |

With the secret set, an unsigned call marked as the BFF gets the address the edge saw, so a
farmer cannot hide by faking the marker.

**What is stored.** Never an IP address:
- The network is the address (IPv4) or its /64 (IPv6: one home rotates through its /64).
- It is HMAC-SHA256'd under a key derived from the server secret `PII_HASH_SALT` and truncated
  to 32 hex characters.
- One row per up-vote: review, voter, author, network hash, and whether the account was under
  30 days old.
- Rows are deleted after **30 days** by the existing retention sweep.
- No API returns the hash, and the report evidence holds counts and ids only.

**The rule** (per member voted for, over the last 72 hours of up-votes on their reviews, grouped
by network). It flags when either holds:
- **fresh accounts clustered:** ≥ 3 distinct accounts on one network, ≥ 2 of them under 30 days
  old;
- **large cluster:** ≥ 5 distinct accounts on one network casting ≥ 10 up-votes.

Shared IP alone is never treated as abuse. A household, office, school or mobile carrier
(carrier-grade NAT) puts honest people on one network; three long-standing accounts in one home
never meet the rule. No approved threshold exists in the Business Rules, so these are
**conservative engineering thresholds for flagging only**, configurable as `VOTE_NETWORK_*`.
The report text tells the Administrator to read it with the reviews' voting evidence
(reciprocity, speed, concentration), not as proof.

**Evidence stored.**
- counts: accounts, new accounts, up-votes, the window;
- which rule fired;
- the review ids and, for staff investigation only, the voter account ids;
- the thresholds, the algorithm (`net-hmac-v1`) and the detection time.
- The network and the address are never stored in evidence.

**Measured cost** (test-database copy, 200,259 network rows over 30 days):
- the rule's one query is an index scan on `ix_vote_network_author_network_created`: 0.08 ms;
- the retention purge uses `ix_vote_network_created`;
- recording a vote is one upsert and that query.

**Owner action** (not done here; environment variables are the owner's):
- set `CLIENT_IP_SIGNING_SECRET` to the same long random value on the API and the frontend, per
  environment.
- Until then, votes cast through the site record no network. The check works only for direct
  API calls on Vercel, and every other check is unaffected.

**Found and fixed on 2026-09-30: the rate limiter kept raw addresses.** Redis is not
configured, so the limiter's Postgres fallback keyed its counters by the raw address
(`rate_limit_counters`, e.g. `rl:vote:<address>`), pruned only after an hour. A local rehearsal
of the site-vote path found the voter's address in that table after three votes. The key is now
a keyed hash of the address (`app/core/rate_limit.py`, `test_rate_limit_fallback.py`). The same
client still maps to one counter, and after the fix a full database dump contained no raw
address. Affiliate click sessions still keep a raw address for 30 days by the documented
Architecture §4 retention policy (hashed at 30 days, deleted at 90); changing that is the
owner's decision. See [PR7_QA_ENVIRONMENT.md](PR7_QA_ENVIRONMENT.md) §8.

**Found while auditing, not changed.** The existing first-vote geography
(`request_traffic_service.record_first_vote_geo`) reads Vercel's geo headers on the API. For
votes through the BFF, those headers may describe the BFF's own location rather than the
voter's. That depends on `API_URL`, which could not be read. It needs checking against real data
before those buckets are presented as voter geography.

## 5. Tests

| File | What it pins |
|---|---|
| `tests/test_duplicate_text.py` (16) | exact, lightly edited and padded copies; unrelated text; short generic text never flagged; Unicode normalisation; filed at submission and still published; the original never flagged; cross-product copies found by the sweep; failure never blocks; copied answers; pasted comments |
| `tests/test_duplicate_images.py` (20) | exact and re-encoded, resized, cropped and brightened copies; unrelated photos far apart; corrupt files and decompression bombs refused; 64-bit round trip; resized copy flagged at publication; identical file; a thread update keeping its own photo not flagged; one member's photo on a second product flagged; unrelated not flagged; corrupt upload never stored; no reverse image provider reported honestly; failure never blocks |
| `tests/test_vote_network.py` (10) | spoofed headers ignored off Vercel; the BFF's shared address never used; signed address believed, forged or stale refused; a fake BFF marker cannot hide the caller; keyed hash, IPv6 /64; a household not flagged; fresh accounts flagged with nobody penalised; a large cluster flagged; nothing stored off Vercel; no address column; 30-day purge |
| `tests/frontend/client-ip-signature.test.mjs` (4) | the BFF's signature equals the API's on a shared vector; edge address read only on Vercel; malformed addresses dropped |
| `tests/test_fraud_signals.py`, `tests/test_report_explanations.py` | the queue signal and the sweep use the one detector; explanations from stored evidence |
| `e2e/review-queue-wilson-journeys.spec.ts` D (browser) | on a real stack, a copied review (case and punctuation changed) is published at once, its public page shows no finding, and an Administrator's **Why was this reported?** reads "Possible copied review" and links the original; nothing shaped like an IP on the panel |

Independent QA retest is required. Nothing here is "QA passed".
