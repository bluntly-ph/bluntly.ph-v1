"use client";

import { GlobalSearch } from "@/components/console/GlobalSearch";

/**
 * The top bar's search (Admin/TopBar 7879:10325; results Search/Admin/Global
 * 8289:29993, No results 8314:32952): reviews, products, sellers and people as
 * you type. Enter with nothing highlighted still opens All reviews with the
 * query, as before. "/" focuses it from anywhere outside a text field.
 */
export function AdminSearch() {
  return (
    <GlobalSearch
      endpoint="/api/v1/admin/search"
      placeholder="Search reviews, products, people…"
      footer="↑↓ to move · Enter to open · Esc to close"
      emptyHint="Try a product name, a seller, a person’s name or a review ID."
      submitHref={(q) => `/admin/review-queue?tab=all&aq=${encodeURIComponent(q)}`}
    />
  );
}
