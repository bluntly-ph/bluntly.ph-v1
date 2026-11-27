"use client";

import { useEffect, useId, useRef } from "react";
import { X } from "@phosphor-icons/react/dist/ssr";

/**
 * The console's confirmation dialog, built to the Confirm/* frames
 * (e.g. Confirm/Queue/Approve 8037:13080): 440px, radius 16, a 20px title with
 * a close button, the consequences as a list, then Back and the action.
 *
 * A native <dialog> opened modally, so focus is trapped and Escape closes it
 * without any of that being reimplemented here.
 */
export function ConfirmDialog({
  open,
  title,
  children,
  confirmLabel,
  cancelLabel = "Back",
  busyLabel,
  busy = false,
  disabled = false,
  tone = "primary",
  error,
  onConfirm,
  onClose,
}: {
  open: boolean;
  title: string;
  children: React.ReactNode;
  confirmLabel: string;
  /** The dismiss button; Confirm/Store/GiveUp says "Keep it". */
  cancelLabel?: string;
  busyLabel?: string;
  busy?: boolean;
  disabled?: boolean;
  tone?: "primary" | "danger" | "ink";
  error?: string | null;
  onConfirm: () => void;
  onClose: () => void;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  const titleId = useId();

  useEffect(() => {
    const dialog = ref.current;
    if (!dialog) return;
    if (open && !dialog.open) dialog.showModal();
    if (!open && dialog.open) dialog.close();
  }, [open]);

  const action =
    tone === "danger"
      ? "bg-[var(--accent-danger)]"
      : tone === "ink"
        ? "bg-[var(--base-ink-800)]"
        : "bg-[var(--accent-primary)]";

  return (
    <dialog
      ref={ref}
      aria-labelledby={titleId}
      onClose={onClose}
      onCancel={(e) => {
        e.preventDefault();
        if (!busy) onClose();
      }}
      className="m-auto w-[440px] max-w-[calc(100vw-32px)] rounded-[16px] bg-[var(--surface-card)] p-0 text-[var(--text-primary)] shadow-[var(--shadow-modal)] backdrop:bg-black/30"
    >
      <div className="flex items-center gap-2 px-6 pb-3 pt-6">
        <h2 id={titleId} className="flex-1 text-[20px] font-semibold leading-tight">{title}</h2>
        <button
          type="button"
          onClick={onClose}
          disabled={busy}
          aria-label="Close"
          className="grid size-8 place-items-center rounded-full text-[var(--text-secondary)] hover:bg-[var(--surface-app)]"
        >
          <X size={18} />
        </button>
      </div>
      <div className="flex flex-col gap-3 px-6 pb-5 text-[14px] leading-snug">{children}</div>
      {error ? (
        <p role="alert" className="px-6 pb-3 text-[12px] text-[var(--accent-danger)]">
          {error}
        </p>
      ) : null}
      <div className="flex justify-end gap-2 border-t border-[var(--border-subtle)] px-6 py-4">
        <button
          type="button"
          onClick={onClose}
          disabled={busy}
          className="h-8 rounded-full border border-[var(--base-ink-800)] px-3 text-[12px] font-medium"
        >
          {cancelLabel}
        </button>
        <button
          type="button"
          onClick={onConfirm}
          disabled={busy || disabled}
          className={`h-8 rounded-full px-4 text-[12px] font-medium text-white disabled:opacity-60 ${action}`}
        >
          {busy ? (busyLabel ?? `${confirmLabel}…`) : confirmLabel}
        </button>
      </div>
    </dialog>
  );
}

/** One consequence line: an icon and what will happen. */
export function Consequence({ icon, children }: { icon: React.ReactNode; children: React.ReactNode }) {
  return (
    <p className="flex items-start gap-3">
      <span className="mt-0.5 shrink-0 text-[var(--text-secondary)]">{icon}</span>
      <span>{children}</span>
    </p>
  );
}
