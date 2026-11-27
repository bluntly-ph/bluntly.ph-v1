"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { ArrowLeft, CaretDown, CaretRight } from "@phosphor-icons/react";

import { PAGE_SIZES, pageCount, pageWindow, shownRange } from "./pagination-model";

/**
 * The console pager (Figma component Pagination; Screen/Admin/People
 * 7998:11931): the range on the left, then ← pages → and the page size.
 *
 * Two ways to drive it:
 * - URL: give `basePath` and `query` (the screen's other parameters, kept as
 *   they are), and every page is a real link — server-rendered screens, the
 *   back button and a shared link all keep the page.
 * - State: give `onChange`, for a screen that holds its list in memory.
 * - Own URL scheme: give `hrefFor(page, size)`, for a screen whose URL pages
 *   another way (the Review Queue's ?offset=&limit=); pages are still links.
 *
 * Moving to another page size starts again from page 1.
 */
export function Pagination({
  page,
  size,
  total,
  sizes = PAGE_SIZES,
  basePath,
  query = {},
  pageParam = "page",
  sizeParam = "size",
  onChange,
  hrefFor,
  label = "Pages",
}: {
  page: number;
  size: number;
  total: number;
  /** The sizes offered; [] hides the size menu. The first is the default and is left out of the URL. */
  sizes?: readonly number[];
  basePath?: string;
  query?: Record<string, string | undefined | null>;
  pageParam?: string;
  sizeParam?: string;
  onChange?: (next: { page: number; size: number }) => void;
  hrefFor?: (page: number, size: number) => string;
  label?: string;
}) {
  const router = useRouter();
  const pages = pageCount(total, size);
  const { first, last } = shownRange(page, size, total);
  const n = (v: number) => v.toLocaleString("en-PH");

  const href = (p: number, s: number = size) => {
    if (hrefFor) return hrefFor(p, s);
    const params = new URLSearchParams();
    for (const [k, v] of Object.entries(query)) if (v) params.set(k, v);
    params.delete(pageParam);
    params.delete(sizeParam);
    if (s !== sizes[0] && sizes.length) params.set(sizeParam, String(s));
    if (p > 1) params.set(pageParam, String(p));
    const qs = params.toString();
    return qs ? `${basePath}?${qs}` : (basePath ?? "");
  };
  const go = (p: number, s: number = size) => {
    if (onChange) onChange({ page: p, size: s });
    else router.push(href(p, s));
  };

  const cell = "grid size-[30px] place-items-center rounded-[8px] text-[12px]";
  const step = (to: number, disabled: boolean, name: string, icon: React.ReactNode) =>
    disabled ? (
      <span aria-disabled="true" aria-label={name} className={`${cell} opacity-40`}>
        {icon}
      </span>
    ) : onChange ? (
      <button type="button" aria-label={name} onClick={() => go(to)} className={`${cell} hover:bg-[var(--surface-app)]`}>
        {icon}
      </button>
    ) : (
      <Link href={href(to)} aria-label={name} className={`${cell} hover:bg-[var(--surface-app)]`}>
        {icon}
      </Link>
    );

  return (
    <nav aria-label={label} className="flex flex-wrap items-center gap-2 text-[12px]">
      {/* Never narrower than its own words: in a narrow column (the Inbox
          list) the page buttons wrap below rather than "Showin / g 1–25". */}
      <p className="min-w-fit flex-1 whitespace-nowrap text-[var(--text-secondary)]">
        Showing {n(first)}–{n(last)} of {n(total)}
      </p>
      {step(page - 1, page <= 1, "Previous page", <ArrowLeft size={14} />)}
      {pageWindow(page, pages).map((p, i) =>
        p === "gap" ? (
          <span key={`gap-${i}`} aria-hidden="true" className={`${cell} text-[var(--text-secondary)]`}>
            …
          </span>
        ) : p === page ? (
          <span key={p} aria-current="page" className={`${cell} bg-[var(--surface-app)] font-medium`}>
            {p}
          </span>
        ) : onChange ? (
          <button key={p} type="button" aria-label={`Page ${p}`} onClick={() => go(p)} className={`${cell} hover:bg-[var(--surface-app)]`}>
            {p}
          </button>
        ) : (
          <Link key={p} href={href(p)} aria-label={`Page ${p}`} className={`${cell} hover:bg-[var(--surface-app)]`}>
            {p}
          </Link>
        ),
      )}
      {step(page + 1, page >= pages, "Next page", <CaretRight size={14} />)}
      {sizes.length ? (
        <label className="relative flex h-[26px] items-center rounded-[8px] border border-[var(--border-subtle)] bg-[var(--surface-card)]">
          <span className="sr-only">Rows per page</span>
          <select
            value={size}
            onChange={(e) => go(1, Number(e.target.value))}
            className="h-full cursor-pointer appearance-none rounded-[8px] bg-transparent pl-[11px] pr-7 text-[12px] outline-none focus-visible:shadow-[0_0_0_2px_var(--accent-primary)]"
          >
            {sizes.map((s) => (
              <option key={s} value={s}>
                {s} per page
              </option>
            ))}
          </select>
          <CaretDown aria-hidden="true" size={12} className="pointer-events-none absolute right-[11px]" />
        </label>
      ) : null}
    </nav>
  );
}
