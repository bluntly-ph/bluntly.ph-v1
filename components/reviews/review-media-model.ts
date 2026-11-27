/**
 * A review's own media — the photos the REVIEWER uploaded — as data.
 *
 * Owner rule (2026-10-05): a review may carry several photos, and NO PHOTO
 * MEANS NO PHOTO. Nothing here ever reads, borrows or substitutes the
 * product's canonical/catalogue/seller image: a review without uploads has an
 * empty list, the composer shows its no-photo state, and the submission sends
 * `photo_urls: []` and `photo_url: null`.
 *
 * Contract: docs/REVIEW_MEDIA_CONTRACT.md. Until the API stores the list, the
 * first photo also goes out as `photo_url`, the single field the API reads
 * today, so a submission is valid against both the old and the new backend.
 */

/**
 * How many photos one review may carry. PROPOSED in the contract, pending
 * RESEARCH: the same 4 the API already enforces for seller reviews
 * (MAX_SELLER_REVIEW_PHOTOS) and answers (AnswerIn.photo_urls). The UI reads
 * it from here only, so it changes in one place when the backend fixes it.
 */
export const MAX_REVIEW_PHOTOS = 4;

/** The list, cleaned: strings only, no blanks, no repeats, capped. */
export function cleanPhotos(urls: unknown, max = MAX_REVIEW_PHOTOS): string[] {
  if (!Array.isArray(urls)) return [];
  const out: string[] = [];
  for (const u of urls) {
    if (typeof u !== "string" || !u.trim() || out.includes(u)) continue;
    out.push(u);
    if (out.length >= max) break;
  }
  return out;
}

/**
 * A stored draft's photos. Drafts saved before multiple photos carry a single
 * `photoUrl`; that one photo is adopted as the list. Nothing else is.
 */
export function draftPhotos(draft: { photoUrls?: unknown; photoUrl?: unknown } | null | undefined): string[] {
  if (!draft) return [];
  if (Array.isArray(draft.photoUrls)) return cleanPhotos(draft.photoUrls);
  return typeof draft.photoUrl === "string" && draft.photoUrl ? [draft.photoUrl] : [];
}

export function addPhoto(urls: string[], url: string, max = MAX_REVIEW_PHOTOS): string[] {
  return cleanPhotos([...urls, url], max);
}

export function removePhoto(urls: string[], index: number): string[] {
  return urls.filter((_, i) => i !== index);
}

/** Swap one photo for another in place, keeping the order the reviewer chose. */
export function replacePhoto(urls: string[], index: number, url: string): string[] {
  if (index < 0 || index >= urls.length) return urls;
  return cleanPhotos(urls.map((u, i) => (i === index ? url : u)));
}

/**
 * What the submission sends. `photo_url` is the first photo (the field the API
 * stores today, and what decides the photo-verified badge); `photo_urls` is the
 * whole list in the reviewer's order. Empty in, `null` and `[]` out — never a
 * fallback image.
 */
export function reviewMediaPayload(urls: string[]): { photo_url: string | null; photo_urls: string[] } {
  const clean = cleanPhotos(urls);
  return { photo_url: clean[0] ?? null, photo_urls: clean };
}

/**
 * The composer's photo step (QA-063). "Skip – I'll add a photo later" means the
 * review goes on with NO photos: whatever was selected or uploaded on the step
 * is dropped from this submission, not just stepped past.
 */
export function skipPhotoStep(step: number): { photoUrls: string[]; step: number } {
  return { photoUrls: [], step: step + 1 };
}
