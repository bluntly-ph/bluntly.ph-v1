/**
 * Adding an unlisted product from a marketplace link (QA-071, QA-072), as data.
 *
 * The picker used to send `name: query || url`, so a reviewer who pasted a
 * link without typing a search first created a product NAMED with the raw
 * Shopee URL, shown as its title everywhere. Now the name is a separate,
 * editable field, proposed from the product name already written into the
 * link's path by the server (`GET /products/resolve-link`, which never fetches
 * the page), and a link is refused as a name on both sides. The reviewer also
 * picks the category, so the product is browsable from the start.
 */

/** Mirrors `backend/app/services/listing_names.looks_like_url`. */
const URLISH = /(?:^|\s)(?:https?:\/\/|www\.)|^[a-z0-9-]+(?:\.[a-z0-9-]+)*\.[a-z]{2,}\/\S*$/i;

export function looksLikeUrl(text: string | null | undefined): boolean {
  const value = (text ?? "").trim();
  return value.length > 0 && URLISH.test(value);
}

/** What the name field starts with: the link's own name, else what they searched. */
export function initialProposedName(proposed: string | null | undefined, query: string): string {
  if (proposed && proposed.trim()) return proposed.trim().slice(0, 160);
  const typed = query.trim();
  return typed && !looksLikeUrl(typed) ? typed.slice(0, 160) : "";
}

/** Why the new product cannot be sent yet, or null when it can. */
export function linkedProductProblem(name: string, category: string): string | null {
  const value = name.trim();
  if (!value) return "Give the product a name.";
  if (looksLikeUrl(value)) return "Use the product's name, not the link.";
  if (!category) return "Choose a category.";
  return null;
}
