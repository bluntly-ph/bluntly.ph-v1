"use client";

import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useState } from "react";
import { ArrowsDownUp, MagnifyingGlass, Plus, SlidersHorizontal, UploadSimple } from "@phosphor-icons/react/dist/ssr";

import { PersonCell, shortAge } from "@/components/admin/queue/QueueCells";
import { ProductEditModal, type EditTarget } from "@/components/admin/products/ProductEditModal";
import { ProductImportModal } from "@/components/admin/products/ProductImportModal";
import { Pagination } from "@/components/console/Pagination";
import { PAGE_SIZES } from "@/components/console/pagination-model";
import { ProductThumbnail } from "@/components/console/ProductThumbnail";
import { CATEGORIES } from "@/lib/landing-data";
import type { CatalogueResult, ProductQueueResult } from "@/lib/moderation";
import { DROPDOWN_PILL_STATES } from "@/components/ui/search-styles";

/**
 * Admin Products, built to Figma Screen/Admin/Products/Queue (7966:11087) and
 * Catalogue (7967:11173): the Queue / Catalogue tabs with their counts, sort /
 * filter / search, the table, Edit on the row, and the pagination row. Edit
 * opens Overlay/Product/Edit or, on a submission, Overlay/Product/Catalogue
 * ("Add to catalogue", with Merge into) — ProductEditModal.
 *
 * Everything is real: GET /admin/products/catalogue (aliases, the approved
 * price trend, counts) and GET /admin/products/queue (submitter, link preview).
 * The URL carries the tab, search, category, sort and page, so a view can be
 * reloaded and shared.
 */

const CATEGORY_LABEL = Object.fromEntries(CATEGORIES.map((c) => [c.slug, c.label]));
const SIZES = PAGE_SIZES;
const peso = (v: string | number) => `₱${Number(v).toLocaleString("en-PH", { maximumFractionDigits: 0 })}`;

function Sparkline({ values }: { values: (string | number)[] }) {
  const v = values.map(Number);
  if (v.length < 2) return <span aria-hidden className="inline-block w-16" />;
  const min = Math.min(...v);
  const max = Math.max(...v);
  const span = max - min || 1;
  const pts = v.map((x, i) => `${((i / (v.length - 1)) * 64).toFixed(1)},${(18 - ((x - min) / span) * 16).toFixed(1)}`).join(" ");
  return (
    <svg width={64} height={20} viewBox="0 0 64 20" aria-hidden className="shrink-0">
      <polyline points={pts} fill="none" stroke="var(--text-primary)" strokeWidth={1.25} strokeLinejoin="round" />
    </svg>
  );
}

export function ProductsScreen({
  tab,
  catalogue,
  queue,
  page,
  size,
  now,
}: {
  tab: "queue" | "catalogue";
  catalogue: CatalogueResult | null;
  queue: ProductQueueResult | null;
  page: number;
  size: number;
  now: number;
}) {
  const router = useRouter();
  const pathname = usePathname() ?? "/admin/products";
  const params = useSearchParams();
  const [editing, setEditing] = useState<EditTarget | null>(null);
  const [importing, setImporting] = useState(false);
  const [panel, setPanel] = useState<"sort" | "filter" | "search" | null>(params.get("q") ? "search" : null);
  const [q, setQ] = useState(params.get("q") ?? "");

  function go(changes: Record<string, string | null>) {
    const next = new URLSearchParams(params.toString());
    for (const [k, v] of Object.entries(changes)) {
      if (v === null || v === "") next.delete(k);
      else next.set(k, v);
    }
    if (!("page" in changes)) next.delete("page");
    router.push(`${pathname}?${next.toString()}`, { scroll: false });
  }

  const total = tab === "catalogue" ? (catalogue?.total ?? 0) : (queue?.total ?? 0);
  const queueRows = (queue?.items ?? []).slice((page - 1) * size, page * size);
  const counts = { queue: catalogue?.queue_count ?? queue?.total ?? null, catalogue: catalogue?.catalogue_count ?? null };
  const sort = params.get("sort") ?? (tab === "catalogue" ? "reviews" : "oldest");
  const sorts = tab === "catalogue" ? [["reviews", "Most reviews"], ["name", "Name"], ["newest", "Newest"]] : [["oldest", "Oldest first"], ["newest", "Newest first"]];

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center gap-2">
        <nav aria-label="Products views" className="flex gap-[2px] rounded-[10px] bg-[var(--surface-app)] p-[3px]">
          {(["queue", "catalogue"] as const).map((t) => (
            <Link
              key={t}
              href={t === "queue" ? "/admin/products" : "/admin/products?tab=catalogue"}
              aria-current={tab === t ? "page" : undefined}
              className={`flex items-center gap-[6px] rounded-[8px] px-3 py-[5px] leading-none ${tab === t ? "bg-[var(--surface-card)] shadow-[var(--shadow-segment)]" : "text-[var(--text-secondary)] hover:text-[var(--text-primary)]"}`}
            >
              <span className="text-[14px] font-medium">{t === "queue" ? "Queue" : "Catalogue"}</span>
              {counts[t] !== null ? <span className="text-[12px] text-[var(--text-secondary)]">{counts[t]}</span> : null}
            </Link>
          ))}
        </nav>
        <span className="flex-1" />
        {[
          ["sort", ArrowsDownUp, "Sort"],
          ...(tab === "catalogue" ? [["filter", SlidersHorizontal, "Filter by category"], ["search", MagnifyingGlass, "Search the catalogue"]] : []),
        ].map(([key, Icon, label]) => {
          const I = Icon as typeof ArrowsDownUp;
          return (
            <button
              key={key as string}
              type="button"
              aria-label={label as string}
              aria-expanded={panel === key}
              onClick={() => setPanel((p) => (p === key ? null : (key as typeof panel)))}
              className={`grid size-8 place-items-center rounded-full ${panel === key ? "bg-[var(--surface-app)]" : "hover:bg-[var(--surface-app)]"}`}
            >
              <I size={18} />
            </button>
          );
        })}
        {/* Owner request 2026-10-03 (no frame): Import and Add product, in the
            console's action-pill language (Reports' "Generate report"). */}
        <button
          type="button"
          onClick={() => setImporting(true)}
          className="ml-1 flex h-8 items-center gap-1.5 rounded-full border border-[var(--text-primary)] px-3 text-[12px]"
        >
          <UploadSimple size={14} aria-hidden /> Import
        </button>
        <button
          type="button"
          onClick={() => setEditing({ id: "", mode: "create", name: "", aliases: [] })}
          className="flex h-8 items-center gap-1.5 rounded-full bg-[var(--accent-primary)] px-3 text-[12px] text-white"
        >
          <Plus size={14} aria-hidden /> Add product
        </button>
      </div>

      {panel === "sort" ? (
        <div className="flex flex-wrap gap-2" role="group" aria-label="Sort">
          {sorts.map(([k, label]) => (
            <button key={k} type="button" aria-pressed={sort === k} onClick={() => go({ sort: k })} className={`h-8 rounded-full border px-3 text-[12px] ${sort === k ? "border-[var(--accent-primary)] text-[var(--accent-primary)]" : "border-[var(--border-subtle)]"}`}>
              {label}
            </button>
          ))}
        </div>
      ) : panel === "filter" ? (
        <label className="flex items-center gap-2 text-[12px]">
          Category
          <select value={params.get("category") ?? ""} onChange={(e) => go({ category: e.target.value || null })} className={`h-8 rounded-full px-3 ${DROPDOWN_PILL_STATES}`}>
            <option value="">All categories</option>
            {CATEGORIES.filter((c) => c.slug !== "trending").map((c) => (
              <option key={c.slug} value={c.slug}>
                {c.label}
              </option>
            ))}
          </select>
        </label>
      ) : panel === "search" ? (
        <form
          role="search"
          onSubmit={(e) => {
            e.preventDefault();
            go({ q: q.trim() || null });
          }}
          className="flex items-center gap-2"
        >
          <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Name or alias" aria-label="Search the catalogue" className="h-8 w-72 rounded-full border border-[var(--border-subtle)] px-3 text-[12px]" />
          <button type="submit" className="h-8 rounded-full border border-[var(--text-primary)] px-3 text-[12px]">
            Search
          </button>
        </form>
      ) : null}

      <div className="overflow-x-auto rounded-[16px] border border-[var(--border-subtle)]">
        <table className="w-full min-w-[900px] border-collapse text-left text-[14px]">
          <caption className="sr-only">{tab === "queue" ? "Submitted products" : "Catalogue"}</caption>
          <thead className="bg-[var(--surface-app)] text-[12px] text-[var(--text-secondary)]">
            <tr>
              {(tab === "queue" ? ["Submitted product", "Marketplace", "Submitted by", "Reviews", "Submitted", "Action"] : ["Product", "Category", "Reviews", "Price trend", "Action"]).map((h) => (
                <th key={h} scope="col" className="h-10 px-3 font-normal">
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {tab === "catalogue" ? (
              catalogue === null ? (
                <tr><td colSpan={5} className="border-t border-[var(--border-subtle)] px-3 py-10 text-center text-[var(--text-secondary)]">The catalogue could not be loaded.</td></tr>
              ) : catalogue.items.length === 0 ? (
                <tr><td colSpan={5} className="border-t border-[var(--border-subtle)] px-3 py-10 text-center text-[var(--text-secondary)]">{params.get("q") || params.get("category") ? "No product matches." : "The catalogue is empty. Approve a submission or use Add product."}</td></tr>
              ) : (
                catalogue.items.map((p) => (
                  <tr key={p.id} data-testid="catalogue-row" className="group border-t border-[var(--border-subtle)] hover:bg-[var(--surface-app)]">
                    <td className="px-3 py-[10px]">
                      <span className="flex items-center gap-[10px]">
                        <ProductThumbnail url={p.image_url} />
                        <span className="flex min-w-0 flex-col gap-1 leading-none">
                          <span className="truncate">{p.name}</span>
                          {p.aliases.length ? <span className="truncate text-[12px] text-[var(--text-secondary)]">Also: {p.aliases.join(", ")}</span> : null}
                        </span>
                      </span>
                    </td>
                    <td className="px-3">{p.category ? (CATEGORY_LABEL[p.category] ?? p.category) : "—"}</td>
                    <td className="px-3 [font-variant-numeric:tabular-nums]">{p.review_count}</td>
                    <td className="px-3">
                      {p.latest_price ? (
                        <span className="flex items-center gap-3">
                          <Sparkline values={p.price_trend} />
                          {peso(p.latest_price)}
                        </span>
                      ) : (
                        <span className="text-[var(--text-secondary)]" title="No approved community price yet">—</span>
                      )}
                    </td>
                    <td className="px-3">
                      <button
                        type="button"
                        onClick={() => setEditing({ id: p.id, mode: "edit", name: p.name, aliases: p.aliases })}
                        aria-label={`Edit ${p.name}`}
                        className="h-7 rounded-full border border-[var(--border-subtle)] bg-[var(--surface-card)] px-3 text-[12px] hover:border-[var(--text-secondary)]"
                      >
                        Edit
                      </button>
                    </td>
                  </tr>
                ))
              )
            ) : queue === null ? (
              <tr><td colSpan={6} className="border-t border-[var(--border-subtle)] px-3 py-10 text-center text-[var(--text-secondary)]">The queue could not be loaded.</td></tr>
            ) : queueRows.length === 0 ? (
              <tr><td colSpan={6} className="border-t border-[var(--border-subtle)] px-3 py-10 text-center text-[var(--text-secondary)]">No submission is waiting.</td></tr>
            ) : (
              queueRows.map((p) => (
                <tr key={p.id} data-testid="queue-row" className="group border-t border-[var(--border-subtle)] hover:bg-[var(--surface-app)]">
                  <td className="px-3 py-[10px]">
                    <span className="flex items-center gap-[10px]">
                      <ProductThumbnail url={p.image_url} />
                      <span className="flex min-w-0 max-w-[340px] flex-col gap-1 leading-none">
                        <span className="truncate">{p.name ?? "Unnamed submission"}</span>
                        {p.link ? (
                          <a
                            href={p.link.url}
                            target="_blank"
                            rel="noreferrer nofollow"
                            title={p.link.https ? p.link.url : `Not https: ${p.link.url}`}
                            className={`truncate text-[12px] ${p.link.marketplace ? "text-[var(--chart-honesty-fund)]" : "text-[var(--accent-danger)]"}`}
                          >
                            {p.link.url.replace(/^https?:\/\//, "")}
                          </a>
                        ) : null}
                      </span>
                    </span>
                  </td>
                  <td className="px-3">{p.link?.marketplace ? p.link.marketplace[0].toUpperCase() + p.link.marketplace.slice(1) : p.link?.host ? <span title="Not a marketplace Bluntly links to">{p.link.host}</span> : "—"}</td>
                  <td className="px-3">
                    {p.submitted_by_name ? (
                      <PersonCell name={p.submitted_by_name} stage={p.submitter_trust_stage ?? undefined} levelName={p.submitter_level_name} href={p.submitted_by_id ? `/admin/people/${p.submitted_by_id}` : undefined} />
                    ) : (
                      "—"
                    )}
                  </td>
                  <td className="px-3">{p.review_count}</td>
                  <td className="px-3 text-[var(--text-secondary)]" suppressHydrationWarning>
                    {shortAge(p.submitted_at, now)}
                  </td>
                  <td className="px-3">
                    <button
                      type="button"
                      onClick={() => setEditing({ id: p.id, mode: "admit", name: p.name ?? "Unnamed submission", aliases: [], link: p.link?.url ?? null })}
                      aria-label={`Edit ${p.name ?? "unnamed submission"}`}
                      className="h-7 rounded-full border border-[var(--border-subtle)] bg-[var(--surface-card)] px-3 text-[12px] hover:border-[var(--text-secondary)]"
                    >
                      Edit
                    </button>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      <Pagination page={page} size={size} total={total} sizes={SIZES} basePath={pathname} query={Object.fromEntries(params.entries())} label="Product pages" />

      {editing ? (
        <ProductEditModal
          key={`${editing.mode}:${editing.id}`}
          target={editing}
          onClose={() => setEditing(null)}
          onOpen={setEditing}
        />
      ) : null}
      {importing ? <ProductImportModal onClose={() => setImporting(false)} /> : null}
    </div>
  );
}
