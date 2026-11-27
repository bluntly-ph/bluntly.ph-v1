"use client";

import { useEffect, useRef } from "react";
import { X } from "@phosphor-icons/react/dist/ssr";

/**
 * A console modal for a row's details (the queue's investigation moved into a
 * modal, meeting 2026-10-02). A native modal <dialog>: focus stays inside and
 * Escape closes it.
 */
export function AdminModal({
  title,
  subtitle,
  width = 960,
  onClose,
  children,
}: {
  title: string;
  subtitle?: string;
  width?: number;
  onClose: () => void;
  children: React.ReactNode;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const dialog = ref.current;
    if (dialog && !dialog.open) dialog.showModal();
  }, []);

  return (
    <dialog
      ref={ref}
      onCancel={(e) => {
        e.preventDefault();
        onClose();
      }}
      aria-label={title}
      style={{ width }}
      className="m-auto flex max-h-[calc(100dvh-32px)] max-w-[calc(100vw-32px)] flex-col overflow-hidden rounded-[24px] bg-[var(--surface-card)] p-0 text-[var(--text-primary)] shadow-[var(--shadow-modal)] backdrop:bg-black/30 [&:not([open])]:hidden"
    >
      <div className="flex shrink-0 items-start gap-3 border-b border-[var(--border-subtle)] px-6 py-5">
        <div className="min-w-0 flex-1">
          <h2 className="text-[20px] font-semibold leading-tight">{title}</h2>
          {subtitle ? <p className="mt-0.5 text-[12px] text-[var(--text-secondary)]">{subtitle}</p> : null}
        </div>
        <button type="button" onClick={onClose} aria-label="Close" className="grid size-8 place-items-center rounded-full hover:bg-[var(--surface-app)]">
          <X size={18} />
        </button>
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto">{children}</div>
    </dialog>
  );
}
