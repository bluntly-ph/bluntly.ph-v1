/**
 * The picture a shared review travels with (QA-070): the review's own photo,
 * else the canonical product's image, else the site's branded card.
 *
 * Only public images can be chosen. The ownership receipt is never a URL on
 * any public read — it is a private object key, served to administrators through a
 * short-lived signed link — so it cannot end up here, in a preview or in a
 * crawler's cache.
 */
export const FALLBACK_SHARE_IMAGE = "/og-default.png";

/** `lib/image.usablePhoto`'s rule: an http(s) URL that is not a fixture. */
function usable(url: string | null | undefined): string | null {
  if (!url || url.includes("example.com")) return null;
  return url.startsWith("http") ? url : null;
}

export function shareImageFor(reviewPhoto: string | null | undefined, productImage: string | null | undefined): string {
  return usable(reviewPhoto) ?? usable(productImage) ?? FALLBACK_SHARE_IMAGE;
}
