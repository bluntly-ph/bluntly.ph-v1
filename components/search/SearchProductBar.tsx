"use client";

import Image from "next/image";
import Link from "next/link";
import { useEffect, useState } from "react";
import { CaretDown, ChartLine, Check, CheckCircle, Question as QuestionIcon, Star, X } from "@phosphor-icons/react/dist/ssr";

import { PriceHistorySheet } from "@/components/product/PriceHistorySheet";

import { usablePhoto } from "@/lib/image";

type Schemas = import("@/lib/api-types").components["schemas"];
type Product = Pick<Schemas["ProductOut"], "id" | "canonical_name" | "image_url" | "review_count" | "line">;
type Card = Schemas["SearchCardOut"];
type Match = { product: Product; card: Card | null };

const n = (v: number) => v.toLocaleString("en-PH");
const peso = (v: string | number) => `₱${Number(v).toLocaleString("en-PH", { maximumFractionDigits: 0 })}`;

function ago(isoDate: string, now: number): string {
  const days = Math.max(0, Math.floor((now - new Date(`${isoDate}T00:00:00+08:00`).getTime()) / 86_400_000));
  if (days === 0) return "today";
  if (days === 1) return "yesterday";
  if (days < 30) return `${days} days ago`;
  const months = Math.floor(days / 30);
  return months < 12 ? `${months} month${months === 1 ? "" : "s"} ago` : `${Math.floor(months / 12)} year${months < 24 ? "" : "s"} ago`;
}

function Thumb({ url, size }: { url: string | null | undefined; size: number }) {
  const src = usablePhoto(url ?? null);
  return (
    <span className="relative shrink-0 overflow-hidden rounded-[12px] bg-[var(--surface-app)]" style={{ width: size, height: size }}>
      {src ? <Image src={src} alt="" width={size} height={size} unoptimized className="size-full object-cover" /> : null}
    </span>
  );
}

/** Figma StatStack (7702:7205): the value in 16px Medium with a 16px glyph, the label in 10px Light. */
function Stat({ value, label, icon }: { value: string; label: string; icon?: React.ReactNode }) {
  return (
    <span className="flex min-w-0 flex-1 flex-col gap-[2px]">
      <span className="flex items-center gap-1 text-[16px] font-medium leading-normal [font-variant-numeric:tabular-nums]">
        {value}
        {icon}
      </span>
      <span className="text-[10px] font-light leading-normal">{label}</span>
    </span>
  );
}

/**
 * The search page's product bar and its Switch sheet (Figma ProductSwitcher
 * 7702:7501 in Screen/Search/Reviews 7693:7336 and Screen/Search/Questions
 * 7718:12930, sheet 7708:8117; read live 2026-10-05): the product the search
 * names, at a glance, and the other products it matches. Picking one reloads
 * the page on it (`product=` in the URL).
 *
 *   card    white, radius 16, 16px in; no shadow
 *   bar     a 60px photo at radius 12, 12px to the name in 14px Medium; under
 *           it the ProductLink tools (a 16px glyph and a 10px Light label);
 *           the orange Switch pill (12px, 12/8px in, a 12px caret) at the right
 *   stats   24px under the bar, three equal StatStacks 12px apart
 *
 * Tools: "Price History" opens the shared Price History sheet (read on first
 * open). The frame's "3D Model" is not drawn: no product carries one (owner
 * rule — do not build 3D).
 */
export function SearchProductBar({
  mode,
  chosen,
  matches,
  query,
  baseQuery,
  now,
}: {
  mode: "reviews" | "questions";
  chosen: Match;
  matches: Match[];
  query: string;
  /** The page's query string without `product`, to which a pick is appended. */
  baseQuery: string;
  now: number;
}) {
  const [open, setOpen] = useState(false);
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);
  const c = chosen.card;
  const name = chosen.product.canonical_name ?? "This product";
  const href = (id: string) => `/search?${baseQuery}${baseQuery ? "&" : ""}product=${id}`;

  return (
    <section aria-label="Product" data-testid="search-product-bar" className="mx-4 rounded-[16px] bg-[var(--surface-card)] p-4 md:mx-0">
      <div className="flex items-center gap-3">
        <Thumb url={chosen.product.image_url} size={60} />
        <div className="flex min-w-0 flex-1 flex-col gap-[2px]">
          <p className="text-[14px] font-medium leading-normal [overflow-wrap:anywhere]">{name}</p>
          <div className="flex items-start gap-3">
            <PriceHistorySheet
              productId={chosen.product.id}
              productName={chosen.product.canonical_name ?? null}
              triggerClassName="flex cursor-pointer items-center gap-1 rounded-full text-[10px] font-light leading-normal hover:underline focus-visible:outline focus-visible:outline-2 focus-visible:outline-[var(--accent-primary)]"
              triggerContent={
                <>
                  <ChartLine size={16} aria-hidden="true" /> Price History
                </>
              }
            />
          </div>
        </div>
        {matches.length > 1 ? (
          <button
            type="button"
            onClick={() => setOpen(true)}
            aria-haspopup="dialog"
            className="flex shrink-0 cursor-pointer items-center gap-1 rounded-full bg-[var(--accent-primary)] py-[6px] pl-3 pr-2 text-[12px] leading-normal text-[var(--text-on-brand)]"
          >
            Switch <CaretDown size={12} aria-hidden="true" />
          </button>
        ) : null}
      </div>
      {c ? (
        <div className="mt-6 flex items-center gap-3">
          {mode === "reviews" ? (
            <>
              <Stat value={Number(c.median_rating).toFixed(1)} label={`across ${n(c.review_count)} review${c.review_count === 1 ? "" : "s"}`} icon={<Star size={16} weight="fill" className="text-[var(--accent-success)]" />} />
              <Stat value={c.recommend_pct === null || c.recommend_pct === undefined ? "—" : `${c.recommend_pct}%`} label="recommend it" icon={<Check size={16} weight="bold" className="text-[var(--accent-success)]" />} />
              <Stat value={c.latest_price ? peso(c.latest_price) : "—"} label={c.latest_price_on ? ago(c.latest_price_on, now) : "no price yet"} />
            </>
          ) : (
            <>
              <Stat value={n(c.best_answers)} label="best answers" icon={<Check size={16} weight="bold" className="text-[var(--accent-success)]" />} />
              <Stat value={n(c.unanswered)} label="unanswered" icon={<QuestionIcon size={16} weight="bold" className="text-[var(--accent-primary)]" />} />
              <Stat value={n(c.active_now)} label="active now" icon={<span className="size-[6px] rounded-full bg-[var(--accent-success)]" aria-hidden />} />
            </>
          )}
        </div>
      ) : null}

      {open ? (
        <div className="fixed inset-0 z-50 flex items-end justify-center bg-black/30 md:items-center" onClick={() => setOpen(false)}>
          <div
            role="dialog"
            aria-modal="true"
            aria-label={`${matches.length} products match`}
            onClick={(e) => e.stopPropagation()}
            className="w-full max-w-[480px] rounded-t-[24px] bg-[var(--surface-card)] px-4 pb-6 pt-2 md:rounded-[24px]"
          >
            <span className="mx-auto mb-3 block h-1 w-9 rounded-full bg-[var(--line-hairline-10)] md:hidden" aria-hidden />
            <div className="flex items-start justify-between gap-3">
              <div>
                <p className="text-[18px] font-semibold">{matches.length} products match</p>
                <p className="mt-1 text-[13px] text-[var(--text-secondary)]">&ldquo;{query}&rdquo;</p>
              </div>
              <button type="button" aria-label="Close" onClick={() => setOpen(false)} className="hidden size-8 place-items-center rounded-full md:grid">
                <X size={16} />
              </button>
            </div>
            <ul className="mt-3 flex flex-col">
              {matches.map((m) => {
                const on = m.product.id === chosen.product.id;
                const mc = m.card;
                return (
                  <li key={m.product.id} className="border-b border-[var(--line-hairline-10)] last:border-b-0">
                    <Link href={href(m.product.id)} onClick={() => setOpen(false)} aria-current={on ? "true" : undefined} className="flex items-center gap-3 py-3">
                      <Thumb url={m.product.image_url} size={44} />
                      <span className="flex min-w-0 flex-1 flex-col gap-1">
                        <span className="truncate text-[15px]">{m.product.canonical_name ?? "Unnamed product"}</span>
                        <span className="text-[13px] text-[var(--text-secondary)]">
                          {mode === "reviews" || !mc ? (
                            `${n(m.product.review_count)} review${m.product.review_count === 1 ? "" : "s"}`
                          ) : (
                            <>
                              {n(mc.questions)} question{mc.questions === 1 ? "" : "s"} ·{" "}
                              {mc.unanswered ? <span className="text-[var(--accent-primary)]">{n(mc.unanswered)} waiting</span> : "all answered"}
                            </>
                          )}
                        </span>
                      </span>
                      {on ? <CheckCircle size={18} className="shrink-0" aria-label="Showing" /> : null}
                    </Link>
                  </li>
                );
              })}
            </ul>
          </div>
        </div>
      ) : null}
    </section>
  );
}
