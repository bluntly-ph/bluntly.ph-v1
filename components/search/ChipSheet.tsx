"use client";

import Image from "next/image";
import { useEffect, useId, useRef, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { Info } from "@phosphor-icons/react";

/**
 * The filter bottom sheet of the current search frames, built from FilterChip
 * pills rather than the retired radio sheet ("All filters" 1587:4658, kept in
 * FilterSheet.tsx for the store page's All filters).
 *
 *  Screen/Search/Reviews/Filters (7762:9999), "Sheet" 7762:10028:
 *    white, top radius 24, 12px top / 16px sides / 32px bottom, 20px between
 *    rows; a 40×4 #d9d9d9 handle; "Filters" 16px Medium with "Reset" 12px in
 *    brand at the right; each group a 12px blue label 10px over its chips;
 *    a 56px full-width brand pill (16px SemiBold) to apply.
 *  Sheet/Filter sellers (8462:36591), the later frame, tone="quiet":
 *    a 20px SlidersHorizontal before the title, "Reset" 12px Light in #737373,
 *    14px Medium ink group labels, 14px between rows and 24px at the bottom.
 *
 *  FilterChip (7808:9228 / 7808:9233): 7px × 14px around a 12px label, radius
 *  16, a 1px #d1d1d1 edge on white; chosen, the brand edge on #fbede3 with the
 *  label in brand Medium. StoreChip (7808:9238): 8px before a 20px logo at
 *  radius 5, 6px tall padding.
 *
 * The choice commits on the pill, as drawn ("Show 42 reviews"), and "Reset"
 * clears the sheet's choices without leaving it. Escape and the scrim close
 * it; the frames draw no close mark, so a screen reader gets one that is
 * visible only while it has focus. From `md` up, where no frame draws the
 * sheet, the same 390px panel is centred as a dialog.
 *
 * KEPT, NOT DRAWN: the ⓘ beside a group label. QA-053 (owner 2026-09-28) asks
 * that each filter say what it means; the button sits after the label and the
 * text opens under it.
 */

const FOCUS =
  "focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--accent-primary)]";

export function ChipSheet({
  title,
  icon,
  tone = "brand",
  submitLabel,
  onClose,
  onReset,
  onSubmit,
  children,
}: {
  title: string;
  /** Sheet/Filter sellers puts a 20px glyph before the title. */
  icon?: ReactNode;
  /** "quiet": Sheet/Filter sellers' grey Reset, ink labels and tighter rows. */
  tone?: "brand" | "quiet";
  submitLabel: string;
  onClose: () => void;
  onReset: () => void;
  onSubmit: () => void;
  children: ReactNode;
}) {
  const titleId = useId();
  const panelRef = useRef<HTMLDivElement | null>(null);
  const quiet = tone === "quiet";

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.preventDefault();
        onClose();
      }
    };
    document.addEventListener("keydown", onKey);
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const panel = panelRef.current;
    (panel?.querySelector<HTMLElement>("[aria-pressed='true']") ?? panel?.querySelector<HTMLElement>("[data-chip]"))?.focus();
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = previous;
    };
  }, [onClose]);

  return createPortal(
    <>
      {/* Pointer-only: keyboard users close with Escape or the focusable close. */}
      <div aria-hidden="true" onClick={onClose} data-sheet-scrim className="fixed inset-0 z-40 bg-[var(--overlay-scrim-40)]" />
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        className="fixed inset-x-0 bottom-0 z-50 mx-auto flex max-h-[85dvh] w-full max-w-[390px] flex-col rounded-t-[24px] bg-[var(--surface-card)] text-[var(--text-primary)] md:bottom-auto md:top-1/2 md:-translate-y-1/2 md:rounded-[24px]"
      >
        <form
          onSubmit={(e) => {
            e.preventDefault();
            onSubmit();
          }}
          className={`flex min-h-0 flex-1 flex-col px-4 pt-3 ${quiet ? "gap-[14px] pb-6" : "gap-5 pb-8"}`}
        >
          <div className={`flex shrink-0 justify-center ${quiet ? "pb-2" : ""}`}>
            <span aria-hidden="true" className="h-1 w-10 rounded-[2px] bg-[var(--base-gray-200)]" />
          </div>
          <div className={`flex shrink-0 items-center gap-2 ${quiet ? "pb-2" : "justify-between"}`}>
            {icon}
            <h2 id={titleId} className={`text-[16px] font-medium leading-normal ${quiet ? "min-w-0 flex-1" : ""}`}>
              {title}
            </h2>
            <button
              type="button"
              onClick={onClose}
              className={`sr-only cursor-pointer rounded-full px-2 text-[12px] focus:not-sr-only ${FOCUS}`}
            >
              Close
            </button>
            <button
              type="button"
              onClick={onReset}
              className={`-m-2 cursor-pointer rounded-full p-2 text-[12px] leading-normal ${
                quiet ? "font-light text-[var(--text-subtle)]" : "text-[var(--accent-primary)]"
              } ${FOCUS}`}
            >
              Reset
            </button>
          </div>

          <div className={`-mx-4 flex min-h-0 flex-1 flex-col overflow-y-auto px-4 ${quiet ? "gap-[14px]" : "gap-5"}`}>
            {children}
          </div>

          <button
            type="submit"
            className={`h-14 w-full shrink-0 cursor-pointer rounded-[var(--radius-pill)] bg-[var(--accent-primary)] px-6 text-[16px] font-semibold leading-6 text-[var(--text-on-brand)] transition-transform duration-[120ms] ease-[var(--ease-standard)] hover:bg-[var(--accent-primary-strong)] motion-safe:active:scale-[0.97] ${FOCUS}`}
          >
            {submitLabel}
          </button>
        </form>
      </div>
    </>,
    document.body,
  );
}

/** One labelled row of chips: Group/Rating (7762:10034), Chips/Profile (8462:36612). */
export function ChipGroup({
  label,
  info,
  tone = "brand",
  children,
}: {
  label: string;
  info?: string;
  tone?: "brand" | "quiet";
  children: ReactNode;
}) {
  const [showInfo, setShowInfo] = useState(false);
  const labelId = useId();
  const infoId = useId();
  const quiet = tone === "quiet";
  return (
    <div role="group" aria-labelledby={labelId} className={`flex shrink-0 flex-col ${quiet ? "gap-[14px]" : "gap-[10px]"}`}>
      <div className="flex items-center gap-1">
        <h3
          id={labelId}
          className={
            quiet
              ? "text-[14px] font-medium leading-5 text-[var(--text-primary)]"
              : "text-[12px] font-normal leading-normal text-[var(--accent-trust)]"
          }
        >
          {label}
        </h3>
        {info ? (
          <button
            type="button"
            aria-label={`About ${label.toLowerCase()}`}
            aria-expanded={showInfo}
            aria-controls={showInfo ? infoId : undefined}
            onClick={() => setShowInfo((v) => !v)}
            className={`-m-1 grid h-6 w-6 cursor-pointer place-items-center rounded-full text-[var(--line-hairline-30)] hover:text-[var(--text-secondary)] ${FOCUS}`}
          >
            <Info size={14} aria-hidden="true" />
          </button>
        ) : null}
      </div>
      {info && showInfo ? (
        <p id={infoId} className="-mt-1 text-[12px] font-light leading-[18px] text-[var(--text-secondary)]">
          {info}
        </p>
      ) : null}
      <div className="flex flex-wrap gap-2">{children}</div>
    </div>
  );
}

const CHIP_BASE = `inline-flex shrink-0 cursor-pointer items-center gap-[6px] whitespace-nowrap rounded-[16px] border text-[12px] leading-normal ${FOCUS}`;
const chipTone = (selected: boolean) =>
  selected
    ? "border-[var(--accent-primary)] bg-[var(--status-high-bg)] font-medium text-[var(--accent-primary)]"
    : "border-[var(--line-chip)] bg-[var(--surface-card)] font-normal text-[var(--text-primary)]";

/** FilterChip: one choice, pressed while it is part of the selection. */
export function Chip({
  label,
  selected,
  onToggle,
}: {
  label: string;
  selected: boolean;
  onToggle: () => void;
}) {
  return (
    <button
      type="button"
      data-chip
      aria-pressed={selected}
      onClick={onToggle}
      className={`${CHIP_BASE} px-[14px] py-[7px] ${chipTone(selected)}`}
    >
      {label}
    </button>
  );
}

// The logos as the component places them: Lazada fills its 20px slot; the
// Shopee artwork is cropped in by the frame's own offsets (image 7, 7808:9240).
const STORE_LOGO = {
  shopee: { src: "/marketplaces/shopee.png", label: "Shopee", crop: "left-[-11.57%] top-[-13.35%] h-[122.96%] w-[121.44%]" },
  lazada: { src: "/marketplaces/lazada.png", label: "Lazada", crop: "inset-0" },
} as const;

/** StoreChip (7808:9238): a marketplace with its logo. */
export function StoreChip({
  store,
  selected,
  onToggle,
}: {
  store: keyof typeof STORE_LOGO;
  selected: boolean;
  onToggle: () => void;
}) {
  const { src, label, crop } = STORE_LOGO[store];
  return (
    <button
      type="button"
      data-chip
      aria-pressed={selected}
      onClick={onToggle}
      className={`${CHIP_BASE} py-[6px] pl-2 pr-[14px] ${chipTone(selected)}`}
    >
      <span aria-hidden="true" className="relative size-5 shrink-0 overflow-hidden rounded-[5px]">
        <span className={`absolute ${crop}`}>
          <Image src={src} alt="" fill sizes="25px" className="object-cover" />
        </span>
      </span>
      {label}
    </button>
  );
}
