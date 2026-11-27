import Link from "next/link";
import { CaretLeft, CaretRight } from "@phosphor-icons/react/dist/ssr";

import { pageCount, pageWindow } from "@/components/console/pagination-model";

/**
 * Numbered page links for public lists (MQA-036 search Reviews, MQA-037 Feed):
 * "‹ Previous 1 2 3 … 9 Next ›", with the current page marked and every page a
 * real link, so a place in the list can be shared and returned to. The window
 * rule is the console pager's (`pageWindow`): first, last, the current page and
 * its neighbours; Previous / Next stay in place, disabled, at either end.
 * Server-rendered; nothing here needs JavaScript.
 *
 * One pagination system, two skins: this and the console `Pagination` share
 * `pagination-model` (page count, clamping, the window); only the drawing
 * differs - the console frame's compact cells, the public site's pills.
 */
export function PageNumbers({
  page,
  total,
  size,
  href,
  label,
  maxPages,
}: {
  page: number;
  total: number;
  size: number;
  /** The link for a page number. */
  href: (page: number) => string;
  /** What the pages are of, for the landmark: "Review pages". */
  label: string;
  /** A cap the list itself has (the API pages at most so deep). */
  maxPages?: number;
}) {
  const pages = Math.min(pageCount(total, size), maxPages ?? Infinity);
  if (pages <= 1) return null;
  const current = Math.min(Math.max(1, page), pages);
  const item = "grid h-9 min-w-9 place-items-center rounded-[var(--radius-pill)] px-3 text-[13px] font-semibold";
  return (
    <nav aria-label={label} className="mt-6 flex flex-wrap items-center justify-center gap-1.5">
      {current > 1 ? (
        <Link href={href(current - 1)} className={`${item} gap-1 text-[var(--text-primary)] shadow-[var(--shadow-hairline-inset)] hover:text-[var(--accent-primary)]`} rel="prev" aria-label="Previous page">
          <span className="flex items-center gap-1">
            <CaretLeft size={14} aria-hidden /> <span className="hidden sm:inline">Previous</span>
          </span>
        </Link>
      ) : (
        // Present but disabled on the first page, as the console pager does, so
        // the row does not shift as a reader moves between pages.
        <span aria-disabled="true" aria-label="Previous page" className={`${item} text-[var(--text-primary)] opacity-40 shadow-[var(--shadow-hairline-inset)]`}>
          <span className="flex items-center gap-1">
            <CaretLeft size={14} aria-hidden /> <span className="hidden sm:inline">Previous</span>
          </span>
        </span>
      )}
      {pageWindow(current, pages).map((p, i) =>
        p === "gap" ? (
          <span key={`gap-${i}`} aria-hidden className="px-1 text-[13px] text-[var(--text-secondary)]">
            …
          </span>
        ) : p === current ? (
          <span key={p} aria-current="page" className={`${item} bg-[var(--text-primary)] text-[var(--surface-card)]`}>
            {p}
          </span>
        ) : (
          <Link key={p} href={href(p)} aria-label={`Page ${p}`} className={`${item} text-[var(--text-primary)] hover:bg-[var(--surface-card)] hover:text-[var(--accent-primary)]`}>
            {p}
          </Link>
        ),
      )}
      {current < pages ? (
        <Link href={href(current + 1)} className={`${item} text-[var(--text-primary)] shadow-[var(--shadow-hairline-inset)] hover:text-[var(--accent-primary)]`} rel="next" aria-label="Next page">
          <span className="flex items-center gap-1">
            <span className="hidden sm:inline">Next</span> <CaretRight size={14} aria-hidden />
          </span>
        </Link>
      ) : (
        <span aria-disabled="true" aria-label="Next page" className={`${item} text-[var(--text-primary)] opacity-40 shadow-[var(--shadow-hairline-inset)]`}>
          <span className="flex items-center gap-1">
            <span className="hidden sm:inline">Next</span> <CaretRight size={14} aria-hidden />
          </span>
        </span>
      )}
    </nav>
  );
}

export { countLine } from "./page-numbers-model";
