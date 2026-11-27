/**
 * What a review shows as ITS photo (owner bug report, 2026-10-03).
 *
 * A review without an uploaded photo used to borrow the product's canonical
 * listing image for its hero and its cards, so it read as the reviewer's own
 * evidence of holding the item. A review's media is only what was uploaded for
 * that review; without one, the review shows its no-photo state. The product's
 * image stays where it is about the product (the review page's product sidebar,
 * product thumbnails, pickers, link previews).
 */

import { usablePhoto } from "./image.ts";

/**
 * The review's own photos, in order (0094, docs/REVIEW_MEDIA_CONTRACT.md):
 * `photo_urls`, or the single `photo_url` from an older response. Empty when
 * the reviewer added none - never the product's image.
 */
export function reviewPhotos(
  review: { photo_urls?: string[] | null; photo_url?: string | null } | null | undefined,
): string[] {
  const urls = review?.photo_urls?.length ? review.photo_urls : review?.photo_url ? [review.photo_url] : [];
  return urls.map((u) => usablePhoto(u)).filter((u): u is string => Boolean(u));
}

/** The review's own (first) uploaded photo, or null. Never the product's image. */
export function reviewPhoto(review: { photo_url?: string | null } | null | undefined): string | null {
  return usablePhoto(review?.photo_url ?? null);
}
