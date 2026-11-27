"use client";

import { useRouter } from "next/navigation";
import { useEffect, useId, useRef, useState } from "react";
import { ShieldWarning, X } from "@phosphor-icons/react";

/**
 * Staff take a review off the public site (owner decision 2026-09-28).
 *
 * NOT author deletion, and never shown as one: this is `POST
 * /admin/reviews/{id}/unpublish`, audited with the staff member, the reason,
 * the time and the review's previous state, and the author is told why.
 * Earnings are left as they were; the console's Restore undoes it.
 *
 * Offered only to staff viewers — and refused by the API to anyone else, which
 * is what actually matters.
 */
const FOCUS =
  "focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--accent-primary)]";

export function TakedownReviewDialog({
  reviewId,
  open,
  onClose,
}: {
  reviewId: string;
  open: boolean;
  onClose: () => void;
}) {
  const router = useRouter();
  const ref = useRef<HTMLDialogElement>(null);
  const titleId = useId();
  const reasonId = useId();
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    if (open && !el.open) el.showModal();
    if (!open && el.open) el.close();
  }, [open]);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const handle = () => {
      setError(null);
      onClose();
    };
    el.addEventListener("close", handle);
    return () => el.removeEventListener("close", handle);
  }, [onClose]);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (busy || !reason.trim()) return;
    setBusy(true);
    setError(null);
    try {
      const res = await fetch(`/api/bff/api/v1/admin/reviews/${encodeURIComponent(reviewId)}/unpublish`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ reason: reason.trim() }),
      });
      if (!res.ok) {
        const problem = (await res.json().catch(() => ({}))) as { detail?: string };
        setError(problem.detail ?? "Couldn't take this review down.");
        return;
      }
      ref.current?.close();
      setReason("");
      router.refresh();
    } catch {
      setError("Couldn't reach the server.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <dialog
      ref={ref}
      aria-labelledby={titleId}
      data-testid="takedown-review-dialog"
      className="m-auto max-h-[90dvh] w-[min(390px,calc(100vw-2rem))] overflow-y-auto rounded-[20px] bg-[var(--surface-app)] p-0 text-[var(--text-primary)] shadow-[var(--shadow-sheet)] backdrop:bg-[var(--overlay-scrim-25)]"
    >
      <div className="flex items-start gap-2 px-6 pt-6">
        <ShieldWarning size={20} aria-hidden="true" className="shrink-0" />
        <h2 id={titleId} className="mt-0.5 min-w-0 flex-1 text-[16px] font-bold leading-none">
          Take this review down?
        </h2>
        <button
          type="button"
          onClick={() => ref.current?.close()}
          aria-label="Close"
          className={`-my-2 -mr-2 grid h-11 w-11 shrink-0 cursor-pointer place-items-center rounded-full hover:bg-[var(--line-hairline-10)] ${FOCUS}`}
        >
          <X size={28} aria-hidden="true" />
        </button>
      </div>
      <hr className="mx-6 mt-[22px] border-0 border-t border-[var(--line-hairline-30)]" />
      <form onSubmit={submit} className="px-6 pb-8 pt-[15px]">
        <p className="text-[14px] leading-[21px]">
          It leaves the public site at once. This is a staff takedown: it is recorded against you with
          your reason, the author is told why, and it can be restored from the console.
        </p>
        <label htmlFor={reasonId} className="mt-5 block text-[14px] font-semibold leading-none">
          Reason (sent to the author)
        </label>
        <textarea
          id={reasonId}
          value={reason}
          onChange={(e) => setReason(e.target.value.slice(0, 500))}
          rows={3}
          required
          className="mt-3 block min-h-[88px] w-full resize-y rounded-[16px] border border-transparent bg-[var(--surface-card)] px-[15px] py-3 text-[14px] leading-[21px] shadow-[var(--shadow-card)] outline-none focus-visible:border-[var(--accent-primary)]"
        />
        {error ? (
          <p role="alert" className="mt-3 text-[12px] leading-[18px] text-[var(--accent-danger)]">
            {error}
          </p>
        ) : null}
        <div className="mt-[30px] flex items-center justify-between">
          <button type="button" onClick={() => ref.current?.close()} className={`cursor-pointer text-[16px] ${FOCUS}`}>
            Cancel
          </button>
          <button
            type="submit"
            disabled={busy || !reason.trim()}
            className={`h-[38px] cursor-pointer rounded-[20px] bg-[var(--base-ink-800)] px-3 text-[16px] text-[var(--text-on-brand)] disabled:cursor-not-allowed disabled:bg-[var(--disabled-surface)] disabled:text-[var(--disabled-text)] ${FOCUS}`}
          >
            {busy ? "Taking down…" : "Take down"}
          </button>
        </div>
      </form>
    </dialog>
  );
}
