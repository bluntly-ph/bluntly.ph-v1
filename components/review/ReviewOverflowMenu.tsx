"use client";

import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { DotsThree, Flag, LinkSimple, ShieldWarning, Trash } from "@phosphor-icons/react";

import { DeleteReviewDialog } from "@/components/review/DeleteReviewDialog";
import { TakedownReviewDialog } from "@/components/review/TakedownReviewDialog";
import { markInteraction } from "@/lib/reading-telemetry-events";

/**
 * The three-dot menu in the review top bar (BUG-012).
 *
 * Copy-link rather than the full share sheet: the share control in the action
 * row below already offers `navigator.share`, and two things opening an OS sheet
 * from one screen is confusing. Report links down to the existing dialog rather
 * than duplicating it — one report path, one set of rules.
 *
 * The author also finds Delete here (owner decision 2026-09-28): it had lived
 * only in the thread panel at the foot of the page, which is how the team came
 * to report that members "have no practical way to delete their own reviews".
 * The server still decides who may delete; this only offers it to the author.
 */
export function ReviewOverflowMenu({
  title,
  reviewId,
  canReport,
  onBar = false,
  inline = false,
  canDelete = false,
  isRoot = true,
  canTakeDown = false,
}: {
  title: string;
  reviewId: string;
  canReport: boolean;
  /** The viewer wrote this review. */
  canDelete?: boolean;
  /** The original review (deleting it takes the thread) rather than an update. */
  isRoot?: boolean;
  /** Staff viewer on a public review they did not write: offer a takedown. */
  canTakeDown?: boolean;
  /** Sitting on the review's orange nav bar, so the trigger is white. */
  onBar?: boolean;
  /**
   * QA-059 (retest, 2026-09-24: "the three-dot menu continues to cover part
   * of the product title"): from `md` the two actions sit in the author line
   * as plain text buttons, so nothing pops over the headline at all.
   */
  inline?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const [copied, setCopied] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [takingDown, setTakingDown] = useState(false);
  const takedownDialog = canTakeDown ? (
    <TakedownReviewDialog reviewId={reviewId} open={takingDown} onClose={() => setTakingDown(false)} />
  ) : null;
  const deleteDialog = canDelete ? (
    <DeleteReviewDialog
      reviewId={reviewId}
      isRoot={isRoot}
      open={deleting}
      onClose={() => setDeleting(false)}
    />
  ) : null;
  const root = useRef<HTMLDivElement>(null);
  const menu = useRef<HTMLDivElement>(null);
  // QA-059: where the menu opens, decided against the viewport when it opens.
  // It was always anchored to the trigger's RIGHT edge, which suits the phone
  // bar (trigger at the right) but from md the trigger heads the left of the
  // headline column, so the 208px menu hung leftward out of the column and
  // down across the title. Now it opens toward the side with room, and upward
  // when there is not room below.
  const [place, setPlace] = useState<{ x: "start" | "end"; y: "below" | "above" }>({
    x: "end",
    y: "below",
  });

  useLayoutEffect(() => {
    if (!open || !root.current || !menu.current) return;
    const trigger = root.current.getBoundingClientRect();
    const box = menu.current.getBoundingClientRect();
    const roomRight = window.innerWidth - trigger.left;
    const roomLeft = trigger.right;
    const x = roomLeft >= box.width + 8 ? "end" : roomRight >= box.width + 8 ? "start" : "end";
    const roomBelow = window.innerHeight - trigger.bottom;
    const y = roomBelow >= box.height + 8 || roomBelow >= trigger.top ? "below" : "above";
    // Measuring needs the menu on screen, so this settles in the same frame.
    setPlace((p) => (p.x === x && p.y === y ? p : { x, y }));
  }, [open]);

  // Dismiss on outside click and on Escape — a menu you can only close by
  // picking something from it is a trap.
  useEffect(() => {
    if (!open) return;
    function onPointerDown(event: MouseEvent) {
      if (!root.current?.contains(event.target as Node)) setOpen(false);
    }
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") setOpen(false);
    }
    // QA-059: the trigger sits in a sticky header, so an open menu stayed put
    // while the page scrolled under it and ended up over the title and the
    // "Ask a question" button. Scrolling the page closes it.
    function onScroll() {
      setOpen(false);
    }
    document.addEventListener("mousedown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => {
      document.removeEventListener("mousedown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
      window.removeEventListener("scroll", onScroll);
    };
  }, [open]);

  async function copyLink() {
    try {
      // The review's own address, not whatever query or fragment the reader's
      // URL carries (the same rule as the share sheet).
      await navigator.clipboard.writeText(new URL(`/reviews/${reviewId}`, window.location.origin).toString());
      setCopied(true);
      // A second surface for the same outcome as ShareButton's clipboard
      // fallback — same "share" marker; the accumulator keeps only whichever
      // fires first.
      markInteraction(reviewId, "share");
      setTimeout(() => setCopied(false), 2000);
    } catch {
      /* Clipboard denied — the visible label simply doesn't change. */
    }
    setOpen(false);
  }

  if (inline) {
    const INLINE =
      "inline-flex min-h-8 cursor-pointer items-center gap-1 rounded-[16px] px-2 text-[12px] font-light leading-none text-[var(--text-secondary)] hover:bg-[var(--line-hairline-10)] hover:text-[var(--text-primary)] focus-visible:outline focus-visible:outline-2 focus-visible:outline-[var(--accent-primary)]";
    return (
      <div className="flex shrink-0 items-center gap-1">
        <button type="button" onClick={copyLink} className={INLINE}>
          <LinkSimple size={16} aria-hidden="true" />
          {copied ? "Copied" : "Copy link"}
        </button>
        {canReport ? (
          <button
            type="button"
            onClick={() => document.getElementById(`report-trigger-${reviewId}`)?.click()}
            className={INLINE}
          >
            <Flag size={16} aria-hidden="true" />
            Report
          </button>
        ) : null}
        {canTakeDown ? (
          <button type="button" onClick={() => setTakingDown(true)} className={INLINE}>
            <ShieldWarning size={16} aria-hidden="true" />
            Take down
          </button>
        ) : null}
        {canDelete ? (
          <button type="button" onClick={() => setDeleting(true)} className={`${INLINE} hover:text-[var(--accent-danger)]`}>
            <Trash size={16} aria-hidden="true" />
            {isRoot ? "Delete review" : "Delete update"}
          </button>
        ) : null}
        <span aria-live="polite" className="sr-only">
          {copied ? `Link to ${title} copied` : ""}
        </span>
        {deleteDialog}
        {takedownDialog}
      </div>
    );
  }

  return (
    <div ref={root} className="relative">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-label="More options"
        aria-expanded={open}
        aria-haspopup="menu"
        className={
          onBar
            ? "grid h-10 w-10 place-items-center rounded-full text-[var(--text-on-brand)] hover:bg-white/15"
            : "grid h-9 w-9 place-items-center rounded-full text-[var(--text-secondary)] hover:bg-[var(--line-hairline-10)] hover:text-[var(--text-primary)]"
        }
      >
        {/* The bar draws Phosphor DotsThree at 28px (Review page 4218:1196). */}
        <DotsThree size={onBar ? 28 : 22} weight={onBar ? "regular" : "bold"} />
      </button>

      {open ? (
        <div
          ref={menu}
          role="menu"
          data-placement={`${place.y}-${place.x}`}
          className={`absolute z-20 w-52 max-w-[calc(100vw-16px)] overflow-hidden rounded-[var(--radius-sm)] bg-[var(--surface-card)] py-1 shadow-[var(--shadow-card)] ${
            place.x === "end" ? "right-0" : "left-0"
          } ${place.y === "below" ? "top-full mt-1" : "bottom-full mb-1"}`}
        >
          <button
            type="button"
            role="menuitem"
            onClick={copyLink}
            className="flex w-full items-center gap-2 px-4 py-2.5 text-left text-[13px] text-[var(--text-primary)] hover:bg-[var(--line-hairline-10)]"
          >
            <LinkSimple size={16} />
            Copy link
          </button>
          {canReport ? (
            <button
              type="button"
              role="menuitem"
              onClick={() => {
                setOpen(false);
                // Drives the existing dialog rather than reimplementing it, so
                // there is one report path with one copy of the reasons and the
                // self-report rule.
                document
                  .getElementById(`report-trigger-${reviewId}`)
                  ?.click();
              }}
              className="flex w-full items-center gap-2 px-4 py-2.5 text-left text-[13px] text-[var(--text-primary)] hover:bg-[var(--line-hairline-10)]"
            >
              <Flag size={16} />
              Report this review
            </button>
          ) : null}
          {canTakeDown ? (
            <button
              type="button"
              role="menuitem"
              onClick={() => {
                setOpen(false);
                setTakingDown(true);
              }}
              className="flex w-full items-center gap-2 px-4 py-2.5 text-left text-[13px] text-[var(--text-primary)] hover:bg-[var(--line-hairline-10)]"
            >
              <ShieldWarning size={16} />
              Take down (staff)
            </button>
          ) : null}
          {canDelete ? (
            <button
              type="button"
              role="menuitem"
              onClick={() => {
                setOpen(false);
                setDeleting(true);
              }}
              className="flex w-full items-center gap-2 px-4 py-2.5 text-left text-[13px] text-[var(--accent-danger)] hover:bg-[var(--line-hairline-10)]"
            >
              <Trash size={16} />
              {isRoot ? "Delete review" : "Delete update"}
            </button>
          ) : null}
        </div>
      ) : null}
      {deleteDialog}
      {takedownDialog}

      <span aria-live="polite" className="sr-only">
        {copied ? `Link to ${title} copied` : ""}
      </span>
    </div>
  );
}

export default ReviewOverflowMenu;
