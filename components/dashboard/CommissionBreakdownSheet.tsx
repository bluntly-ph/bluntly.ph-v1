"use client";

import { useEffect, useId, useRef, useState } from "react";
import { CaretRight, Info, X } from "@phosphor-icons/react/dist/ssr";

import { completedSpan, counted, peso, pesoWhole } from "@/components/dashboard/contributor-model";
import type { CommissionBreakdown } from "@/lib/dashboard";

/**
 * "Commission breakdown" — Figma Proposals › 35 (9057:46463): the ⓘ on "Where
 * the commission went" (Card/Commission 9057:46610) opens it as an overlay
 * (prototype 9177:53790: move in from the bottom, 300 ms, ease out; the scrim
 * 9177:53791 closes it). "· opened" 9057:46788 is the first screen, "· full
 * content (scrolls)" 9057:47088 everything below it.
 *
 *   sheet     white, hairline edge, top radius 24, 12 / 16 / 32 px in, 20 px
 *             between groups, its top 80 px below the screen's (it scrolls
 *             inside itself); a 40x4 hairline handle
 *   header    16 SemiBold title over the 12 px span of completed orders; a
 *             44 px close with an 18 px X
 *   groups    a 12 Medium label at 70%, then rows: 14 label (70%) over a 12
 *             meta line, the amount 14 Medium at the right
 *   net       a hairline above, 14 SemiBold both sides, 12 px rows
 *   split     8 px dots in the card's colours; "You · 30%" SemiBold with a
 *             16 SemiBold amount; Pending in a #f2f2f2 12 px-radius note
 *   tiles     Shopee and Lazada side by side, #f2f2f2, radius 12, 12 px in
 *   products  the top five by net commission with hairlines between, then a
 *             44 px "See all N products"
 *
 * Closes on ✕, a tap on the scrim, Escape, or a swipe down on the handle or
 * header. Every figure is the API's (`commission_breakdown`); nothing here
 * adds money up.
 */

const TOP = 5;

export function CommissionBreakdownSheet({ breakdown }: { breakdown: CommissionBreakdown }) {
  const dialogRef = useRef<HTMLDialogElement>(null);
  const sheetRef = useRef<HTMLDivElement>(null);
  const drag = useRef<{ y: number; t: number } | null>(null);
  const titleId = useId();
  const [isOpen, setIsOpen] = useState(false);
  const [all, setAll] = useState(false);
  const [offset, setOffset] = useState(0);

  useEffect(() => {
    const el = dialogRef.current;
    if (!el) return;
    const onClose = () => {
      setIsOpen(false);
      setAll(false);
      setOffset(0);
    };
    el.addEventListener("close", onClose);
    return () => el.removeEventListener("close", onClose);
  }, []);

  useEffect(() => {
    const el = dialogRef.current;
    if (isOpen && el && !el.open) el.showModal();
  }, [isOpen]);

  const close = () => dialogRef.current?.close();

  // Swipe down: the sheet follows the finger; past a quarter of its height, or
  // a quick flick, it closes; otherwise it springs back.
  function onPointerDown(e: React.PointerEvent) {
    // Capturing the pointer would take the click away from the close button.
    if (e.button !== 0 || (e.target as HTMLElement).closest("button")) return;
    drag.current = { y: e.clientY, t: e.timeStamp };
    (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
  }
  function onPointerMove(e: React.PointerEvent) {
    if (drag.current) setOffset(Math.max(0, e.clientY - drag.current.y));
  }
  function onPointerUp(e: React.PointerEvent) {
    const start = drag.current;
    drag.current = null;
    if (!start) return;
    const dy = Math.max(0, e.clientY - start.y);
    const fast = dy > 40 && dy / Math.max(e.timeStamp - start.t, 1) > 0.6;
    const height = sheetRef.current?.offsetHeight ?? 600;
    if (dy > height / 4 || fast) close();
    else setOffset(0);
  }

  const b = breakdown;
  const net = Number(b.net_commission);
  const pct = (v: string, fallback: number) => (net > 0 ? Math.round((Number(v) / net) * 100) : fallback);
  const span = completedSpan(b.first_completed ?? null, b.last_completed ?? null);
  const shown = all ? b.products : b.products.slice(0, TOP);
  const empty = b.items === 0 && b.pending_orders === 0;

  return (
    <>
      {/* The 32 px ⓘ of Card/Commission inside a 44 px target (dev note). */}
      <button
        type="button"
        onClick={() => setIsOpen(true)}
        aria-haspopup="dialog"
        aria-label="Commission breakdown"
        className="-m-1.5 grid size-11 shrink-0 cursor-pointer place-items-center rounded-full focus-visible:outline focus-visible:outline-2 focus-visible:outline-[var(--accent-primary)]"
      >
        <span className="grid size-8 place-items-center rounded-full bg-[var(--surface-app)]">
          <Info size={16} aria-hidden="true" />
        </span>
      </button>
      <dialog
        ref={dialogRef}
        aria-labelledby={titleId}
        onClick={(e) => {
          if (e.target === dialogRef.current) close();
        }}
        className="mx-auto mb-0 mt-auto w-full max-w-full overflow-visible bg-transparent p-0 text-[var(--text-primary)] backdrop:bg-[var(--overlay-scrim-32)] md:max-w-[390px]"
      >
        {isOpen ? (
          <div
            ref={sheetRef}
            style={offset ? { transform: `translateY(${offset}px)` } : undefined}
            className={`animate-sheet-up flex max-h-[calc(100dvh-80px)] flex-col rounded-t-[24px] border border-b-0 border-[var(--line-hairline-10)] bg-[var(--surface-card)] ${offset ? "" : "transition-transform duration-200 ease-[var(--ease-standard)]"}`}
          >
            <div
              onPointerDown={onPointerDown}
              onPointerMove={onPointerMove}
              onPointerUp={onPointerUp}
              onPointerCancel={() => {
                drag.current = null;
                setOffset(0);
              }}
              className="flex shrink-0 touch-none flex-col gap-5 px-4 pt-3"
            >
              <div className="flex justify-center" aria-hidden="true">
                <span className="h-1 w-10 rounded-[2px] bg-[var(--line-hairline-10)]" />
              </div>
              <div className="flex items-center">
                <div className="flex min-w-0 flex-1 flex-col gap-0.5 leading-normal">
                  <h2 id={titleId} className="text-[16px] font-semibold">
                    Commission breakdown
                  </h2>
                  {span ? <p className="text-[12px] text-[var(--text-secondary)]">{span}</p> : null}
                </div>
                <button
                  type="button"
                  onClick={close}
                  aria-label="Close commission breakdown"
                  className="grid size-11 shrink-0 cursor-pointer place-items-center rounded-full hover:bg-[var(--line-hairline-10)] focus-visible:outline focus-visible:outline-2 focus-visible:outline-[var(--accent-primary)]"
                >
                  <X size={18} aria-hidden="true" />
                </button>
              </div>
            </div>

            <div className="flex min-h-0 flex-col gap-5 overflow-y-auto overscroll-contain px-4 pb-8 pt-5">
              {empty ? (
                <p className="text-[14px] leading-normal text-[var(--text-secondary)]">
                  No completed orders through your links yet. When a marketplace reports one, it shows here from gross sales to what you earned.
                </p>
              ) : null}

              <Group label="Gross to net">
                <Row label="Gross sales" meta={salesMeta(b)} amount={peso(b.gross_sales)} />
                <Row label="Gross commission" meta="Remitted by marketplace" amount={peso(b.gross_commission)} />
                <Row
                  label="Reversals"
                  meta={`${b.cancelled_items.toLocaleString("en-US")} cancelled · ${b.refunded_items.toLocaleString("en-US")} refunded`}
                  amount={peso(b.reversals, true)}
                />
                <div className="h-px w-full bg-[var(--line-hairline-10)]" />
                <div className="flex items-center gap-2 py-3 text-[14px] font-semibold leading-normal">
                  <span className="min-w-0 flex-1">Net commission</span>
                  <span className="shrink-0 tabular-nums">{peso(b.net_commission)}</span>
                </div>
              </Group>

              <Group label="Split">
                <ul className="flex flex-col">
                  <SplitRow colour="var(--accent-primary)" label={`You · ${pct(b.you, 30)}%`} amount={peso(b.you)} lead />
                  <SplitRow colour="var(--chart-honesty-fund)" label={`Honesty Fund · ${pct(b.honesty_fund, 30)}%`} amount={peso(b.honesty_fund)} />
                  <SplitRow colour="var(--base-gray-200)" label={`Bluntly · ${pct(b.bluntly, 40)}%`} amount={peso(b.bluntly)} />
                </ul>
                {Number(b.credited) !== Number(b.you) ? (
                  <p className="pb-2 text-[12px] leading-normal text-[var(--text-secondary)]">
                    {peso(b.credited)} of your share is credited to your wallet. The rest is from sales the marketplace reported that
                    aren&rsquo;t tied to one of your reviews yet.
                  </p>
                ) : null}
                <p className="flex items-center gap-2 rounded-[12px] bg-[var(--surface-app)] px-3 py-2.5 text-[14px] leading-normal">
                  <span className="min-w-0 flex-1 text-[var(--text-secondary)]">
                    Pending<span className="sr-only">, not counted yet</span>
                  </span>
                  <span className="shrink-0 font-medium tabular-nums">
                    {peso(b.pending_commission)} · {counted(b.pending_orders, "order")}
                  </span>
                </p>
              </Group>

              <Group label="By marketplace">
                <ul className="flex gap-2">
                  {b.marketplaces.map((m) => (
                    <li key={m.platform} className="flex min-w-0 flex-1 flex-col gap-0.5 rounded-[12px] bg-[var(--surface-app)] p-3 leading-normal">
                      <span className="text-[12px] text-[var(--text-secondary)]">{MARKETPLACE[m.platform] ?? m.platform}</span>
                      <span className="text-[16px] font-semibold tabular-nums">{peso(m.gross_commission)}</span>
                      <span className="text-[12px] text-[var(--text-secondary)]">{counted(m.orders, "order")}</span>
                    </li>
                  ))}
                </ul>
              </Group>

              {b.products.length ? (
                <Group label="By product · net commission">
                  <ul className="flex flex-col">
                    {shown.map((p, i) => (
                      <li
                        key={p.product_id ?? `${p.name}-${i}`}
                        className={`flex items-center gap-2 py-2.5 leading-normal ${i > 0 ? "border-t border-[var(--line-hairline-10)]" : ""}`}
                      >
                        <span className="flex min-w-0 flex-1 flex-col gap-0.5">
                          <span title={p.name} className="line-clamp-2 break-words text-[14px] [overflow-wrap:anywhere]">
                            {p.name}
                          </span>
                          <span className="text-[12px] text-[var(--text-secondary)]">
                            {counted(p.orders, "order")} · {p.sales == null ? "sales not reported" : `${pesoWhole(p.sales)} sales`}
                          </span>
                        </span>
                        <span className="shrink-0 text-[14px] font-medium tabular-nums">{peso(p.net_commission)}</span>
                      </li>
                    ))}
                  </ul>
                  {b.products.length > TOP ? (
                    <button
                      type="button"
                      onClick={() => setAll((v) => !v)}
                      aria-expanded={all}
                      className="flex h-11 w-fit cursor-pointer items-center gap-1 text-[14px] font-medium focus-visible:outline focus-visible:outline-2 focus-visible:outline-[var(--accent-primary)]"
                    >
                      {all ? `Show the top ${TOP}` : `See all ${counted(b.products.length, "product")}`}
                      <CaretRight size={14} aria-hidden="true" className={all ? "-rotate-90" : ""} />
                    </button>
                  ) : null}
                </Group>
              ) : null}
            </div>
          </div>
        ) : null}
      </dialog>
    </>
  );
}

/** "91 orders · 123 items", plus the orders that report no sales figure (ledger entries). */
function salesMeta(b: CommissionBreakdown): string {
  const line = `${counted(b.sales_orders ?? b.orders, "order")} · ${counted(b.sales_items ?? b.items, "item")}`;
  const missing = b.orders - (b.sales_orders ?? b.orders);
  return missing > 0 ? `${line} · ${counted(missing, "order")} without a sales figure` : line;
}

const MARKETPLACE: Record<string, string> = { shopee: "Shopee", lazada: "Lazada", amazon: "Amazon", other: "Other" };

function Group({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <section aria-label={label} className="flex flex-col">
      <h3 className="pb-1 text-[12px] font-medium leading-normal text-[var(--text-secondary)]">{label}</h3>
      {children}
    </section>
  );
}

function Row({ label, meta, amount }: { label: string; meta: string; amount: string }) {
  return (
    <div className="flex items-center gap-2 py-2 leading-normal">
      <span className="flex min-w-0 flex-1 flex-col gap-0.5 text-[var(--text-secondary)]">
        <span className="text-[14px]">{label}</span>
        <span className="text-[12px]">{meta}</span>
      </span>
      <span className="shrink-0 text-[14px] font-medium tabular-nums">{amount}</span>
    </div>
  );
}

function SplitRow({ colour, label, amount, lead = false }: { colour: string; label: string; amount: string; lead?: boolean }) {
  return (
    <li className="flex items-center gap-2 py-2 leading-normal">
      <span aria-hidden="true" className="size-2 shrink-0 rounded-full" style={{ background: colour }} />
      <span className={`min-w-0 flex-1 text-[14px] ${lead ? "font-semibold" : "text-[var(--text-secondary)]"}`}>{label}</span>
      <span className={`shrink-0 tabular-nums ${lead ? "text-[16px] font-semibold" : "text-[14px] font-medium"}`}>{amount}</span>
    </li>
  );
}
