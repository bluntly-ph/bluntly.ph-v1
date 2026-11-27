"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useMemo, useRef, useState } from "react";
import { CaretDown, Check, ListChecks, MagnifyingGlass, Package } from "@phosphor-icons/react";
import { SEARCH_FIELD_STATES, SEARCH_INPUT } from "@/components/ui/search-styles";

export type ChooserProduct = {
  product_id: string;
  name: string;
  image_url: string | null;
  earned: string;
  published_at?: string | null;
};

function Thumb({ src }: { src: string | null }) {
  const [failed, setFailed] = useState(false);
  if (!src || failed) {
    return (
      <span aria-hidden className="grid size-10 shrink-0 place-items-center rounded-[10px] bg-[var(--surface-app)] text-[var(--base-gray-400)]">
        <Package size={18} />
      </span>
    );
  }
  // eslint-disable-next-line @next/next/no-img-element -- product images come from many hosts
  return <img src={src} alt="" onError={() => setFailed(true)} className="size-10 shrink-0 rounded-[10px] object-cover" />;
}

const peso = (v: string) => `₱${Number(v).toLocaleString("en-PH", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
const day = (iso: string) => new Date(iso).toLocaleDateString("en-US", { month: "short", day: "numeric", timeZone: "Asia/Manila" });

/**
 * Performance's review switcher (Figma Switcher 7761:7896 opening the sheet
 * Screen/Performance/Choose review 7849:9886): the orange pill names the
 * chosen review; the sheet lists "All reviews" then each product reviewed,
 * with what it earned this period and when it was posted, searchable by name.
 * Choosing writes `?product=` to the URL, like the other dashboard pickers.
 */
export function ReviewChooser({
  value,
  products,
  totalReviews,
  totalEarned,
  periodLabel,
}: {
  value: string;
  products: ChooserProduct[];
  totalReviews: number;
  totalEarned: string;
  /** "this week" / "this month": what the earned figures cover. */
  periodLabel: string;
}) {
  const router = useRouter();
  const pathname = usePathname() ?? "/dashboard/insights";
  const search = useSearchParams();
  const ref = useRef<HTMLDialogElement>(null);
  const [query, setQuery] = useState("");
  const current = products.find((p) => p.product_id === value)?.name ?? "All reviews";
  const shown = useMemo(() => {
    const q = query.trim().toLowerCase();
    return q ? products.filter((p) => p.name.toLowerCase().includes(q)) : products;
  }, [products, query]);

  function choose(id: string) {
    ref.current?.close();
    const next = new URLSearchParams(search?.toString() ?? "");
    if (id) next.set("product", id);
    else next.delete("product");
    router.push(`${pathname}?${next.toString()}`, { scroll: false });
  }

  const row = (selected: boolean) =>
    `flex w-full items-center gap-3 rounded-[16px] border px-3 py-2 text-left ${selected ? "border-[var(--accent-primary)] bg-[var(--status-high-bg)]" : "border-transparent hover:bg-[var(--surface-app)]"}`;

  return (
    <>
      <button
        type="button"
        aria-haspopup="dialog"
        onClick={() => ref.current?.showModal()}
        className="inline-flex h-8 min-w-0 shrink items-center gap-[6px] rounded-[16px] bg-[var(--accent-primary)] pl-[14px] pr-[10px] text-[12px] font-medium leading-normal text-white focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--accent-primary)]"
      >
        <span className="sr-only">Review: </span>
        <span className="truncate">{current}</span>
        <CaretDown size={16} aria-hidden className="shrink-0" />
      </button>
      <dialog
        ref={ref}
        aria-labelledby="choose-review-title"
        onClick={(e) => {
          if (e.target === e.currentTarget) e.currentTarget.close();
        }}
        className="m-0 mt-auto max-h-[85dvh] w-full max-w-none rounded-t-[32px] bg-[var(--surface-card)] p-0 text-[var(--text-primary)] backdrop:bg-black/40 md:m-auto md:max-w-[440px] md:rounded-[32px]"
      >
        <div className="flex max-h-[85dvh] flex-col gap-3 px-4 pb-6 pt-2">
          <span aria-hidden className="mx-auto h-1 w-10 rounded-full bg-[var(--base-gray-200)]" />
          <h2 id="choose-review-title" className="flex items-center gap-2 px-1 text-[16px] font-medium">
            <ListChecks size={18} aria-hidden /> Choose a review
          </h2>
          <label className={`flex h-12 items-center gap-2 rounded-full px-4 ${SEARCH_FIELD_STATES}`}>
            <MagnifyingGlass size={18} aria-hidden />
            <input
              type="search"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search your reviews"
              aria-label="Search your reviews"
              className={`${SEARCH_INPUT} text-[16px]`}
            />
          </label>
          <ul className="flex flex-col gap-1 overflow-y-auto">
            {query.trim() ? null : (
              <li>
                <button type="button" aria-pressed={!value} onClick={() => choose("")} className={row(!value)}>
                  <span aria-hidden className="grid size-10 shrink-0 place-items-center rounded-[10px] bg-[var(--surface-app)]">
                    <ListChecks size={18} />
                  </span>
                  <span className="flex min-w-0 flex-1 flex-col gap-[2px]">
                    <span className="text-[14px] font-medium">All reviews</span>
                    <span className="text-[12px] text-[var(--base-gray-400)]">
                      {totalReviews} {totalReviews === 1 ? "review" : "reviews"} · {peso(totalEarned)} earned {periodLabel}
                    </span>
                  </span>
                  {!value ? <Check size={18} aria-hidden className="text-[var(--accent-primary)]" /> : null}
                </button>
              </li>
            )}
            {shown.map((p) => {
              const selected = p.product_id === value;
              return (
                <li key={p.product_id}>
                  <button type="button" aria-pressed={selected} onClick={() => choose(p.product_id)} className={row(selected)}>
                    <Thumb src={p.image_url} />
                    <span className="flex min-w-0 flex-1 flex-col gap-[2px]">
                      <span className={`truncate text-[14px] font-medium ${selected ? "text-[var(--accent-primary)]" : ""}`}>{p.name}</span>
                      <span className={`text-[12px] ${selected ? "text-[var(--accent-primary)]" : "text-[var(--base-gray-400)]"}`}>
                        {peso(p.earned)} earned{p.published_at ? ` · ${day(p.published_at)}` : ""}
                      </span>
                    </span>
                    {selected ? <Check size={18} aria-hidden className="text-[var(--accent-primary)]" /> : null}
                  </button>
                </li>
              );
            })}
            {shown.length === 0 ? <li className="px-3 py-4 text-[13px] text-[var(--base-gray-400)]">No review matches “{query.trim()}”.</li> : null}
          </ul>
        </div>
      </dialog>
    </>
  );
}
