"use client";

import Image from "next/image";
import { useEffect, useId, useState } from "react";
import { ImageSquare, LinkSimple, MagnifyingGlass } from "@phosphor-icons/react/dist/ssr";

import { ProductStepDecor } from "@/components/reviews/ProductStepDecor";
import { TiltedRatingCards, type TiltedCard } from "@/components/reviews/TiltedRatingCards";
import { usablePhoto } from "@/lib/image";
import { CATEGORIES } from "@/lib/landing-data";
import { initialProposedName, linkedProductProblem } from "@/components/reviews/product-link-model";
import { LINK_FIELD_STATES } from "@/components/ui/search-styles";
import { PUBLIC_FIELD_STATES, PUBLIC_FILL } from "@/components/ui/field-styles";

export type PickedProduct = {
  id: string;
  canonical_name: string | null;
  category: string | null;
  /**
   * The product photo the catalogue already stores.
   *
   * QA-001: the picker drew a grey square for every result and never asked for
   * this, so a reviewer choosing between "Anker 737" and "Aukey 10000mAh" had
   * two identical blank tiles to tell them apart. `ProductOut` has served
   * `image_url` all along; only this type omitted it.
   */
  image_url: string | null;
};

/**
 * One search result, Figma "Reviewer Page - Step 1" (4431:442) and "Question
 * Page - Step 1" (4709:14832): the product in 14px Bold, 12px down its spec
 * rows — a 44px white disc holding a 32px glyph in a 1.5px black outline, the
 * value in 12px Regular and its name under it in 10px Light — and the product
 * photo at 120px, radius 16, on the right. Rows sit 16px under a full-bleed
 * hairline and 36px above the next.
 *
 * INTENTIONAL PRODUCT DIFFERENCE: the frames' specs are "Battery" and
 * "Variants". The catalogue holds neither, so the one real attribute a product
 * carries — its category — is the spec row, with that category's own glyph.
 */
function ProductResult({ product, onPick }: { product: PickedProduct; onPick: (p: PickedProduct) => void }) {
  const src = usablePhoto(product.image_url);
  const category = CATEGORIES.find((c) => c.slug === product.category);
  const CategoryIcon = category?.icon;

  return (
    <button
      type="button"
      onClick={() => onPick(product)}
      className="flex w-full cursor-pointer items-start justify-between gap-4 px-4 pb-9 pt-4 text-left hover:bg-[var(--line-hairline-10)] focus-visible:outline focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-[var(--accent-primary)] sm:px-6"
    >
      <span className="min-w-0 flex-1">
        <span className="block text-[14px] font-bold leading-[21px] text-[var(--text-primary)]">
          {product.canonical_name ?? "Unnamed product"}
        </span>
        {category && CategoryIcon ? (
          <span className="mt-3 flex items-center gap-3">
            <span className="grid h-11 w-11 shrink-0 place-items-center rounded-full bg-[var(--surface-card)]">
              <CategoryIcon size={32} weight="light" aria-hidden="true" className="text-[var(--base-black)]" />
            </span>
            <span className="flex flex-col">
              <span className="text-[12px] leading-none text-[var(--text-primary)]">{category.label}</span>
              <span className="mt-1.5 text-[10px] font-light leading-none text-[var(--text-primary)]">Category</span>
            </span>
          </span>
        ) : null}
      </span>
      <span className="relative grid h-[120px] w-[120px] shrink-0 place-items-center overflow-hidden rounded-[16px] bg-[#e1e1e1]">
        {src ? (
          <Image src={src} alt="" fill sizes="120px" className="object-cover" />
        ) : (
          <ImageSquare size={28} weight="light" aria-hidden="true" className="text-[var(--base-gray-400)]" />
        )}
      </span>
    </button>
  );
}

/**
 * The composers' first step: find the product. Shared by "Reviewer Page - Step
 * 1" (4431:442) and "Question Page - Step 1" (4705:14719 / 4709:14832), which
 * draw the same stack with their own words: "Let's get started!" in 12px
 * Regular, the question 10px lower in 20px Medium brand orange, the blurb 10px
 * lower in 12px Light at 70%; a 56px field at pill radius with a 1px #323232
 * outline and the query 24px in, in 16px Regular at 0.8px tracking; results
 * 25px under it; the link field pinned 35px above the bottom edge.
 */
export function ProductPicker({
  onPick,
  title,
  blurb,
  placeholder,
  searchLabel,
  fieldClassName = "mt-4",
  decorCards,
  emptyHint = true,
}: {
  onPick: (p: PickedProduct) => void;
  title: string;
  blurb: string;
  placeholder: string;
  searchLabel: string;
  fieldClassName?: string;
  /** The frame's own tilted cards behind the idle step; the reviewer frame's layer when omitted. */
  decorCards?: TiltedCard[];
  /** The magnifier and "Find the product you bought": the reviewer frame draws them, the question frame does not. */
  emptyHint?: boolean;
}) {
  const [q, setQ] = useState("");
  const [results, setResults] = useState<PickedProduct[]>([]);
  const [busy, setBusy] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [sourceUrl, setSourceUrl] = useState("");
  const [error, setError] = useState<string | null>(null);
  const linkId = useId();
  // QA-072: after "Use this link", the proposed product before it is sent.
  const [proposal, setProposal] = useState<{
    url: string;
    marketplace: string | null;
    name: string;
    category: string;
    existing: PickedProduct | null;
  } | null>(null);
  const nameId = useId();
  const categoryId = useId();

  const query = q.trim();
  const searching = query.length >= 2;

  useEffect(() => {
    if (!searching) return;
    const t = setTimeout(async () => {
      setBusy(true);
      try {
        const res = await fetch(`/api/bff/api/v1/products?q=${encodeURIComponent(query)}&limit=8`);
        setResults(res.ok ? await res.json() : []);
      } catch {
        setResults([]);
      } finally {
        setBusy(false);
      }
    }, 300);
    return () => clearTimeout(t);
  }, [query, searching]);

  const visibleResults = searching ? results : [];

  /**
   * Submit an unlisted product (BUG-020, QA-071, QA-072).
   *
   * A marketplace link, not a name the reviewer invents. The API stores the row
   * `pending` for an administrator to name canonically — otherwise "Jisulife fan"
   * and "JISULIFE Life 9" become separate products and their reviews never
   * meet. First the link is read (never fetched): if bluntly already has that
   * exact listing, the reviewer is offered it; otherwise they confirm a
   * PROPOSED name — the one written into the link, editable — and a category.
   */
  async function readLink() {
    const url = sourceUrl.trim();
    if (!url || submitting) return;
    if (!/^https?:\/\//i.test(url)) {
      setError("Paste the full link, starting with https://");
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      const res = await fetch(`/api/bff/api/v1/products/resolve-link?url=${encodeURIComponent(url)}`);
      if (!res.ok) {
        const p = (await res.json().catch(() => ({}))) as { detail?: string };
        setError(p.detail ?? "Couldn't read that link.");
        return;
      }
      const body = (await res.json()) as {
        url: string;
        marketplace: string | null;
        proposed_name: string | null;
        existing_product: PickedProduct | null;
      };
      setProposal({
        url: body.url,
        marketplace: body.marketplace,
        name: initialProposedName(body.proposed_name, query),
        category: body.existing_product?.category ?? "",
        existing: body.existing_product,
      });
    } catch {
      setError("Couldn't reach the server.");
    } finally {
      setSubmitting(false);
    }
  }

  async function submitProposal() {
    if (!proposal || submitting) return;
    const problem = linkedProductProblem(proposal.name, proposal.category);
    if (problem) {
      setError(problem);
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      const res = await fetch("/api/bff/api/v1/products", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ name: proposal.name.trim(), category: proposal.category, source_url: proposal.url }),
      });
      if (!res.ok) {
        const p = (await res.json().catch(() => ({}))) as { detail?: unknown };
        setError(typeof p.detail === "string" ? p.detail : "Couldn't submit that product.");
        return;
      }
      onPick(await res.json());
    } catch {
      setError("Couldn't reach the server.");
    } finally {
      setSubmitting(false);
    }
  }

  const proposalProblem = proposal ? linkedProductProblem(proposal.name, proposal.category) : null;
  const pickable = CATEGORIES.filter((c) => c.slug !== "trending");

  return (
    // `relative isolate` so the decorative cards behind the empty state sit
    // behind this step's content rather than behind the page.
    <div className="relative isolate">
      {!searching ? (
        decorCards ? (
          <TiltedRatingCards cards={decorCards} className="fixed inset-x-0 bottom-0 top-[72px] -z-10 hidden max-sm:block" />
        ) : (
          <ProductStepDecor />
        )
      ) : null}
      <p className="text-[12px] leading-none text-[var(--text-primary)]">Let&rsquo;s get started!</p>
      <h1 className="mt-2.5 text-[20px] font-medium leading-none text-[var(--accent-primary)]">{title}</h1>
      <p className="mt-[7px] text-[12px] font-light leading-[18px] text-[rgba(32,32,32,0.7)]">{blurb}</p>

      <input
        value={q}
        onChange={(e) => setQ(e.target.value)}
        aria-label={searchLabel}
        placeholder={placeholder}
        className={`${fieldClassName} h-14 w-full rounded-[var(--radius-pill)] border border-[var(--base-gray-600)] bg-[var(--surface-app)] px-6 text-[16px] tracking-[0.8px] text-[var(--text-primary)] outline-none placeholder:text-[var(--text-muted)] focus-visible:border-[var(--accent-primary)]`}
      />

      {searching && !busy ? (
        <p aria-live="polite" className="mt-[25px] text-[12px] leading-none text-[var(--text-primary)]">
          {visibleResults.length} {visibleResults.length === 1 ? "result" : "results"} found
        </p>
      ) : null}

      {visibleResults.length > 0 ? (
        <ul className="-mx-4 mt-[17px] border-t border-[var(--line-hairline-10)] sm:-mx-6 md:mx-0">
          {visibleResults.map((p) => (
            <li key={p.id} className="border-b border-[var(--line-hairline-10)]">
              <ProductResult product={p} onPick={onPick} />
            </li>
          ))}
        </ul>
      ) : null}

      {/* The empty state under the field, as the reviewer's step 1 frame draws
          it: 174px down a 64px MagnifyingGlass in a 2px line, "Find the product
          you bought" 16px lower in 16px Regular at 0.8px tracking, and the hint
          in 12px Light at 70% on 18px lines, 180px wide. */}
      {!searching && emptyHint ? (
        <div className="flex flex-col items-center pb-16 pt-[174px] text-center md:pb-0 md:pt-24">
          <MagnifyingGlass size={64} weight="thin" aria-hidden="true" className="text-[var(--base-black)]" />
          <p className="mt-4 text-[16px] leading-none tracking-[0.8px] text-[var(--text-primary)]">
            Find the product you bought
          </p>
          <p className="mt-[9px] w-[180px] text-[12px] font-light leading-[1.5] text-[rgba(32,32,32,0.7)]">
            No need for the exact model. Just type what you know
          </p>
        </div>
      ) : null}

      {/* "Can't find product? Paste Shopee link here": a 52px card at radius
          12, white at 30% with a 0 4px 4px shadow at 10%, 35px above the bottom
          edge — a 20px LinkSimple in #8c8c8c and 14px Regular at 30% ink. It is
          the paste field itself, so the link goes straight in and a short
          action appears once there is something to send. On the website it
          follows the results instead of floating over them. */}
      <div className="fixed inset-x-0 bottom-[35px] z-20 px-4 sm:px-6 md:static md:mt-12 md:px-0">
        <div className="mx-auto w-full max-w-[42rem]">
          {error ? (
            <p role="alert" className="mb-2 text-[12px] text-[var(--accent-danger)]">
              {error}
            </p>
          ) : null}
          {proposal ? (
            <div
              role="group"
              aria-label="The product this link is for"
              className="mb-2 rounded-[12px] bg-[var(--surface-app)] p-4 shadow-[var(--shadow-card)]"
            >
              {proposal.existing ? (
                <>
                  <p className="text-[13px] text-[var(--text-primary)]">
                    Already on bluntly: <span className="font-semibold">{proposal.existing.canonical_name}</span>
                  </p>
                  <div className="mt-3 flex flex-wrap gap-3">
                    <button
                      type="button"
                      onClick={() => proposal.existing && onPick(proposal.existing)}
                      className="cursor-pointer rounded-[20px] bg-[var(--accent-primary)] px-3 py-2 text-[12px] leading-none text-[var(--text-on-brand)]"
                    >
                      Review this product
                    </button>
                    <button
                      type="button"
                      onClick={() => setProposal(null)}
                      className="cursor-pointer text-[12px] text-[var(--text-secondary)] underline-offset-4 hover:underline"
                    >
                      Cancel
                    </button>
                  </div>
                </>
              ) : (
                <>
                  <label htmlFor={nameId} className="block text-[12px] font-medium text-[var(--text-primary)]">
                    Product name
                  </label>
                  <input
                    id={nameId}
                    value={proposal.name}
                    onChange={(e) => setProposal({ ...proposal, name: e.target.value.slice(0, 160) })}
                    placeholder="e.g. Anker Soundcore Q20i"
                    aria-describedby={`${nameId}-hint`}
                    className={`mt-1 h-10 px-3 ${PUBLIC_FIELD_STATES} ${PUBLIC_FILL}`}
                  />
                  <p id={`${nameId}-hint`} className="mt-1 text-[11px] text-[var(--text-secondary)]">
                    {proposal.name
                      ? "Taken from the link. Correct it if it's wrong — an administrator confirms the final name."
                      : "This link doesn't include the product's name. Type it — an administrator confirms the final name."}
                  </p>
                  <label htmlFor={categoryId} className="mt-3 block text-[12px] font-medium text-[var(--text-primary)]">
                    Category
                  </label>
                  <select
                    id={categoryId}
                    value={proposal.category}
                    onChange={(e) => setProposal({ ...proposal, category: e.target.value })}
                    className={`mt-1 h-10 px-3 ${PUBLIC_FIELD_STATES} ${PUBLIC_FILL}`}
                  >
                    <option value="">Choose a category</option>
                    {pickable.map((c) => (
                      <option key={c.slug} value={c.slug}>
                        {c.label}
                      </option>
                    ))}
                  </select>
                  <div className="mt-3 flex flex-wrap items-center gap-3">
                    <button
                      type="button"
                      onClick={submitProposal}
                      disabled={submitting || proposalProblem !== null}
                      className="cursor-pointer rounded-[20px] bg-[var(--accent-primary)] px-3 py-2 text-[12px] leading-none text-[var(--text-on-brand)] disabled:cursor-not-allowed disabled:opacity-50"
                    >
                      {submitting ? "Adding…" : "Add product"}
                    </button>
                    <button
                      type="button"
                      onClick={() => setProposal(null)}
                      className="cursor-pointer text-[12px] text-[var(--text-secondary)] underline-offset-4 hover:underline"
                    >
                      Cancel
                    </button>
                  </div>
                </>
              )}
            </div>
          ) : null}
          <div className={`flex h-[52px] items-center gap-2 rounded-[12px] bg-[rgba(255,255,255,0.3)] px-4 shadow-[0_4px_4px_0_var(--shadow-color-10)] backdrop-blur-sm ${LINK_FIELD_STATES}`}>
            <LinkSimple size={20} weight="light" aria-hidden="true" className="shrink-0 text-[var(--base-gray-400)]" />
            <label className="sr-only" htmlFor={linkId}>
              Can&rsquo;t find the product? Paste its Shopee or Lazada link
            </label>
            <input
              id={linkId}
              value={sourceUrl}
              onChange={(e) => {
                setSourceUrl(e.target.value);
                setProposal(null);
              }}
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  e.preventDefault();
                  void readLink();
                }
              }}
              inputMode="url"
              placeholder="Can’t find product? Paste Shopee link here"
              className="min-w-0 flex-1 bg-transparent text-[14px] leading-none text-[var(--text-primary)] outline-none placeholder:text-[rgba(32,32,32,0.3)]"
            />
            {sourceUrl.trim() && !proposal ? (
              <button
                type="button"
                onClick={readLink}
                disabled={submitting}
                className="shrink-0 cursor-pointer rounded-[20px] bg-[var(--accent-primary)] px-3 py-2 text-[12px] font-light leading-none text-[var(--text-on-brand)] disabled:opacity-60"
              >
                {submitting ? "Reading…" : "Use this link"}
              </button>
            ) : null}
          </div>
        </div>
      </div>
    </div>
  );
}

export default ProductPicker;
