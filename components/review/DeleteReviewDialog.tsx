"use client";

import { useRouter } from "next/navigation";
import { useEffect, useId, useRef, useState } from "react";
import { Trash, X } from "@phosphor-icons/react";

/**
 * The author deletes their own review (Business Rules §4, owner decision
 * 2026-09-28: "users still have no practical way to delete their own reviews").
 *
 * One dialog, opened from every place an author meets their review: the ⋯
 * menu and the author row on the review page, the thread panel under it, and
 * each card on /profile. It asks for the word "delete" typed out whatever is
 * being deleted — the original takes the whole thread with it and cannot be
 * undone, and an explicit, typed confirmation is the owner's requirement.
 *
 * The server decides everything that matters: that the caller is the author
 * (403 otherwise), that deleting the original ends the thread and every future
 * earning, that money already paid is never clawed back and leaves only the
 * product's aggregate "removed by its author" trace. This component only asks.
 *
 * NO FIGMA FRAME: set as the report sheet is (radius 20, page colour, a 16px
 * Bold title over a hairline, a danger pill), so it reads as the same product.
 */

const DELETE_WORD = "delete";
const FOCUS =
  "focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--accent-primary)]";
const PILL = `h-[38px] cursor-pointer rounded-[20px] px-3 text-[16px] leading-none tracking-[0.8px] text-[var(--text-on-brand)] ${FOCUS}`;

export function DeleteReviewDialog({
  reviewId,
  isRoot,
  open,
  onClose,
  redirectTo = "/profile?deleted=1",
}: {
  reviewId: string;
  /** Unknown (a card that does not say) is treated as the original: the stronger warning. */
  isRoot: boolean | null;
  open: boolean;
  onClose: () => void;
  redirectTo?: string | null;
}) {
  const router = useRouter();
  const dialogRef = useRef<HTMLDialogElement>(null);
  const titleId = useId();
  const inputId = useId();
  const [typed, setTyped] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const wholeThread = isRoot !== false;

  useEffect(() => {
    const el = dialogRef.current;
    if (!el) return;
    if (open && !el.open) el.showModal();
    if (!open && el.open) el.close();
  }, [open]);

  useEffect(() => {
    const el = dialogRef.current;
    if (!el) return;
    const handle = () => {
      setTyped("");
      setError(null);
      onClose();
    };
    el.addEventListener("close", handle);
    return () => el.removeEventListener("close", handle);
  }, [onClose]);

  async function confirm(event: React.FormEvent) {
    event.preventDefault();
    if (busy) return;
    if (typed.trim().toLowerCase() !== DELETE_WORD) {
      setError(`Type "${DELETE_WORD}" to confirm.`);
      return;
    }
    setBusy(true);
    setError(null);
    try {
      // The confirmation parameter is what the API requires to take a whole
      // thread; for an update entry it is simply ignored.
      const res = await fetch(`/api/bff/api/v1/reviews/${encodeURIComponent(reviewId)}?confirm=delete-thread`, {
        method: "DELETE",
      });
      if (!res.ok) {
        const problem = (await res.json().catch(() => ({}))) as { detail?: string };
        setError(problem.detail ?? "Couldn't delete this review.");
        return;
      }
      dialogRef.current?.close();
      if (redirectTo) router.push(redirectTo);
      router.refresh();
    } catch {
      setError("Couldn't reach the server.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <dialog
      ref={dialogRef}
      aria-labelledby={titleId}
      data-testid="delete-review-dialog"
      className="m-auto max-h-[90dvh] w-[min(390px,calc(100vw-2rem))] overflow-y-auto rounded-[20px] bg-[var(--surface-app)] p-0 text-[var(--text-primary)] shadow-[var(--shadow-sheet)] backdrop:bg-[var(--overlay-scrim-25)]"
    >
      <div className="flex items-start gap-2 px-6 pt-6">
        <Trash size={20} aria-hidden="true" className="shrink-0 text-[var(--accent-danger)]" />
        <h2 id={titleId} className="mt-0.5 min-w-0 flex-1 text-[16px] font-bold leading-none">
          {wholeThread ? "Delete your review?" : "Delete this update?"}
        </h2>
        <button
          type="button"
          onClick={() => dialogRef.current?.close()}
          aria-label="Close"
          className={`-my-2 -mr-2 grid h-11 w-11 shrink-0 cursor-pointer place-items-center rounded-full hover:bg-[var(--line-hairline-10)] ${FOCUS}`}
        >
          <X size={28} aria-hidden="true" />
        </button>
      </div>
      <hr className="mx-6 mt-[22px] border-0 border-t border-[var(--line-hairline-30)]" />
      <form onSubmit={confirm} className="px-6 pb-8 pt-[15px]">
        <ul className="list-disc space-y-1.5 pl-5 text-[14px] leading-[21px]">
          {wholeThread ? (
            <>
              <li>The whole review is removed, including every update you added to it.</li>
              <li>It stops earning straight away, and its affiliate link is switched off.</li>
              <li>Money you were already paid stays yours; nothing is taken back.</li>
              <li>This can&rsquo;t be undone.</li>
            </>
          ) : (
            <>
              <li>Only this update is removed; your original review and other updates stay.</li>
              <li>The latest remaining entry becomes the one that counts.</li>
              <li>This can&rsquo;t be undone.</li>
            </>
          )}
        </ul>
        <label htmlFor={inputId} className="mt-6 block text-[14px] font-semibold leading-none">
          Type &ldquo;{DELETE_WORD}&rdquo; to confirm
        </label>
        <input
          id={inputId}
          value={typed}
          onChange={(e) => setTyped(e.target.value)}
          autoComplete="off"
          autoCapitalize="none"
          spellCheck={false}
          className="mt-3 block h-11 w-full rounded-[16px] border border-transparent bg-[var(--surface-card)] px-[15px] text-[14px] shadow-[var(--shadow-card)] outline-none focus-visible:border-[var(--accent-primary)]"
        />
        {error ? (
          <p role="alert" className="mt-3 text-[12px] leading-[18px] text-[var(--accent-danger)]">
            {error}
          </p>
        ) : null}
        <div className="mt-[38px] flex items-center justify-between">
          <button
            type="button"
            onClick={() => dialogRef.current?.close()}
            className={`cursor-pointer text-[16px] leading-none tracking-[0.8px] text-[var(--text-primary)] ${FOCUS}`}
          >
            Keep it
          </button>
          <button
            type="submit"
            disabled={busy || typed.trim().toLowerCase() !== DELETE_WORD}
            className={`${PILL} bg-[var(--accent-danger)] disabled:cursor-not-allowed disabled:bg-[var(--disabled-surface)] disabled:text-[var(--disabled-text)]`}
          >
            {busy ? "Deleting…" : wholeThread ? "Delete review" : "Delete update"}
          </button>
        </div>
      </form>
    </dialog>
  );
}

/** A trigger + dialog pair, for places that just need a Delete button. */
export function DeleteReviewButton({
  reviewId,
  isRoot = null,
  className,
  label = "Delete",
  redirectTo,
}: {
  reviewId: string;
  isRoot?: boolean | null;
  className?: string;
  label?: string;
  redirectTo?: string | null;
}) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        className={
          className ??
          `inline-flex h-8 cursor-pointer items-center gap-1 rounded-[20px] border border-[rgba(32,32,32,0.3)] px-[11px] text-[12px] leading-none text-[var(--text-primary)] hover:border-[var(--accent-danger)] hover:text-[var(--accent-danger)] ${FOCUS}`
        }
      >
        <Trash size={16} aria-hidden="true" />
        {label}
      </button>
      <DeleteReviewDialog
        reviewId={reviewId}
        isRoot={isRoot}
        open={open}
        onClose={() => setOpen(false)}
        redirectTo={redirectTo}
      />
    </>
  );
}
