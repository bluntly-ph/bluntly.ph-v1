"use client";

import { useRouter } from "next/navigation";
import { useEffect, useId, useRef, useState } from "react";
import { TOP_SEARCH_STATES } from "@/components/ui/search-styles";
import {
  ChatText,
  MagnifyingGlass,
  Package,
  Question,
  Storefront,
  Users,
  X,
} from "@phosphor-icons/react/dist/ssr";

/**
 * The console top bar's search, as a results panel (Figma Search/Admin/Global
 * 8289:29993 and Search/Seller/Global 8289:30079; "No results" 8314:32952 /
 * 8314:33015). Grouped hits arrive from the API as the viewer types (≥ 2
 * characters, debounced); ↑↓ move, Enter opens, Esc closes, "/" focuses.
 *
 * `endpoint` is the BFF path that answers `?q=` with groups: /admin/search for
 * staff, /sellers/{id}/search for a store's owner.
 */

type Hit = { type: string; id: string; title: string; sub?: string | null; href: string; tag: string };
type Group = { key: string; label: string; items: Hit[] };

const ICON: Record<string, typeof ChatText> = {
  review: ChatText,
  product: Package,
  seller: Storefront,
  person: Users,
  question: Question,
};

export function GlobalSearch({
  endpoint,
  placeholder,
  footer,
  emptyHint,
  /** Enter with nothing highlighted (staff: All reviews with the query). */
  submitHref,
}: {
  endpoint: string;
  placeholder: string;
  footer: string;
  emptyHint: string;
  submitHref?: (q: string) => string;
}) {
  const router = useRouter();
  const listId = useId();
  const [q, setQ] = useState("");
  const [groups, setGroups] = useState<Group[] | null>(null);
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(-1);
  const [loading, setLoading] = useState(false);
  const input = useRef<HTMLInputElement>(null);
  const box = useRef<HTMLDivElement>(null);
  const term = q.trim();
  const flat = (groups ?? []).flatMap((g) => g.items);

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      const t = e.target as HTMLElement | null;
      const typing = t && (t.tagName === "INPUT" || t.tagName === "TEXTAREA" || t.tagName === "SELECT" || t.isContentEditable);
      if (e.key === "/" && !typing) {
        e.preventDefault();
        input.current?.focus();
      }
    }
    function onClick(e: MouseEvent) {
      if (box.current && !box.current.contains(e.target as Node)) setOpen(false);
    }
    window.addEventListener("keydown", onKey);
    window.addEventListener("mousedown", onClick);
    return () => {
      window.removeEventListener("keydown", onKey);
      window.removeEventListener("mousedown", onClick);
    };
  }, []);

  useEffect(() => {
    if (term.length < 2) return;
    let cancelled = false;
    const t = setTimeout(() => {
      setLoading(true);
      fetch(`/api/bff${endpoint}?q=${encodeURIComponent(term)}`, { cache: "no-store" })
        .then((r) => (r.ok ? (r.json() as Promise<Group[]>) : Promise.reject(new Error("search"))))
        .then((rows) => {
          if (!cancelled) {
            setGroups(rows);
            setActive(-1);
          }
        })
        .catch(() => {
          if (!cancelled) setGroups([]);
        })
        .finally(() => {
          if (!cancelled) setLoading(false);
        });
    }, 220);
    return () => {
      cancelled = true;
      clearTimeout(t);
    };
  }, [term, endpoint]);

  function go(hit: Hit) {
    setOpen(false);
    router.push(hit.href);
  }

  function onKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === "Escape") {
      setOpen(false);
      input.current?.blur();
      return;
    }
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault();
      setOpen(true);
      if (!flat.length) return;
      setActive((i) => (e.key === "ArrowDown" ? (i + 1) % flat.length : (i <= 0 ? flat.length : i) - 1));
      return;
    }
    if (e.key === "Enter") {
      e.preventDefault();
      if (active >= 0 && flat[active]) go(flat[active]);
      else if (term && submitHref) {
        setOpen(false);
        router.push(submitHref(term));
      } else if (flat[0]) go(flat[0]);
    }
  }

  const showPanel = open && term.length >= 2 && groups !== null;
  // Where each group's rows start in `flat`, so ↑↓ and the hovered row agree.
  const starts = (groups ?? []).reduce<number[]>((acc, g, gi) => [...acc, gi === 0 ? 0 : acc[gi - 1] + groups![gi - 1].items.length], []);

  return (
    <div ref={box} className="relative hidden md:block">
      {/* Admin/TopSearch (8265:27300): grey, 5% darker on hover; focused, white with
          a brand edge and halo and an "Esc" hint; filled, white with its clear. */}
      <div role="search" className={`group flex h-[30px] w-[300px] items-center gap-2 rounded-[10px] py-[7px] pl-[10px] pr-2 lg:w-[300px] ${TOP_SEARCH_STATES}`}>
        <MagnifyingGlass size={16} className="shrink-0 text-[var(--text-secondary)]" aria-hidden />
        <input
          ref={input}
          value={q}
          role="combobox"
          aria-label={placeholder.replace(/…$/, "")}
          aria-expanded={showPanel}
          aria-controls={listId}
          aria-autocomplete="list"
          aria-activedescendant={active >= 0 ? `${listId}-${active}` : undefined}
          onChange={(e) => {
            setQ(e.target.value);
            setOpen(true);
            if (e.target.value.trim().length < 2) setGroups(null);
          }}
          onFocus={() => setOpen(true)}
          onKeyDown={onKeyDown}
          placeholder={placeholder}
          className="min-w-0 flex-1 bg-transparent text-[12px] leading-none caret-[var(--accent-primary)] outline-none placeholder:text-[var(--text-secondary)]"
        />
        {q ? (
          <button
            type="button"
            aria-label="Clear search"
            onClick={() => {
              setQ("");
              setGroups(null);
              input.current?.focus();
            }}
            className="grid size-5 place-items-center rounded-full text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
          >
            <X size={14} />
          </button>
        ) : (
          <>
            <kbd className="rounded-[6px] bg-[var(--surface-card)] px-[6px] py-px font-sans text-[10px] leading-[14px] text-[var(--text-secondary)] group-focus-within:hidden">/</kbd>
            <kbd className="hidden rounded-[6px] bg-[var(--surface-app)] px-[6px] py-px font-sans text-[10px] leading-[14px] text-[var(--text-secondary)] group-focus-within:inline">Esc</kbd>
          </>
        )}
      </div>
      {showPanel ? (
        <div
          id={listId}
          role="listbox"
          aria-label="Search results"
          aria-busy={loading}
          className="absolute right-0 top-[calc(100%+8px)] z-50 w-[420px] max-w-[calc(100vw-32px)] rounded-[16px] border border-[var(--border-subtle)] bg-[var(--surface-card)] shadow-[var(--shadow-modal)]"
        >
          {flat.length === 0 ? (
            <div className="px-5 py-6" data-testid="search-empty">
              <p className="text-[14px] font-medium">No results for “{term}”</p>
              <p className="mt-1 text-[12px] text-[var(--text-secondary)]">{emptyHint}</p>
            </div>
          ) : (
            <div className="max-h-[60dvh] overflow-y-auto py-2">
              {groups!.map((g, gi) => (
                <div key={g.key} role="group" aria-label={g.label} className="pb-1">
                  <p className="px-5 pb-1 pt-2 text-[10px] font-medium uppercase tracking-[0.06em] text-[var(--text-secondary)]">{g.label}</p>
                  {g.items.map((hit, hi) => {
                    const i = starts[gi] + hi;
                    const Icon = ICON[hit.type] ?? ChatText;
                    return (
                      <div
                        key={`${hit.type}-${hit.id}`}
                        id={`${listId}-${i}`}
                        role="option"
                        aria-selected={active === i}
                        data-testid="search-hit"
                        onMouseEnter={() => setActive(i)}
                        onMouseDown={(e) => {
                          e.preventDefault();
                          go(hit);
                        }}
                        className={`mx-2 flex cursor-pointer items-center gap-3 rounded-[12px] px-3 py-2 ${active === i ? "bg-[var(--surface-app)]" : ""}`}
                      >
                        <span aria-hidden className="grid size-8 shrink-0 place-items-center rounded-[8px] bg-[var(--surface-app)]">
                          <Icon size={16} />
                        </span>
                        <span className="flex min-w-0 flex-1 flex-col gap-1 leading-none">
                          <span className="truncate text-[14px]">{hit.title}</span>
                          {hit.sub ? <span className="truncate text-[12px] text-[var(--text-secondary)]">{hit.sub}</span> : null}
                        </span>
                        <span className="shrink-0 text-[11px] text-[var(--text-secondary)]">{hit.tag}</span>
                      </div>
                    );
                  })}
                </div>
              ))}
            </div>
          )}
          <p className="border-t border-[var(--border-subtle)] px-5 py-3 text-[12px] text-[var(--text-secondary)]">{footer}</p>
        </div>
      ) : null}
    </div>
  );
}
