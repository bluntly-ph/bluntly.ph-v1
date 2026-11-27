"use client";

import { useEffect, useId, useState } from "react";
import { PUBLIC_INPUT } from "@/components/ui/field-styles";

export type RequestProduct = { id: string; canonical_name: string | null };

/**
 * Which product the request is about. Required: every request belongs to its
 * product's thread for good, and every later review of that product answers
 * it (dev/QA sync 2026-09-29). A plain search over the catalogue the review
 * composer uses, so the asker picks the same canonical product a reviewer
 * will write about.
 */
export function RequestProductField({
  value,
  onChange,
}: {
  value: RequestProduct | null;
  onChange: (p: RequestProduct | null) => void;
}) {
  const id = useId();
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<RequestProduct[]>([]);
  const [searching, setSearching] = useState(false);

  const term = query.trim();
  // Derived, not reset in the effect: a short query or a chosen product shows
  // no list, whatever the last search returned.
  const shown = value || term.length < 2 ? [] : results;

  useEffect(() => {
    if (value || term.length < 2) return;
    const controller = new AbortController();
    const timer = setTimeout(() => {
      setSearching(true);
      fetch(`/api/bff/api/v1/products?q=${encodeURIComponent(term)}&limit=6`, {
        signal: controller.signal,
      })
        .then((res) => (res.ok ? (res.json() as Promise<RequestProduct[] | { items: RequestProduct[] }>) : []))
        .then((body) => setResults(Array.isArray(body) ? body : (body.items ?? [])))
        .catch(() => undefined)
        .finally(() => setSearching(false));
    }, 200);
    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [term, value]);

  if (value) {
    return (
      <div className="flex flex-col gap-1.5">
        <span className="text-[13px] font-medium text-[var(--text-primary)]">Product</span>
        <div className="flex items-center justify-between gap-3 rounded-[var(--radius-sm)] bg-[var(--surface-card)] px-4 py-2.5 shadow-[var(--shadow-hairline-inset)]">
          <span data-testid="request-product" className="text-[14px] text-[var(--text-primary)]">
            {value.canonical_name ?? "Unnamed product"}
          </span>
          <button
            type="button"
            onClick={() => onChange(null)}
            className="text-[13px] font-medium text-[var(--accent-primary)] underline"
          >
            Change
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-1.5">
      <label htmlFor={id} className="text-[13px] font-medium text-[var(--text-primary)]">
        Which product? <span className="font-normal text-[var(--text-secondary)]">(required)</span>
      </label>
      <input
        id={id}
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        placeholder="Search for the product, e.g. Tefal wok pan"
        autoComplete="off"
        className={PUBLIC_INPUT}
      />
      {shown.length > 0 ? (
        <ul aria-label="Matching products" className="flex flex-col gap-1">
          {shown.map((p) => (
            <li key={p.id}>
              <button
                type="button"
                onClick={() => onChange(p)}
                className="w-full rounded-[var(--radius-sm)] bg-[var(--surface-card)] px-4 py-2 text-left text-[14px] text-[var(--text-primary)] shadow-[var(--shadow-hairline-inset)] hover:bg-[var(--line-hairline-10)]"
              >
                {p.canonical_name ?? "Unnamed product"}
              </button>
            </li>
          ))}
        </ul>
      ) : query.trim().length >= 2 && !searching ? (
        <p className="text-[12px] text-[var(--text-secondary)]">
          No product by that name yet. Write the first review of it, or ask about one that is listed.
        </p>
      ) : null}
    </div>
  );
}
