"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { ArrowsDownUp, Check, MagnifyingGlass, SlidersHorizontal } from "@phosphor-icons/react/dist/ssr";

import { ICON_BUTTON, MENU, usePopover } from "@/components/console/popover";

import { listHref, type FilterGroup } from "./list-query";
import { SEARCH_INPUT, TOOLBAR_SEARCH_STATES } from "@/components/ui/search-styles";
import { MENU_ITEM } from "@/components/console/fields";

/**
 * A console list's Sort / Filter / Search popovers (Figma Menu/<Screen>/Sort,
 * Menu/<Screen>/Filter, Search/<Screen>), driven by the URL so a filtered list
 * can be shared and survives a reload. Every change resets ?page.
 *
 * `params` is the screen's current query (tab or view included); `keys` names
 * the ones this control owns, so "Clear all" clears only its own filters.
 */

export type { FilterGroup } from "./list-query";

export function ListControls({
  basePath,
  params,
  sorts,
  defaultSort,
  filters = [],
  search,
}: {
  basePath: string;
  params: Record<string, string>;
  sorts: [string, string][];
  defaultSort: string;
  filters?: FilterGroup[];
  search?: { placeholder: string; label: string };
}) {
  const router = useRouter();
  const { open: sortOpen, setOpen: setSortOpen, ref: sortRef } = usePopover();
  const { open: filterOpen, setOpen: setFilterOpen, ref: filterRef } = usePopover();
  const { open: searchOpen, setOpen: setSearchOpen, ref: searchRef } = usePopover();
  const [q, setQ] = useState(params.q ?? "");
  const sort = params.sort || defaultSort;
  const active = filters.filter((f) => params[f.key]).length;
  const href = (patch: Record<string, string>) => listHref(basePath, params, { page: "", ...patch });
  const chip = (on: boolean) =>
    `rounded-full border px-3 py-[6px] text-[12px] ${on ? "border-[var(--text-primary)] bg-[var(--text-primary)] text-[var(--surface-card)]" : "border-[var(--border-subtle)] hover:border-[var(--text-secondary)]"}`;

  return (
    <div className="flex items-center gap-1">
      <div ref={sortRef} className="relative">
        <button type="button" onClick={() => setSortOpen(!sortOpen)} aria-expanded={sortOpen} aria-label="Sort" className={ICON_BUTTON}>
          <ArrowsDownUp size={18} />
        </button>
        {sortOpen ? (
          <ul className={`${MENU} w-[220px] p-2`} role="menu" aria-label="Sort">
            {sorts.map(([key, label]) => (
              <li key={key} role="none">
                <Link
                  role="menuitemradio"
                  aria-checked={sort === key}
                  href={href({ sort: key === defaultSort ? "" : key })}
                  scroll={false}
                  onClick={() => setSortOpen(false)}
                  className={MENU_ITEM}
                >
                  {label}
                  {sort === key ? <Check size={16} aria-hidden /> : null}
                </Link>
              </li>
            ))}
          </ul>
        ) : null}
      </div>
      {filters.length ? (
        <div ref={filterRef} className="relative">
          <button
            type="button"
            onClick={() => setFilterOpen(!filterOpen)}
            aria-expanded={filterOpen}
            aria-label={active ? `Filters, ${active} on` : "Filters"}
            className={ICON_BUTTON}
          >
            <SlidersHorizontal size={18} />
            {active ? <span aria-hidden className="absolute right-1 top-1 size-[6px] rounded-full bg-[var(--accent-primary)]" /> : null}
          </button>
          {filterOpen ? (
            <div role="group" aria-label="Filters" className={`${MENU} flex w-[340px] flex-col gap-4 p-4`}>
              {filters.map((f) => (
                <div key={f.key} className="flex flex-col gap-2">
                  <p className="text-[12px] text-[var(--text-secondary)]">{f.title}</p>
                  <div className="flex flex-wrap gap-2">
                    {f.options.map(([value, label, count]) => {
                      const on = params[f.key] === value;
                      return (
                        <Link key={value} href={href({ [f.key]: on ? "" : value })} scroll={false} aria-pressed={on} className={chip(on)}>
                          {label}
                          {count !== undefined ? <span className={`ml-1.5 [font-variant-numeric:tabular-nums] ${on ? "opacity-70" : "text-[var(--text-secondary)]"}`}>{count}</span> : null}
                        </Link>
                      );
                    })}
                  </div>
                </div>
              ))}
              <Link
                href={href(Object.fromEntries(filters.map((f) => [f.key, ""])))}
                scroll={false}
                onClick={() => setFilterOpen(false)}
                className="self-start border-t border-[var(--border-subtle)] pt-3 text-[14px] text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
              >
                Clear all
              </Link>
            </div>
          ) : null}
        </div>
      ) : null}
      {search ? (
        <div ref={searchRef} className="relative">
          <button type="button" onClick={() => setSearchOpen(!searchOpen)} aria-expanded={searchOpen} aria-label={search.label} className={ICON_BUTTON}>
            <MagnifyingGlass size={18} />
            {params.q ? <span aria-hidden className="absolute right-1 top-1 size-[6px] rounded-full bg-[var(--accent-primary)]" /> : null}
          </button>
          {searchOpen ? (
            <form
              role="search"
              onSubmit={(e) => {
                e.preventDefault();
                setSearchOpen(false);
                router.push(href({ q: q.trim() }), { scroll: false });
              }}
              className={`${MENU} flex w-[360px] items-center gap-2 p-2`}
            >
              {/* Admin/ToolbarSearch (8270:28869): the pill carries Default / Hover / Focus / Filled. */}
              <span className={`flex h-9 min-w-0 flex-1 items-center gap-2 rounded-[32px] pl-[14px] pr-3 ${TOOLBAR_SEARCH_STATES}`}>
                <MagnifyingGlass size={16} aria-hidden className="shrink-0 text-[var(--text-secondary)]" />
                <input autoFocus value={q} onChange={(e) => setQ(e.target.value)} placeholder={search.placeholder} aria-label={search.label} className={`${SEARCH_INPUT} h-8 text-[14px] placeholder:text-[var(--text-secondary)]`} />
              </span>
              {params.q ? (
                <Link href={href({ q: "" })} scroll={false} onClick={() => setQ("")} className="text-[12px] text-[var(--text-secondary)] hover:text-[var(--text-primary)]">
                  Clear
                </Link>
              ) : null}
            </form>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
