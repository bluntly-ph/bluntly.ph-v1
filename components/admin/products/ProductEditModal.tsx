"use client";

import Image from "next/image";
import { useRouter } from "next/navigation";
import { useEffect, useId, useRef, useState } from "react";
import { Package, Plus, X } from "@phosphor-icons/react/dist/ssr";

import { AdminModal } from "@/components/admin/AdminModal";
import { ConfirmDialog } from "@/components/admin/ConfirmDialog";
import { Switch } from "@/components/console/Switch";
import { Bar, Block, Pill, SkeletonRegion } from "@/components/ui/Skeleton";
import {
  PART_KINDS,
  PART_LABEL,
  asIsBlocker,
  asIsPayload,
  blocker,
  partsFrom,
  partsPayload,
  savesAs,
  specsPayload,
  startsAsIs,
  type NamePart,
  type PartKind,
  type SpecRow,
} from "@/components/admin/products/product-edit-model";
import { CATEGORIES } from "@/lib/landing-data";
import { prepareImageForUpload, usablePhoto } from "@/lib/image";
import { FIELD_STATES } from "@/components/console/fields";

/**
 * Overlay/Product/Edit (7970:11204) and Overlay/Product/Catalogue (7970:11467),
 * one component: Edit names a catalogue product; "Add to catalogue" admits a
 * submission from the Queue, either by naming it or by merging it into a
 * product already in the catalogue ("Merge into").
 *
 * Every control saves through the existing product endpoints: canonicalize
 * (brand, the name parts, category, specs with "In name"), aliases (add, and
 * remove — audited), image, and attach (the merge). "Saves as" is the name the
 * API will compose, from the same rule.
 *
 * "Add product" (mode `create`, owner request 2026-10-03; no frame, so it is
 * this same form): the naming plus the listing link, kept in the form until
 * POST /admin/products adds it in one go. A product already in the catalogue
 * is refused (409 product_exists) and offered for editing instead. Once added,
 * the modal reopens on it in Edit, where its photo can be uploaded.
 */

const CATEGORY_OPTIONS = CATEGORIES.filter((c) => c.slug !== "trending");
const BOX = `${FIELD_STATES} h-10 rounded-[12px] px-4 text-[14px]`;
const FIELD = `${BOX} w-full min-w-0`;
const LABEL = "mb-1.5 block text-[12px] text-[var(--text-secondary)]";

type Product = {
  id: string;
  canonical_name: string | null;
  brand?: string | null;
  line?: string | null;
  key_spec?: string | null;
  descriptor?: string | null;
  specs?: SpecRow[];
  category?: string | null;
  review_count?: number;
  image_url?: string | null;
};

export type EditTarget = {
  /** Empty when mode is "create": the product does not exist yet. */
  id: string;
  mode: "edit" | "admit" | "create";
  /** Shown once when the modal opens (e.g. "Added to the catalogue."). */
  notice?: string;
  name: string;
  aliases: string[];
  /** The submitted link, shown under the name in "Add to catalogue". */
  link?: string | null;
};

async function problem(res: Response, fallback: string): Promise<string> {
  const p = (await res.json().catch(() => ({}))) as { detail?: unknown };
  return typeof p.detail === "string" ? p.detail : fallback;
}

export function ProductEditModal({
  target,
  onClose,
  onOpen,
}: {
  target: EditTarget;
  onClose: () => void;
  /** Opens another product in this modal (after an add, or on a duplicate). */
  onOpen?: (next: EditTarget) => void;
}) {
  const creating = target.mode === "create";
  const router = useRouter();
  const id = useId();
  const [product, setProduct] = useState<Product | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [brand, setBrand] = useState("");
  const [category, setCategory] = useState<string | null>(null);
  const [parts, setParts] = useState<NamePart[]>([{ kind: "line", value: "" }]);
  const [specs, setSpecs] = useState<SpecRow[]>([]);
  const [aliases, setAliases] = useState<string[]>(target.aliases);
  const [newAlias, setNewAlias] = useState("");
  const [merge, setMerge] = useState<{ id: string; name: string } | null>(null);
  // "As is" naming and merge suggestions (Figma 8277:29379, 8287:29648).
  const [asIs, setAsIs] = useState(false);
  const [noBrand, setNoBrand] = useState(false);
  const [asIsName, setAsIsName] = useState(target.mode === "create" ? "" : target.name);
  const [similar, setSimilar] = useState<{ id: string; name: string; category?: string | null; review_count?: number }[]>([]);
  const [mergeInto, setMergeInto] = useState<{ id: string; name: string } | null>(null);
  const [mergeQuery, setMergeQuery] = useState("");
  const [mergeHits, setMergeHits] = useState<{ id: string; name: string }[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(target.notice ?? null);
  const [sourceUrl, setSourceUrl] = useState("");
  const [existing, setExisting] = useState<{ id: string; name: string } | null>(null);
  const file = useRef<HTMLInputElement>(null);
  // Nothing to load for a product that does not exist yet.
  const [blank] = useState<Product | null>(() => (target.mode === "create" ? { id: "", canonical_name: null, review_count: 0 } : null));

  useEffect(() => {
    if (target.mode === "create") return;
    let cancelled = false;
    fetch(`/api/bff/api/v1/products/${target.id}`)
      .then(async (res) => (res.ok ? ((await res.json()) as Product) : Promise.reject(new Error("load"))))
      .then((p) => {
        if (cancelled) return;
        setProduct(p);
        setBrand(p.brand ?? "");
        setCategory(p.category ?? null);
        // A submission starts from what the member typed, to be split into parts.
        setParts(target.mode === "edit" ? partsFrom(p) : [{ kind: "line", value: target.name }]);
        setSpecs(p.specs ?? []);
        if (target.mode === "edit" && startsAsIs(p)) {
          setAsIs(true);
          setNoBrand(true);
          setAsIsName(p.canonical_name ?? "");
        }
      })
      .catch(() => !cancelled && setLoadError("This product could not be loaded."));
    return () => {
      cancelled = true;
    };
  }, [target.id, target.mode, target.name]);

  useEffect(() => {
    if (target.mode !== "admit" || mergeQuery.trim().length < 2) return;
    const t = setTimeout(() => {
      fetch(`/api/bff/api/v1/admin/products/catalogue?limit=8&q=${encodeURIComponent(mergeQuery.trim())}`)
        .then((r) => (r.ok ? r.json() : { items: [] }))
        .then((b: { items: { id: string; name: string }[] }) => setMergeHits(b.items.filter((i) => i.id !== target.id)))
        .catch(() => setMergeHits([]));
    }, 200);
    return () => clearTimeout(t);
  }, [mergeQuery, target.mode, target.id]);

  // "Already on Bluntly? Merge instead of adding a second page."
  const typedName = asIs ? asIsName : savesAs(brand, parts, []);
  useEffect(() => {
    const q = typedName.trim();
    if (q.length < 3) return;
    let cancelled = false;
    const t = setTimeout(() => {
      fetch(`/api/bff/api/v1/admin/products/catalogue?limit=4&q=${encodeURIComponent(q)}`)
        .then((r) => (r.ok ? r.json() : { items: [] }))
        .then((b: { items: { id: string; name: string; category?: string | null; review_count?: number }[] }) => {
          if (!cancelled) setSimilar(b.items.filter((i) => i.id !== target.id).slice(0, 2));
        })
        .catch(() => !cancelled && setSimilar([]));
    }, 300);
    return () => {
      cancelled = true;
      clearTimeout(t);
    };
  }, [typedName, target.id]);

  const shown = product ?? blank;
  const name = asIs ? asIsName.replace(/\s+/g, " ").trim() : savesAs(brand, parts, specs);
  const missing = merge ? null : asIs ? asIsBlocker(asIsName, category) : blocker(brand, parts, category);
  const used = new Set(parts.map((p) => p.kind));

  async function removeAlias(a: string) {
    if (creating) return setAliases((list) => list.filter((x) => x !== a));
    const res = await fetch(`/api/bff/api/v1/products/${target.id}/aliases?alias=${encodeURIComponent(a)}`, { method: "DELETE" });
    if (res.ok || res.status === 404) setAliases((list) => list.filter((x) => x !== a));
    else setError(await problem(res, "Couldn't remove that alias."));
  }

  async function uploadPhoto(e: React.ChangeEvent<HTMLInputElement>) {
    const f = e.target.files?.[0];
    e.target.value = "";
    if (!f) return;
    setBusy(true);
    setError(null);
    try {
      const prepared = await prepareImageForUpload(f, "photo");
      if (prepared.error) {
        setError(prepared.error);
        return;
      }
      const body = new FormData();
      body.append("file", prepared.file);
      const res = await fetch(`/api/bff/api/v1/products/${target.id}/image`, { method: "POST", body });
      if (!res.ok) {
        setError(await problem(res, "That image couldn't be uploaded."));
        return;
      }
      const p = (await res.json()) as Product;
      setProduct((old) => (old ? { ...old, image_url: p.image_url } : p));
      setNotice("Photo saved.");
    } finally {
      setBusy(false);
    }
  }

  async function save() {
    if (busy || missing) return;
    setBusy(true);
    setError(null);
    setExisting(null);
    try {
      if (creating) {
        const res = await fetch("/api/bff/api/v1/admin/products", {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({
            ...(asIs ? asIsPayload(asIsName, brand, noBrand) : { brand: brand.trim(), ...partsPayload(parts) }),
            category,
            specs: specsPayload(specs),
            aliases: [...aliases, ...(newAlias.trim() ? [newAlias.trim()] : [])],
            source_url: sourceUrl.trim() || null,
          }),
        });
        if (res.status === 409) {
          const p = (await res.json().catch(() => ({}))) as { detail?: string; product_id?: string; canonical_name?: string };
          setError(p.detail ?? "That product is already in the catalogue.");
          if (p.product_id) setExisting({ id: p.product_id, name: p.canonical_name ?? "the product" });
          return;
        }
        if (!res.ok) {
          setError(await problem(res, "Couldn't add the product."));
          return;
        }
        const made = (await res.json()) as Product;
        router.refresh();
        onOpen?.({ id: made.id, mode: "edit", name: made.canonical_name ?? name, aliases: [...aliases], notice: "Added to the catalogue. Add its photo here, or close." });
        return;
      }
      if (merge) {
        const res = await fetch(`/api/bff/api/v1/products/${target.id}/attach`, {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({ target_product_id: merge.id }),
        });
        if (!res.ok) {
          setError(await problem(res, "Couldn't merge it."));
          return;
        }
      } else {
        const res = await fetch(`/api/bff/api/v1/products/${target.id}/canonicalize`, {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({
            ...(asIs ? asIsPayload(asIsName, brand, noBrand) : { brand: brand.trim(), ...partsPayload(parts) }),
            category,
            specs: specsPayload(specs),
            aliases: newAlias.trim() ? [newAlias.trim()] : [],
          }),
        });
        if (!res.ok) {
          setError(await problem(res, "Couldn't save the product."));
          return;
        }
        // MQA-004: a submission just named as a new product leaves the Queue for
        // the Catalogue; reopen it there in Edit, as "Add product" does, so its
        // name can be checked and changed straight away (and found again later).
        if (target.mode === "admit" && onOpen) {
          const made = (await res.json().catch(() => null)) as (Product & { aliases?: string[] }) | null;
          router.refresh();
          onOpen({
            id: target.id,
            mode: "edit",
            name: made?.canonical_name ?? name,
            aliases: made?.aliases ?? [],
            notice: "Added to the catalogue. Its name can be changed here at any time (Products › Catalogue › Edit).",
          });
          return;
        }
      }
      onClose();
      router.refresh();
    } catch {
      setError("Couldn't reach the server.");
    } finally {
      setBusy(false);
    }
  }

  /** Confirm/Product/Merge: this catalogue page into another (POST /products/{id}/merge). */
  async function mergeNow() {
    if (!mergeInto) return;
    setBusy(true);
    setError(null);
    try {
      const res = await fetch(`/api/bff/api/v1/products/${target.id}/merge`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ target_product_id: mergeInto.id }),
      });
      if (!res.ok) {
        setError(await problem(res, "Couldn't merge it."));
        setMergeInto(null);
        return;
      }
      setMergeInto(null);
      router.refresh();
      if (onOpen) onOpen({ id: mergeInto.id, mode: "edit", name: mergeInto.name, aliases: [], notice: `Merged. “${shown?.canonical_name ?? target.name}” is now a search alias here.` });
      else onClose();
    } catch {
      setError("Couldn't reach the server.");
    } finally {
      setBusy(false);
    }
  }

  async function addAlias() {
    const a = newAlias.trim();
    if (!a) return;
    if (creating) {
      if (!aliases.some((x) => x.toLowerCase() === a.toLowerCase())) setAliases((list) => [...list, a]);
      setNewAlias("");
      return;
    }
    const res = await fetch(`/api/bff/api/v1/products/${target.id}/aliases`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ aliases: [a] }),
    });
    if (!res.ok) {
      setError(await problem(res, "Couldn't add that alias."));
      return;
    }
    const added = (await res.json()) as string[];
    setAliases((list) => [...list, ...added]);
    setNewAlias("");
  }

  const photo = usablePhoto(shown?.image_url ?? null);
  const admit = target.mode === "admit";

  return (
    <AdminModal title={creating ? "Add product" : admit ? "Add to catalogue" : "Edit product"} onClose={onClose}>
      {loadError ? (
        <p role="alert" className="px-6 py-10 text-center text-[14px] text-[var(--text-secondary)]">
          {loadError}
        </p>
      ) : !shown ? (
        <SkeletonRegion label="Loading the product" className="flex flex-col gap-5 px-6 py-5">
          <div className="flex items-center gap-4">
            <Block className="size-20" />
            <span className="flex flex-1 flex-col gap-2">
              <Bar size={14} className="w-56 max-w-full" />
              <Bar size={8} className="w-40" />
            </span>
            <Pill className="h-9 w-28" />
          </div>
          <div className="grid gap-x-6 gap-y-5 md:grid-cols-2">
            {Array.from({ length: 6 }, (_, i) => (
              <span key={i} className="flex flex-col gap-2">
                <Bar size={10} className="w-20" />
                <Block className="h-11 w-full" />
              </span>
            ))}
          </div>
        </SkeletonRegion>
      ) : (
        <>
          <div className="flex flex-col gap-5 px-6 py-5">
            <div className="flex items-center gap-4">
              {photo ? (
                <Image src={photo} alt="" width={80} height={80} unoptimized className="size-20 shrink-0 rounded-[16px] object-cover" />
              ) : (
                <span aria-hidden className="grid size-20 shrink-0 place-items-center rounded-[16px] bg-[var(--surface-app)] text-[var(--text-secondary)]">
                  <Package size={20} />
                </span>
              )}
              <span className="flex min-w-0 flex-1 flex-col gap-1">
                <span className="truncate text-[16px] font-semibold">{creating ? name || "New product" : target.name}</span>
                {creating ? (
                  <span className="text-[12px] text-[var(--text-secondary)]">Add a photo once it is in the catalogue.</span>
                ) : admit && target.link ? (
                  <a href={target.link} target="_blank" rel="noreferrer nofollow" className="truncate text-[12px] text-[var(--chart-honesty-fund)]">
                    {target.link.replace(/^https?:\/\//, "")}
                  </a>
                ) : (
                  <span className="text-[12px] text-[var(--text-secondary)]">
                    {CATEGORY_OPTIONS.find((c) => c.slug === shown.category)?.label ?? "No category"} · {shown.review_count ?? 0}{" "}
                    {shown.review_count === 1 ? "review" : "reviews"}
                  </span>
                )}
              </span>
              {creating ? null : (
                <>
                  <button type="button" onClick={() => file.current?.click()} disabled={busy} className="h-9 shrink-0 rounded-full border border-[var(--text-primary)] px-4 text-[12px]">
                    {photo ? "Replace photo" : "Add photo"}
                  </button>
                  <input ref={file} type="file" accept="image/png,image/jpeg,image/webp" aria-label="Product image" className="hidden" onChange={uploadPhoto} />
                </>
              )}
            </div>

            {admit ? (
              <div className="relative">
                <label className={LABEL} htmlFor={`${id}-merge`}>
                  Merge into
                </label>
                {merge ? (
                  <div className="flex h-10 items-center gap-2 rounded-[12px] border border-[var(--accent-primary)] px-4 text-[14px]">
                    <span className="flex-1 truncate">{merge.name}</span>
                    <button type="button" aria-label="Don't merge" onClick={() => setMerge(null)}>
                      <X size={14} />
                    </button>
                  </div>
                ) : (
                  <input id={`${id}-merge`} className={FIELD} placeholder="Search the catalogue" value={mergeQuery} onChange={(e) => setMergeQuery(e.target.value)} />
                )}
                {!merge && mergeQuery.trim().length >= 2 && mergeHits.length > 0 ? (
                  <ul className="absolute inset-x-0 top-full z-10 mt-1 max-h-56 overflow-auto rounded-[12px] border border-[var(--border-subtle)] bg-[var(--surface-card)] shadow-[var(--shadow-card)]">
                    {mergeHits.map((h) => (
                      <li key={h.id}>
                        <button type="button" onClick={() => setMerge(h)} className="w-full px-4 py-2 text-left text-[14px] hover:bg-[var(--surface-app)]">
                          {h.name}
                        </button>
                      </li>
                    ))}
                  </ul>
                ) : null}
              </div>
            ) : null}

            {creating ? (
              <div>
                <label className={LABEL} htmlFor={`${id}-link`}>
                  Marketplace listing <span className="text-[var(--text-secondary)]">(optional)</span>
                </label>
                <input id={`${id}-link`} type="url" inputMode="url" className={FIELD} placeholder="https://shopee.ph/…" value={sourceUrl} onChange={(e) => setSourceUrl(e.target.value)} />
              </div>
            ) : null}

            <fieldset disabled={Boolean(merge)} className="grid gap-x-6 gap-y-5 disabled:opacity-50 md:grid-cols-2">
              <div>
                <label className={LABEL} htmlFor={`${id}-brand`}>
                  Brand
                </label>
                <input
                  id={`${id}-brand`}
                  className={`${FIELD} disabled:bg-[var(--surface-app)] disabled:text-[var(--text-secondary)]`}
                  value={noBrand ? "" : brand}
                  placeholder={noBrand ? "No brand" : undefined}
                  disabled={noBrand}
                  onChange={(e) => setBrand(e.target.value)}
                />
                <label className="mt-2 flex items-center gap-2 text-[14px]">
                  <input
                    type="checkbox"
                    checked={noBrand}
                    onChange={(e) => {
                      setNoBrand(e.target.checked);
                      // A product with no brand is named as is.
                      if (e.target.checked && !asIs) {
                        setAsIs(true);
                        setAsIsName(name || asIsName);
                      }
                    }}
                    className="size-4 accent-[var(--accent-primary)]"
                  />
                  No brand <span className="text-[12px] text-[var(--text-secondary)]">· generic or unbranded</span>
                </label>
              </div>
              <div>
                <label className={LABEL} htmlFor={`${id}-cat`}>
                  Category
                </label>
                <select id={`${id}-cat`} className={FIELD} value={category ?? ""} onChange={(e) => setCategory(e.target.value || null)}>
                  <option value="">Choose a category</option>
                  {CATEGORY_OPTIONS.map((c) => (
                    <option key={c.slug} value={c.slug}>
                      {c.label}
                    </option>
                  ))}
                </select>
              </div>

              <div className="flex flex-col gap-2">
                <div className="flex items-center gap-3">
                  <span className={`${LABEL} mb-0 flex-1`}>Name</span>
                  <div role="radiogroup" aria-label="How the name is written" className="flex gap-[2px] rounded-[10px] bg-[var(--surface-app)] p-[3px]">
                    {([
                      [false, "From parts"],
                      [true, "As is"],
                    ] as const).map(([value, label]) => (
                      <button
                        key={label}
                        type="button"
                        role="radio"
                        aria-checked={asIs === value}
                        onClick={() => {
                          if (value && !asIs) setAsIsName(name || asIsName);
                          if (!value) setNoBrand(false);
                          setAsIs(value);
                        }}
                        className={`rounded-[8px] px-3 py-[5px] text-[14px] leading-none ${asIs === value ? "bg-[var(--surface-card)] shadow-[var(--shadow-segment)]" : "text-[var(--text-secondary)]"}`}
                      >
                        {label}
                      </button>
                    ))}
                  </div>
                </div>
                {asIs ? (
                  <>
                    <input aria-label="Name, as is" className={FIELD} value={asIsName} onChange={(e) => setAsIsName(e.target.value)} />
                    <p className="text-[12px] text-[var(--text-secondary)]">Saved exactly as typed. Use it when there’s no brand, line or model.</p>
                  </>
                ) : null}
                {!asIs && parts.map((p, i) => (
                  <div key={i} className="flex items-center gap-2">
                    <select
                      aria-label={`Name part ${i + 1}`}
                      className={`${BOX} w-[160px] shrink-0`}
                      value={p.kind}
                      onChange={(e) => setParts((list) => list.map((x, j) => (j === i ? { ...x, kind: e.target.value as PartKind } : x)))}
                    >
                      {PART_KINDS.filter((k) => k === p.kind || !used.has(k)).map((k) => (
                        <option key={k} value={k}>
                          {PART_LABEL[k]}
                        </option>
                      ))}
                    </select>
                    <input
                      aria-label={PART_LABEL[p.kind]}
                      className={FIELD}
                      value={p.value}
                      onChange={(e) => setParts((list) => list.map((x, j) => (j === i ? { ...x, value: e.target.value } : x)))}
                    />
                    <button
                      type="button"
                      aria-label={`Remove ${PART_LABEL[p.kind]}`}
                      disabled={p.kind === "line"}
                      onClick={() => setParts((list) => list.filter((_, j) => j !== i))}
                      className="grid size-8 shrink-0 place-items-center disabled:invisible"
                    >
                      <X size={16} />
                    </button>
                  </div>
                ))}
                {!asIs && used.size < PART_KINDS.length ? (
                  <button
                    type="button"
                    onClick={() => setParts((list) => [...list, { kind: PART_KINDS.find((k) => !used.has(k))!, value: "" }])}
                    className="flex w-fit items-center gap-1 text-[14px] text-[var(--chart-honesty-fund)]"
                  >
                    <Plus size={16} /> Add part
                  </button>
                ) : null}
                {similar.length > 0 && typedName.trim().length >= 3 && !merge ? (
                  <div className="flex flex-col gap-2 rounded-[12px] bg-[var(--surface-app)] p-3" data-testid="merge-suggestions">
                    <p className="text-[12px] font-medium">Already on Bluntly? {creating ? "Open it instead of adding a second page." : "Merge instead of adding a second page."}</p>
                    {similar.map((hit) => (
                      <div key={hit.id} className="flex items-center gap-3">
                        <Package size={16} aria-hidden className="shrink-0" />
                        <span className="flex min-w-0 flex-1 flex-col gap-1 leading-none">
                          <span className="truncate text-[14px]">{hit.name}</span>
                          <span className="text-[12px] text-[var(--text-secondary)]">
                            {[CATEGORY_OPTIONS.find((c) => c.slug === hit.category)?.label, hit.review_count != null ? `${hit.review_count} review${hit.review_count === 1 ? "" : "s"}` : null].filter(Boolean).join(" · ")}
                          </span>
                        </span>
                        <button
                          type="button"
                          onClick={() =>
                            creating
                              ? onOpen?.({ id: hit.id, mode: "edit", name: hit.name, aliases: [] })
                              : admit
                                ? setMerge({ id: hit.id, name: hit.name })
                                : setMergeInto({ id: hit.id, name: hit.name })
                          }
                          className="shrink-0 text-[12px] text-[var(--chart-honesty-fund)] hover:underline"
                        >
                          {creating ? "Open" : "Merge"}
                        </button>
                      </div>
                    ))}
                  </div>
                ) : null}
                {asIs ? (
                  <button type="button" onClick={() => setAsIs(false)} className="w-fit text-[12px] text-[var(--chart-honesty-fund)] hover:underline">
                    Split into parts
                  </button>
                ) : null}
                <span className={`${LABEL} mt-3`}>Also known as</span>
                {/* Admin/Input states on the box that holds the chips and the typing (8265:27094). */}
                <div className="flex min-h-[52px] flex-wrap items-center gap-2 rounded-[12px] border border-[var(--line-hairline-30)] p-2 hover:border-[var(--border-input-hover)] focus-within:border-[var(--accent-primary)] focus-within:shadow-[var(--ring-field-focus)] focus-within:hover:border-[var(--accent-primary)]">
                  {aliases.map((a) => (
                    <span key={a} className="flex items-center gap-1 rounded-full border border-[var(--border-subtle)] px-3 py-1 text-[12px]">
                      {a}
                      <button type="button" aria-label={`Remove alias ${a}`} onClick={() => void removeAlias(a)}>
                        <X size={12} />
                      </button>
                    </span>
                  ))}
                  <input
                    aria-label="Add an alias"
                    placeholder={aliases.length ? "" : "Add a name people use"}
                    value={newAlias}
                    onChange={(e) => setNewAlias(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter") {
                        e.preventDefault();
                        void addAlias();
                      }
                    }}
                    className="min-w-[120px] flex-1 bg-transparent px-1 text-[14px] outline-none"
                  />
                </div>
              </div>

              <div className="flex flex-col gap-2">
                <span className="flex items-center">
                  <span className={`${LABEL} flex-1`}>Specs</span>
                  <span className={`${LABEL} w-[84px]`}>In name</span>
                </span>
                {specs.map((s, i) => (
                  <div key={i} className="flex items-center gap-2">
                    <input
                      aria-label={`Spec ${i + 1} label`}
                      className={`${BOX} w-[160px] shrink-0`}
                      value={s.label}
                      onChange={(e) => setSpecs((list) => list.map((x, j) => (j === i ? { ...x, label: e.target.value } : x)))}
                    />
                    <input
                      aria-label={`Spec ${i + 1} value`}
                      placeholder="Optional"
                      className={FIELD}
                      value={s.value}
                      onChange={(e) => setSpecs((list) => list.map((x, j) => (j === i ? { ...x, value: e.target.value } : x)))}
                    />
                    <Switch
                      checked={s.in_name}
                      label={`${s.label || "Spec"} in the name`}
                      onChange={(on) => setSpecs((list) => list.map((x, j) => (j === i ? { ...x, in_name: on } : x)))}
                    />
                    <button type="button" aria-label={`Remove spec ${s.label}`} onClick={() => setSpecs((list) => list.filter((_, j) => j !== i))} className="grid size-8 shrink-0 place-items-center">
                      <X size={16} />
                    </button>
                  </div>
                ))}
                {specs.length < 12 ? (
                  <button
                    type="button"
                    onClick={() => setSpecs((list) => [...list, { label: "", value: "", in_name: false }])}
                    className="flex w-fit items-center gap-1 text-[14px] text-[var(--chart-honesty-fund)]"
                  >
                    <Plus size={16} /> Add spec
                  </button>
                ) : null}
              </div>
            </fieldset>
            {error ? (
              <p role="alert" className="flex flex-wrap items-center gap-2 text-[12px] text-[var(--accent-danger)]">
                {error}
                {existing && onOpen ? (
                  <button
                    type="button"
                    onClick={() => onOpen({ id: existing.id, mode: "edit", name: existing.name, aliases: [] })}
                    className="h-7 rounded-full border border-[var(--text-primary)] px-3 text-[12px] text-[var(--text-primary)]"
                  >
                    Edit it
                  </button>
                ) : null}
              </p>
            ) : null}
            {notice ? (
              <p role="status" className="text-[12px] text-[var(--text-secondary)]">
                {notice}
              </p>
            ) : null}
          </div>
          <div className="flex flex-wrap items-center gap-3 border-t border-[var(--border-subtle)] px-6 py-4">
            {admit || creating ? (
              <span className="flex min-w-0 flex-1 flex-col">
                <span className="text-[12px] text-[var(--text-secondary)]">{merge ? "Merges into" : "Saves as"}</span>
                <span className="truncate text-[14px] font-medium" data-testid="saves-as">
                  {merge ? merge.name : name || "—"}
                </span>
              </span>
            ) : null}
            <button type="button" onClick={onClose} className="h-9 rounded-full border border-[var(--text-primary)] px-4 text-[12px]">
              Cancel
            </button>
            <button
              type="button"
              onClick={() => void save()}
              disabled={busy || Boolean(missing)}
              title={missing ?? undefined}
              className="h-9 rounded-full bg-[var(--accent-primary)] px-4 text-[12px] text-white disabled:opacity-50"
            >
              {busy ? "Saving…" : creating ? "Add product" : admit ? (merge ? "Merge into product" : "Add to catalogue") : "Save changes"}
            </button>
            {missing ? <span className="text-[12px] text-[var(--text-secondary)]">{missing}</span> : null}
          </div>
        </>
      )}
      <ConfirmDialog
        open={mergeInto !== null}
        title={`Merge into ${mergeInto?.name ?? "this product"}?`}
        confirmLabel="Merge"
        busyLabel="Merging…"
        busy={busy}
        error={error}
        onConfirm={() => void mergeNow()}
        onClose={() => setMergeInto(null)}
      >
        <p>Reviews, questions and links move to {mergeInto?.name}.</p>
        <p>“{shown?.canonical_name ?? target.name}” stays as a search alias.</p>
      </ConfirmDialog>
    </AdminModal>
  );
}
