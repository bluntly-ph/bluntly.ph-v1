"use client";

import Image from "next/image";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { MagnifyingGlass, Package, Star, X } from "@phosphor-icons/react/dist/ssr";

import { AdminModal } from "@/components/admin/AdminModal";
import { ConfirmDialog } from "@/components/admin/ConfirmDialog";
import { Chip } from "@/components/console/Chip";
import { ListControls, type FilterGroup } from "@/components/console/ListControls";
import { listHref } from "@/components/console/list-query";
import { Pagination } from "@/components/console/Pagination";
import { CATEGORIES } from "@/lib/landing-data";
import { FIELD_INPUT } from "@/components/console/fields";
import { Callout } from "@/components/console/Callout";

import { agoShort } from "./overview-model";
import { PRODUCT_SORTS, PRODUCT_TABS, applyProducts, changeLabel, inTab, pct, verdictBar, type ProductTab, type Row } from "./products-model";

/**
 * Screen/Seller/Products (Figma 8204:22648; Waiting 8214:23301, All 8214:23647)
 * with Overlay/Store/LinkProduct (8204:23173), Confirm/Store/LinkProduct
 * (8213:23439), Confirm/Store/CancelLink (8213:23484) and
 * Overlay/Store/RequestProduct (8213:23372, Similar 8278:29593).
 *
 * Linking never creates or edits a product page: the owner picks pages from
 * the catalogue, a moderator approves, and approved products bring their
 * figures here. A missing product is a request for a moderator to add it.
 */

type Schemas = import("@/lib/api-types").components["schemas"];
type StoreProducts = Schemas["StoreProductsOut"];
type Option = Schemas["StoreProductOptionOut"];

const CATEGORY_LABEL = Object.fromEntries(CATEGORIES.map((c) => [c.slug, c.label]));
const CATEGORY_OPTIONS = CATEGORIES.filter((c) => c.slug !== "trending");

export function SellerProducts({
  storeId,
  storeName,
  data,
  query,
  now,
  page,
  size,
  openLink = false,
}: {
  storeId: string;
  storeName: string;
  data: StoreProducts | null;
  query: Record<string, string>;
  now: number;
  page: number;
  size: number;
  /** ?link=1 (Quick actions → Link a product) opens the Link window on arrival. */
  openLink?: boolean;
}) {
  const router = useRouter();
  const tab: ProductTab = query.tab === "waiting" || query.tab === "all" ? query.tab : "linked";
  const [linking, setLinking] = useState(openLink);
  const [requesting, setRequesting] = useState<string | null>(null);
  const [cancelling, setCancelling] = useState<Row | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const rows = (data?.rows ?? []) as Row[];
  const shown = applyProducts(rows, tab, query);
  const paged = shown.slice((page - 1) * size, page * size);
  const base = `/seller/${storeId}/products`;
  const counts = { linked: rows.filter((r) => inTab(r, "linked")).length, waiting: rows.filter((r) => inTab(r, "waiting")).length, all: rows.filter((r) => inTab(r, "all")).length };
  const categories = [...new Set(rows.filter((r) => inTab(r, "linked")).map((r) => r.category).filter(Boolean))] as string[];
  const filters: FilterGroup[] = [
    ...(categories.length ? [{ key: "category", title: "Category", options: categories.map((c) => [c, CATEGORY_LABEL[c] ?? c] as [string, string]) }] : []),
    { key: "rating", title: "Rating", options: [["low", "Below 4"], ["high", "4 and up"], ["few", "Not enough reviews"]] },
    { key: "open", title: "Questions", options: [["1", "Has open questions"]] },
  ];

  async function cancel() {
    if (!cancelling) return;
    setBusy(true);
    setError(null);
    const res = await fetch(`/api/bff/api/v1/sellers/${storeId}/products/${cancelling.id}/cancel`, { method: "POST" }).catch(() => null);
    setBusy(false);
    if (res?.ok) {
      setCancelling(null);
      router.refresh();
    } else setError("The request couldn’t be cancelled. Try again.");
  }

  return (
    <div className="flex flex-col gap-4">
      <h1 className="text-[24px] font-semibold leading-none">Products</h1>
      <div className="flex flex-wrap items-center gap-3">
        <nav aria-label="Product views" className="flex w-fit flex-wrap gap-[2px] rounded-[10px] bg-[var(--surface-app)] p-[3px]">
          {PRODUCT_TABS.map((t) => (
            <Link
              key={t.key}
              href={listHref(base, {}, { tab: t.key === "linked" ? "" : t.key })}
              aria-current={tab === t.key ? "page" : undefined}
              className={`flex items-center gap-[6px] rounded-[8px] px-3 py-[5px] leading-none ${
                tab === t.key ? "bg-[var(--surface-card)] shadow-[var(--shadow-segment)]" : "text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
              }`}
            >
              <span className="text-[14px] font-medium">{t.label}</span>
              <span className="text-[12px] text-[var(--text-secondary)]">{counts[t.key]}</span>
            </Link>
          ))}
        </nav>
        <span className="flex-1" />
        <ListControls basePath={base} params={query} sorts={PRODUCT_SORTS} defaultSort="reviews" filters={filters} search={{ placeholder: "Product name", label: "Search products" }} />
        <button type="button" onClick={() => setLinking(true)} className="h-9 rounded-full bg-[var(--accent-primary)] px-4 text-[12px] text-white">
          Link a product
        </button>
      </div>

      {data === null ? (
        <p role="alert" className="rounded-[16px] border border-[var(--border-subtle)] p-6 text-[14px] text-[var(--text-secondary)]">
          Your products couldn’t be loaded. Try again in a moment.
        </p>
      ) : (
        <>
          <section aria-label="Products at a glance" className="grid gap-3 sm:grid-cols-3">
            <Card label="Products linked" value={String(data.linked)} note={data.waiting ? `${data.waiting} waiting for approval` : "None waiting"} />
            <Card label="Reviews across them" value={data.reviews.toLocaleString("en-PH")} note="Product reviews, not store reviews" />
            <Card
              label="Open questions"
              value={String(data.open_questions)}
              note={data.products_with_open_questions ? `Across ${data.products_with_open_questions} product${data.products_with_open_questions === 1 ? "" : "s"}` : "Nothing unanswered"}
            />
          </section>

          <div className="overflow-x-auto rounded-[16px] border border-[var(--border-subtle)]">
            <table className="w-full min-w-[900px] border-collapse text-left text-[14px]">
              <caption className="sr-only">Your store’s products</caption>
              <thead className="bg-[var(--surface-app)] text-[12px] text-[var(--text-secondary)]">
                <tr>
                  {(tab === "waiting" ? ["Product", "Category", "Requested", "Status", "Action"] : ["Product", "Reviews", "Rating", "Verdicts", "Last 30 days", "Questions", "Action"]).map((h) => (
                    <th key={h} scope="col" className="h-10 px-3 font-normal">
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {paged.length === 0 ? (
                  <tr>
                    <td colSpan={7} className="border-t border-[var(--border-subtle)] px-3 py-10 text-center text-[var(--text-secondary)]">
                      {rows.length === 0
                        ? "No products yet. Link the product pages your store sells; a moderator checks each one."
                        : tab === "waiting"
                          ? "Nothing waiting for approval."
                          : "No product matches."}
                    </td>
                  </tr>
                ) : tab === "waiting" ? (
                  paged.map((r) => (
                    <tr key={r.id} data-testid="store-product-row" className="border-t border-[var(--border-subtle)]">
                      <td className="px-3 py-[10px]">
                        <ProductCell name={r.name} image={r.image_url} sub={`${r.figures.reviews} review${r.figures.reviews === 1 ? "" : "s"} on Bluntly`} />
                      </td>
                      <td className="px-3">{CATEGORY_LABEL[r.category ?? ""] ?? "—"}</td>
                      <td className="px-3 text-[var(--text-secondary)]" suppressHydrationWarning>
                        {agoShort(r.requested_at, now)}
                      </td>
                      <td className="px-3">
                        <Chip tone="warning">Waiting for approval</Chip>
                      </td>
                      <td className="px-3">
                        <button type="button" onClick={() => setCancelling(r)} className="h-8 rounded-full border border-[var(--border-subtle)] bg-[var(--surface-card)] px-3 text-[12px] hover:border-[var(--text-secondary)]">
                          Cancel request
                        </button>
                      </td>
                    </tr>
                  ))
                ) : (
                  paged.map((r) => {
                    const f = r.figures;
                    const bar = verdictBar(f);
                    const change = changeLabel(f);
                    const waiting = r.status === "pending";
                    return (
                      <tr key={r.id} data-testid="store-product-row" className="group border-t border-[var(--border-subtle)] hover:bg-[var(--surface-app)]">
                        <td className="px-3 py-[10px]">
                          <ProductCell name={r.name} image={r.image_url} sub={CATEGORY_LABEL[r.category ?? ""] ?? "No category"} />
                        </td>
                        <td className="px-3 [font-variant-numeric:tabular-nums]">{f.reviews}</td>
                        <td className="px-3">
                          {f.median != null && !waiting ? (
                            <span className="flex items-center gap-1 [font-variant-numeric:tabular-nums]">
                              <Star size={14} weight="fill" className="text-[var(--semantic-success-500)]" aria-hidden />
                              {f.median.toFixed(1)}
                            </span>
                          ) : (
                            "—"
                          )}
                        </td>
                        <td className="px-3">
                          {waiting ? (
                            <span className="text-[12px] text-[var(--text-secondary)]">After approval</span>
                          ) : bar ? (
                            <span className="flex flex-col gap-1">
                              <span className="flex h-[6px] w-[150px] gap-[2px] overflow-hidden rounded-full" aria-hidden>
                                <span className="bg-[var(--semantic-success-500)]" style={{ width: `${bar[0]}%` }} />
                                <span className="bg-[var(--accent-star)]" style={{ width: `${bar[1]}%` }} />
                                <span className="bg-[var(--semantic-danger)]" style={{ width: `${bar[2]}%` }} />
                              </span>
                              <span className="text-[12px] text-[var(--text-secondary)]">{pct(f.worth_it)} worth it</span>
                            </span>
                          ) : (
                            <span className="text-[12px] text-[var(--text-secondary)]">Not enough reviews yet</span>
                          )}
                        </td>
                        <td className={`px-3 text-[12px] ${change.tone === "up" ? "text-[var(--semantic-success-500)]" : change.tone === "down" ? "text-[var(--semantic-danger)]" : "text-[var(--text-secondary)]"}`}>
                          {waiting ? "—" : change.text}
                        </td>
                        <td className="px-3">{f.open_questions ? `${f.open_questions} open` : 0}</td>
                        <td className="px-3 py-[6px]">
                          {waiting ? (
                            <Chip tone="warning">Waiting</Chip>
                          ) : (
                            <Link
                              href={`${base}/${r.product_id}`}
                              className="inline-block h-8 rounded-full border border-[var(--border-subtle)] bg-[var(--surface-card)] px-3 text-[12px] leading-8 opacity-0 hover:border-[var(--text-secondary)] focus:opacity-100 group-hover:opacity-100 max-md:opacity-100"
                            >
                              Analytics
                            </Link>
                          )}
                        </td>
                      </tr>
                    );
                  })
                )}
              </tbody>
            </table>
          </div>
          <Pagination page={page} size={size} total={shown.length} basePath={base} query={query} label="Product pages" />
        </>
      )}

      {linking ? (
        <LinkModal
          storeId={storeId}
          storeName={storeName}
          onClose={() => {
            setLinking(false);
            // Drop ?link=1 so a refresh doesn't open it again (other filters stay).
            if (openLink) router.replace(listHref(base, query), { scroll: false });
          }}
          onRequest={(name) => {
            setLinking(false);
            setRequesting(name);
          }}
        />
      ) : null}
      {requesting !== null ? (
        <RequestProductModal
          storeId={storeId}
          initialName={requesting}
          onClose={() => setRequesting(null)}
          onLink={() => {
            setRequesting(null);
            setLinking(true);
          }}
        />
      ) : null}
      <ConfirmDialog
        open={cancelling !== null}
        title="Cancel this request?"
        confirmLabel="Cancel request"
        busyLabel="Cancelling…"
        busy={busy}
        error={error}
        onConfirm={() => void cancel()}
        onClose={() => setCancelling(null)}
      >
        <p>{cancelling?.name} won’t be linked. You can ask again later.</p>
      </ConfirmDialog>
    </div>
  );
}

function Card({ label, value, note }: { label: string; value: string; note: string }) {
  return (
    <div className="flex flex-col gap-2 rounded-[16px] border border-[var(--border-subtle)] p-5">
      <span className="text-[12px] text-[var(--text-secondary)]">{label}</span>
      <span className="text-[24px] font-semibold leading-none [font-variant-numeric:tabular-nums]">{value}</span>
      <span className="text-[12px] text-[var(--text-secondary)]">{note}</span>
    </div>
  );
}

function ProductCell({ name, sub, image }: { name: string; sub: string; image?: string | null }) {
  return (
    <span className="flex items-center gap-3">
      {image ? (
        <Image src={image} alt="" width={40} height={40} unoptimized className="size-10 shrink-0 rounded-[8px] object-cover" />
      ) : (
        <span aria-hidden className="grid size-10 shrink-0 place-items-center rounded-[8px] bg-[var(--surface-app)]">
          <Package size={18} />
        </span>
      )}
      <span className="flex min-w-0 flex-col gap-1 leading-none">
        <span className="truncate font-medium">{name}</span>
        <span className="truncate text-[12px] text-[var(--text-secondary)]">{sub}</span>
      </span>
    </span>
  );
}

function useCatalogue(storeId: string, q: string) {
  const [results, setResults] = useState<Option[] | null>(null);
  useEffect(() => {
    const term = q.trim();
    if (term.length < 2) return;
    let cancelled = false;
    const t = setTimeout(() => {
      fetch(`/api/bff/api/v1/sellers/${storeId}/products/options?q=${encodeURIComponent(term)}`, { cache: "no-store" })
        .then((r) => (r.ok ? (r.json() as Promise<Option[]>) : Promise.reject(new Error("options"))))
        .then((rows) => !cancelled && setResults(rows))
        .catch(() => !cancelled && setResults([]));
    }, 220);
    return () => {
      cancelled = true;
      clearTimeout(t);
    };
  }, [q, storeId]);
  return q.trim().length >= 2 ? results : null;
}

/** Overlay/Store/LinkProduct + Confirm/Store/LinkProduct. */
function LinkModal({ storeId, storeName, onClose, onRequest }: { storeId: string; storeName: string; onClose: () => void; onRequest: (name: string) => void }) {
  const router = useRouter();
  const [q, setQ] = useState("");
  const results = useCatalogue(storeId, q);
  const [sent, setSent] = useState<Record<string, true>>({});
  const [confirm, setConfirm] = useState<Option | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function send() {
    if (!confirm) return;
    setBusy(true);
    setError(null);
    try {
      const res = await fetch(`/api/bff/api/v1/sellers/${storeId}/products`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ product_id: confirm.product_id }),
      });
      if (!res.ok) {
        const p = (await res.json().catch(() => ({}))) as { detail?: unknown };
        setError(typeof p.detail === "string" ? p.detail : "The link couldn’t be sent.");
        return;
      }
      setSent((m) => ({ ...m, [confirm.product_id]: true }));
      setConfirm(null);
      router.refresh();
    } catch {
      setError("Couldn’t reach the server.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <AdminModal title="Link a product" width={560} onClose={onClose}>
        <div className="flex flex-col gap-4 overflow-y-auto px-6 pb-5 pt-2">
          <p className="text-[14px] text-[var(--text-secondary)]">Pick products on Bluntly that your store sells. You can’t create or edit product pages.</p>
          {/* Admin/Input Type=Search states (8265:27121–27174). */}
          <div className="flex items-center gap-2 rounded-[12px] border border-[var(--line-hairline-30)] px-3 hover:border-[var(--border-input-hover)] focus-within:border-[var(--accent-primary)] focus-within:shadow-[var(--ring-field-focus)] focus-within:hover:border-[var(--accent-primary)]">
            <MagnifyingGlass size={16} aria-hidden className="text-[var(--text-secondary)]" />
            <input autoFocus value={q} onChange={(e) => setQ(e.target.value)} aria-label="Search the catalogue" placeholder="Product name" className="h-11 flex-1 bg-transparent text-[14px] caret-[var(--accent-primary)] outline-none" />
            {q ? (
              <button type="button" aria-label="Clear" onClick={() => setQ("")}>
                <X size={16} />
              </button>
            ) : null}
          </div>
          {results ? (
            <div>
              <p className="pb-2 text-[11px] font-medium uppercase tracking-[0.06em] text-[var(--text-secondary)]">
                {results.length} result{results.length === 1 ? "" : "s"}
              </p>
              <ul className="flex flex-col">
                {results.map((o) => {
                  const state = sent[o.product_id] ? "pending" : o.state;
                  return (
                    <li key={o.product_id} data-testid="link-option" className="flex items-center gap-3 border-t border-[var(--border-subtle)] py-3">
                      <ProductCell name={o.name} sub={`${CATEGORY_LABEL[o.category ?? ""] ?? "No category"} · ${o.review_count ? `${o.review_count} review${o.review_count === 1 ? "" : "s"}` : "No reviews yet"}`} />
                      <span className="flex-1" />
                      {state === "pending" ? (
                        <Chip tone="warning">Waiting for approval</Chip>
                      ) : state === "linked" ? (
                        <Chip tone="success">Linked</Chip>
                      ) : (
                        <button type="button" onClick={() => setConfirm(o)} className="h-8 rounded-full border border-[var(--border-subtle)] px-3 text-[12px] hover:border-[var(--text-secondary)]">
                          Link
                        </button>
                      )}
                    </li>
                  );
                })}
              </ul>
              {results.length === 0 ? <p className="py-4 text-[14px] text-[var(--text-secondary)]">Nothing on Bluntly matches. Ask for a product page.</p> : null}
            </div>
          ) : null}
          <Callout>
            A moderator checks each link. Once approved, the product shows as sold by {storeName} and its analytics appear here.
          </Callout>
        </div>
        <div className="flex items-center gap-3 border-t border-[var(--border-subtle)] px-6 py-4">
          <button type="button" onClick={() => onRequest(q.trim())} className="text-[12px] text-[var(--accent-primary)] hover:underline">
            Ask for a product page
          </button>
          <span className="flex-1" />
          <button type="button" onClick={onClose} className="h-9 rounded-full border border-[var(--text-primary)] px-4 text-[12px]">
            Cancel
          </button>
          <button type="button" onClick={onClose} className="h-9 rounded-full bg-[var(--accent-primary)] px-4 text-[12px] text-white">
            Done
          </button>
        </div>
      </AdminModal>
      <ConfirmDialog
        open={confirm !== null}
        title={`Link ${confirm?.name ?? "this product"}?`}
        confirmLabel="Send for approval"
        busyLabel="Sending…"
        busy={busy}
        error={error}
        onConfirm={() => void send()}
        onClose={() => setConfirm(null)}
      >
        <p>A moderator checks that your store sells it.</p>
        <p>Once approved, it shows as sold by {storeName}, and its analytics appear under Products.</p>
      </ConfirmDialog>
    </>
  );
}

/** Overlay/Store/RequestProduct (8213:23372) and its Similar state (8278:29593). */
function RequestProductModal({ storeId, initialName, onClose, onLink }: { storeId: string; initialName: string; onClose: () => void; onLink: () => void }) {
  const [name, setName] = useState(initialName);
  const [brand, setBrand] = useState("");
  const [noBrand, setNoBrand] = useState(false);
  const [category, setCategory] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<string | null>(null);
  const similar = useCatalogue(storeId, name);
  const fullName = (() => {
    const n = name.trim();
    const b = noBrand ? "" : brand.trim();
    return b && !n.toLowerCase().startsWith(b.toLowerCase()) ? `${b} ${n}` : n;
  })();
  const ready = name.trim().length >= 2 && !!category && !busy;

  async function send() {
    setBusy(true);
    setError(null);
    try {
      const res = await fetch("/api/bff/api/v1/products", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ name: fullName, category }),
      });
      const p = (await res.json().catch(() => ({}))) as { detail?: unknown; status?: string; canonical_name?: string };
      if (!res.ok) {
        setError(typeof p.detail === "string" ? p.detail : "The request couldn’t be sent.");
        return;
      }
      setDone(
        res.status === 200 && p.status === "canonicalized"
          ? `${p.canonical_name ?? "It"} is already on Bluntly. Link it from Products.`
          : "Sent. A moderator adds the page if it’s a real product; then link it from Products.",
      );
    } catch {
      setError("Couldn’t reach the server.");
    } finally {
      setBusy(false);
    }
  }

  const LABEL = "mb-1.5 block text-[11px] font-medium uppercase tracking-[0.06em] text-[var(--text-secondary)]";
  const FIELD = FIELD_INPUT;
  return (
    <AdminModal title="Ask for a product page" width={560} onClose={onClose}>
      <div className="flex flex-col gap-4 overflow-y-auto px-6 pb-5 pt-2">
        <p className="text-[14px] text-[var(--text-secondary)]">Bluntly creates product pages, not stores. Tell us what’s missing and a moderator adds it if it’s a real product.</p>
        {done ? (
          <p role="status" className="rounded-[12px] bg-[var(--surface-app)] p-3 text-[14px]">
            {done}
          </p>
        ) : (
          <>
            <div>
              <label htmlFor="req-name" className={LABEL}>
                Product name
              </label>
              <input id="req-name" className={FIELD} value={name} maxLength={200} onChange={(e) => setName(e.target.value)} placeholder="e.g. Jisulife Neck Fan Pro2" />
              <p className="mt-1 text-[12px] text-[var(--text-secondary)]">Write it the way buyers search for it. If it has no brand, just the product.</p>
            </div>
            {similar && similar.length > 0 ? (
              <div className="flex flex-col gap-2 rounded-[12px] bg-[var(--surface-app)] p-3" data-testid="request-similar">
                <p className="text-[12px] font-medium">These are already on Bluntly. If one is yours, link it instead.</p>
                {similar.slice(0, 3).map((o) => (
                  <div key={o.product_id} className="flex items-center gap-3">
                    <ProductCell name={o.name} sub={`${CATEGORY_LABEL[o.category ?? ""] ?? "No category"} · ${o.review_count} review${o.review_count === 1 ? "" : "s"}`} />
                    <span className="flex-1" />
                    <button type="button" onClick={onLink} className="shrink-0 text-[12px] text-[var(--chart-honesty-fund)] hover:underline">
                      Link this
                    </button>
                  </div>
                ))}
              </div>
            ) : null}
            <div>
              <label htmlFor="req-brand" className={LABEL}>
                Brand · optional
              </label>
              <input id="req-brand" className={FIELD} value={noBrand ? "" : brand} disabled={noBrand} placeholder={noBrand ? "No brand" : "e.g. Jisulife"} onChange={(e) => setBrand(e.target.value)} />
              <label className="mt-2 flex items-center gap-2 text-[14px]">
                <input type="checkbox" checked={noBrand} onChange={(e) => setNoBrand(e.target.checked)} className="size-4 accent-[var(--accent-primary)]" />
                It has no brand
              </label>
            </div>
            <div>
              <label htmlFor="req-cat" className={LABEL}>
                Category
              </label>
              <select id="req-cat" className={FIELD} value={category} onChange={(e) => setCategory(e.target.value)}>
                <option value="">Choose a category</option>
                {CATEGORY_OPTIONS.map((c) => (
                  <option key={c.slug} value={c.slug}>
                    {c.label}
                  </option>
                ))}
              </select>
            </div>
            <p className="text-[12px] text-[var(--text-secondary)]">No links. Once the page exists, link it from Products.</p>
            {error ? (
              <p role="alert" className="text-[12px] text-[var(--accent-danger)]">
                {error}
              </p>
            ) : null}
          </>
        )}
      </div>
      <div className="flex items-center justify-end gap-3 border-t border-[var(--border-subtle)] px-6 py-4">
        <button type="button" onClick={onClose} className="h-9 rounded-full border border-[var(--text-primary)] px-4 text-[12px]">
          {done ? "Close" : "Cancel"}
        </button>
        {done ? null : (
          <button type="button" disabled={!ready} onClick={() => void send()} className="h-9 rounded-full bg-[var(--accent-primary)] px-4 text-[12px] text-white disabled:opacity-50">
            {busy ? "Sending…" : "Send request"}
          </button>
        )}
      </div>
    </AdminModal>
  );
}
