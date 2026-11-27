"use client";

import { useEffect, useLayoutEffect, useRef, useState, type ReactNode } from "react";
import { DotsThree } from "@phosphor-icons/react";

export type OverflowItem = {
  key: string;
  label: string;
  icon?: ReactNode;
  onSelect: () => void;
};

/**
 * A row's "⋯" menu (QA-065 notifications, QA-069 comments).
 *
 * The review top bar's menu (ReviewOverflowMenu) generalised: it opens toward
 * the side of the viewport with room and upward when there is none below
 * (QA-059), closes on an outside press or Escape — returning focus to the
 * trigger — and moves between items with the arrow keys. Every item does
 * something; a menu never lists a control that is not wired.
 */
export function OverflowMenu({ label, items }: { label: string; items: OverflowItem[] }) {
  const [open, setOpen] = useState(false);
  const root = useRef<HTMLDivElement>(null);
  const menu = useRef<HTMLDivElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const [place, setPlace] = useState<{ x: "start" | "end"; y: "below" | "above" }>({
    x: "end",
    y: "below",
  });

  useLayoutEffect(() => {
    if (!open || !root.current || !menu.current) return;
    const box = menu.current.getBoundingClientRect();
    const at = root.current.getBoundingClientRect();
    const x = at.right >= box.width + 8 ? "end" : "start";
    const roomBelow = window.innerHeight - at.bottom;
    const y = roomBelow >= box.height + 8 || roomBelow >= at.top ? "below" : "above";
    setPlace((p) => (p.x === x && p.y === y ? p : { x, y }));
    menu.current.querySelector<HTMLElement>("[role=menuitem]")?.focus();
  }, [open]);

  useEffect(() => {
    if (!open) return;
    function onPointerDown(event: PointerEvent) {
      if (!root.current?.contains(event.target as Node)) setOpen(false);
    }
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        event.preventDefault();
        setOpen(false);
        trigger.current?.focus();
        return;
      }
      if (event.key !== "ArrowDown" && event.key !== "ArrowUp") return;
      const entries = Array.from(menu.current?.querySelectorAll<HTMLElement>("[role=menuitem]") ?? []);
      if (entries.length === 0) return;
      event.preventDefault();
      const at = entries.indexOf(document.activeElement as HTMLElement);
      const next = event.key === "ArrowDown" ? (at + 1) % entries.length : (at - 1 + entries.length) % entries.length;
      entries[next]?.focus();
    }
    // QA-059: an open menu that stays put while the page scrolls ends up over
    // whatever scrolls under it. Scrolling the page closes it.
    const onScroll = () => setOpen(false);
    document.addEventListener("pointerdown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => {
      document.removeEventListener("pointerdown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
      window.removeEventListener("scroll", onScroll);
    };
  }, [open]);

  if (items.length === 0) return null;

  return (
    <div ref={root} className="relative shrink-0">
      <button
        ref={trigger}
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-label={label}
        aria-expanded={open}
        aria-haspopup="menu"
        className="grid h-9 w-9 cursor-pointer place-items-center rounded-full text-[var(--text-secondary)] hover:bg-[var(--line-hairline-10)] hover:text-[var(--text-primary)] focus-visible:outline focus-visible:outline-2 focus-visible:outline-[var(--accent-primary)]"
      >
        <DotsThree size={22} weight="bold" />
      </button>
      {open ? (
        <div
          ref={menu}
          role="menu"
          aria-label={label}
          data-placement={`${place.y}-${place.x}`}
          className={`absolute z-30 w-52 max-w-[calc(100vw-16px)] overflow-hidden rounded-[var(--radius-sm)] bg-[var(--surface-card)] py-1 shadow-[var(--shadow-card)] ${
            place.x === "end" ? "right-0" : "left-0"
          } ${place.y === "below" ? "top-full mt-1" : "bottom-full mb-1"}`}
        >
          {items.map((item) => (
            <button
              key={item.key}
              type="button"
              role="menuitem"
              onClick={() => {
                setOpen(false);
                item.onSelect();
              }}
              className="flex w-full cursor-pointer items-center gap-2 px-4 py-2.5 text-left text-[13px] text-[var(--text-primary)] hover:bg-[var(--overlay-hover)] focus-visible:bg-[var(--overlay-hover)] focus-visible:outline-none active:bg-[var(--overlay-pressed)]"
            >
              {item.icon}
              {item.label}
            </button>
          ))}
        </div>
      ) : null}
    </div>
  );
}

export default OverflowMenu;
