# Review media contract (product reviews)

Owner: RESEARCH (backend / data). Consumer: PIM (composer, review page, cards).
Status: implemented on `defense-build-oct6` (migration `0094_review_photos`).
This file describes the CURRENT implementation, not a design. No Figma here.

## The one rule

**NO PHOTO = NO DEFAULT PHOTO.** A review whose author added no photos has
`photo_urls: []` and `photo_url: null` — in the database and on every API
response. The product's listing image is `product.image_url` (product context)
and is never written to, or returned as, a review's photos. A client can always
tell `review.photo_urls == []` apart from `product.image_url == "https://…"`.

## Data model

| Column (`reviews`) | Type | Meaning |
|---|---|---|
| `photo_urls` | `text[] NOT NULL DEFAULT '{}'` | The reviewer's own photos of the item, **array order = display order**. CHECK `cardinality(photo_urls) <= 4`. |
| `photo_url` | `text NULL` | Always `photo_urls[1]` (first photo) or NULL. Kept for readers written for one photo (cards, dashboards, the duplicate-photo check). Kept in step by `models/review.py::_sync_photos` on every flush. |

Same shape store reviews (`seller_reviews.photo_urls`) and answers already use —
no second media system, no media table. Existing single-photo reviews were
backfilled (`photo_urls = {photo_url}`).

Media type: photos only (no video, no documents). Proof of purchase is a
different object in a PRIVATE bucket (`POST /reviews/receipt`) and never
appears in `photo_urls`.

## Limits

| Rule | Value | Where |
|---|---|---|
| Photos per review entry | **4** (`MAX_REVIEW_PHOTOS`) — same as store reviews and answers | `app/models/review.py`, schema `max_length`, DB CHECK |
| File size | **4 MB** per photo (`MAX_REVIEW_PHOTO_BYTES`) → 413 `file_too_large` | `services/storage.validate_review_photo` |
| Types | **PNG, JPEG, WebP**, sniffed from the bytes (the browser's Content-Type is ignored); HEIC refused → 415 `unsupported_media_type`; a corrupt/bomb image → 415 `unreadable_image` | same |
| URL | http(s) only, and an object **this author** uploaded (`<review-photos>/<user_id>/…`) → else 403 `photo_not_owned` | `routes/reviews._own_photos_or_403` |

## Endpoints

### Upload one photo — `POST /api/v1/reviews/photo`
- `multipart/form-data`, field `file`. Signed-in user.
- 200 `{"url": "https://…/review-photos/<user_id>/<uuid>.<ext>"}` — a public URL.
- Validation (size, type, decode) happens **before** storage: a refused file
  stores nothing and records nothing.
- Storage down / not configured → 503 `storage_unavailable`, nothing saved.
- One file per call. Upload each photo, keep the URLs in the order shown.
- The upload is not attached to anything yet; it becomes review media only when
  its URL is submitted in `photo_urls`.

### Submit a review — `POST /api/v1/reviews` (and an update entry, `POST /reviews/{id}/updates`)
- `photo_urls: string[]` — the photos to publish, in display order, ≤ 4.
  Duplicates are dropped (first occurrence kept). `[]` = no photos.
- `photo_url: string | null` — single-photo clients only; means
  `photo_urls: [photo_url]`. **Ignored when `photo_urls` is sent**, so
  `photo_urls: []` always wins (Skip).
- 403 `photo_not_owned` if any URL is not the author's own upload;
  422 for more than 4 or a non-http(s) URL.
- `verification_status` is `verified` when at least one photo is the author's
  own upload ("Photo provided" — possession, not proof of purchase).

### Replace the photos (the one swap, Business Rules §4) — `PATCH /api/v1/reviews/{id}`
- Author only (else 403 `not_review_owner`). Once (`photo_swap_used` 409),
  within 72 h of publishing (`photo_swap_window_closed` 409).
- Body `{"photo_urls": [...]}` replaces the **whole ordered set** (or
  `{"photo_url": "…"}` = a set of one). An empty set is refused
  (422 `photo_required`): a swap replaces photos, it does not remove them.
- Recorded as a new version (`snapshot.photo_urls`, note "photo replaced").
- No other field may change (409 `review_content_frozen`).

### Delete
There is no endpoint that deletes a single photo of a published review.
Published content is frozen (§4); the swap above is the only change.
Before submitting, "removing" a photo is client-side: leave its URL out of
`photo_urls`.

## Responses

Every review object (`ReviewOut`: `GET /reviews/{id}`, `GET /reviews`,
`review` inside `GET /reviews/{id}/full`, `/reviews/feed`, `/reviews/mine`,
threads) carries:

```json
{ "photo_urls": ["https://…/a.jpg", "https://…/b.jpg"], "photo_url": "https://…/a.jpg" }
```

and, with zero photos, `{ "photo_urls": [], "photo_url": null }`. Feed/full
responses carry the product separately: `product.image_url` (may be set while
`review.photo_urls` is empty — draw the review's no-photo state).

## Drafts

`/review-drafts` stores the composer's form state as opaque JSON; the server
does not read photos from it and never publishes from a draft. Publishing is
only `POST /reviews` with `photo_urls`. A photo in a draft that is not in the
submitted list is not published.

## Skip ("I'll add a photo later")

Submit `photo_urls: []`. The review has no photos — the swap within 72 h is
the only way to add them after publishing (it must add at least one).

## Storage and cleanup

- Bucket `review-photos` (PUBLIC — review photos are drawn on the published
  page). Objects are keyed by uploader: `<user_id>/<uuid>.<ext>`.
- A rejected upload never reaches storage. A storage failure returns 503 and
  nothing is recorded. The only DB row an upload writes is its fingerprint for
  the duplicate-photo check (`image_fingerprints`), best-effort.
- **Known gap (unchanged from the single-photo design):** a photo uploaded and
  then removed/skipped before submitting stays in the bucket, unreferenced, under
  the uploader's prefix. It is not review media (no review lists it). There is
  no orphan sweep yet; adding one needs the storage listing on the production
  project (Supabase connector authorisation required to verify safely).
- The duplicate-photo check (reused photo of an earlier review) compares the
  review's FIRST photo (`photo_url`).

## Product image vs review photos elsewhere (audited)

- `lib/review-media.ts::reviewPhoto` returns only the review's own photo, never
  the product's (owner rule 2026-10-03).
- Share / OpenGraph (`app/reviews/[id]/page.tsx`): the link preview image is the
  review's photo, else the product image, else the site card. That is
  link-preview imagery about the product, not review evidence, and it is never
  serialized as a review photo.
- Contributor dashboard "best reviews" and the admin Overview queue preview have
  a thumbnail field named `image_url` (product image first, then the review's
  photo). It is a product thumbnail, not review media.

## Production verification (Supabase connector, read-only, 2026-10-05)

- Production project `byobedbhodhvocgrkrse` is at alembic `0085_email_outbox`:
  `photo_urls` does NOT exist there yet (0086–0094 pending, owner authorisation).
- 204 reviews, 156 with a photo: **all 156** are objects in `review-photos`
  under their own author's prefix; **0** equal the product's `image_url`; 0 point
  outside the bucket. 0094's backfill will turn each into a one-photo list.
- Buckets: `review-photos` (public), `review-receipts` (private),
  `product-images` (public), `avatars` (public).

## Change log
- 2026-10-05 RESEARCH: `photo_urls` added (0094), ≤4, ordered; zero photos = `[]`.
