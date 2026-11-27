import "server-only";

import { apiFetch } from "./api/client";

type Schemas = import("@/lib/api-types").components["schemas"];
export type SearchProduct = Pick<Schemas["ProductOut"], "id" | "canonical_name" | "image_url" | "review_count" | "line">;
export type SearchCard = Schemas["SearchCardOut"];
export type ProductMatch = { product: SearchProduct; card: SearchCard | null };
export type ProductResolution = {
  /** The products the query names, most-reviewed first (the Switch sheet). */
  matches: ProductMatch[];
  /** The one the bar shows: the reader's pick, else the best match. */
  chosen: ProductMatch;
  /** The words that named the product, and what is left (the question). */
  productTerms: string;
  rest: string;
};

/**
 * Which product a search names (Figma Mobile Search v10B 7693:7490 and the
 * Questions v3/v6 frames): "jisulife fan noise library" is the Jisulife fan,
 * asked about noise in a library. Null when nothing matches, and the page
 * searches as before.
 *
 * Resolved by the API in ONE call (GET /api/v1/search/resolve; cost plan,
 * 2026-10-22). This used to run here: up to five product searches, one per
 * leading run of words, then one search-card call per match (up to six more),
 * each a billed function call and a database transaction. The rules moved to
 * backend/app/api/v1/routes/pages.py `resolve_product` unchanged: each leading
 * run (dropping up to four words from the end) is looked up, the run kept is
 * the LONGEST whose best match is as reviewed as any run found, and the words
 * after it are the question. Public, so it is cached for 60 s.
 */
export async function resolveSearchProduct(q: string, pick?: string | null): Promise<ProductResolution | null> {
  if (!q.trim()) return null;
  const params = new URLSearchParams({ q: q.trim().slice(0, 200) });
  if (pick) params.set("pick", pick.slice(0, 64));
  return apiFetch<ProductResolution | null>(`/api/v1/search/resolve?${params}`, { revalidate: 60 }).catch(() => null);
}
