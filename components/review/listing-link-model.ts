/**
 * QA-006: where "Buy it here" goes when a review has no affiliate link.
 *
 * A shop link used to appear only on a review approved to earn a commission,
 * so most reviews offered the reader no way to reach the product at all, and
 * the tester's "Buy it here" failed. The product's own marketplace listing is
 * a plain link to the product: nobody earns from it, it is labelled as such,
 * and it is offered only when it is an https link on a known marketplace (the
 * server checks the host; this re-checks the scheme before rendering).
 */

export type ListingPlatform = "shopee" | "lazada" | "amazon" | "other";

const MARKETPLACE: Record<Exclude<ListingPlatform, "other">, string> = {
  shopee: "Shopee",
  lazada: "Lazada",
  amazon: "Amazon",
};

export type ListingLink = { href: string; label: string };

/** The link to render, or null when there is nothing safe to link to. */
export function listingLink(
  url: string | null | undefined,
  platform: ListingPlatform | null | undefined,
): ListingLink | null {
  if (!url || !/^https:\/\//i.test(url)) return null;
  const name = platform && platform !== "other" ? MARKETPLACE[platform] : null;
  return { href: url, label: name ? `View on ${name}` : "View the listing" };
}

/** Said beside the link, so a plain link is never mistaken for a sponsored one. */
export const LISTING_NOTE = "Not an affiliate link — nobody earns from this click.";
