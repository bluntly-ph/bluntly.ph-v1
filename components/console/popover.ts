"use client";

import { useEffect, useRef, useState } from "react";

/**
 * The console's toolbar menus (Sort / Filter / Search popovers, Figma Menu/*):
 * open state that closes on an outside click or Escape.
 */
export function usePopover() {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    function onClick(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    }
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") setOpen(false);
    }
    window.addEventListener("mousedown", onClick);
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("mousedown", onClick);
      window.removeEventListener("keydown", onKey);
    };
  }, [open]);
  return { open, setOpen, ref };
}

/** Figma "IconButton" in a console toolbar (32px, 8px radius). */
export const ICON_BUTTON =
  "relative grid size-8 place-items-center rounded-[8px] hover:bg-[var(--surface-app)] focus-visible:outline focus-visible:outline-2 focus-visible:outline-[var(--accent-primary)]";

/** A toolbar menu panel: 16px radius, hairline, the modal/menu shadow token. */
export const MENU =
  "absolute right-0 top-[calc(100%+6px)] z-30 rounded-[16px] border border-[var(--border-subtle)] bg-[var(--surface-card)] shadow-[var(--shadow-modal)]";
