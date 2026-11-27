"use client";

import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { Check } from "@phosphor-icons/react";

/**
 * Figma "Menu" (7761:7939) as Screen/Search/Reviews/Sort open (7762:9948) and
 * Screen/Product/Questions/Sort open (7762:9479) draw it under a sort pill:
 * a 220px white card at radius 16 with 8px above and below and the
 * 0 4 16 / 12% shadow; each Menu/Option (7761:7914) 44px tall, 16px in, a
 * 14px label; the current one in brand Medium with a 16px Check at the right.
 * A 4% scrim covers the page while it is open.
 *
 * It sits 8px under the bar that holds the pill: right-aligned to that bar
 * when the pill is at its right ("Most helpful" beside "Filters"), otherwise
 * left-aligned to the pill ("Sort" after "All filters"), and never closer than
 * 16px to the screen's edge. When there is no room below, it opens 8px above
 * the pill instead.
 *
 * KEPT, NOT DRAWN: an optional `note` under the options — the sellers' sort
 * says what "Best evidenced" means (MQA-033), which the radio sheet used to.
 * And `sections`, for a sort the old radio sheet split into headed groups
 * (owner 2026-10-07: every sort is this dropdown, never a sheet or pills):
 * a 12px heading over each group, a hairline between groups. A section can
 * carry its own value, so one menu can set two orders at once — the comment
 * thread's rating first, then date to break ties.
 *
 * Choosing applies at once and closes, as the frames draw no button. Keyboard:
 * the current option takes focus; arrows, Home and End move; Enter or Space
 * chooses; Escape or Tab closes and returns focus to the pill.
 */

export type SortOption<T extends string> = { value: T; label: string };

export type SortSection<T extends string> = {
  heading: string;
  options: SortOption<T>[];
  /** This section's own current value and chooser; else the menu's. */
  value?: T;
  onChoose?: (value: T) => void;
};

const WIDTH = 220;
const EDGE = 16;
const GAP = 8;

export function SortMenu<T extends string>({
  label,
  anchor,
  bar,
  options,
  sections,
  value,
  onChoose,
  onClose,
  note,
}: {
  /** The menu's accessible name, e.g. "Sort reviews". */
  label: string;
  /** The pill that opened it. */
  anchor: HTMLElement;
  /** The bar the pill sits in; the menu hangs under it. */
  bar?: HTMLElement | null;
  /** One list of options, or `sections` of them. */
  options?: SortOption<T>[];
  sections?: SortSection<T>[];
  value?: T;
  onChoose?: (value: T) => void;
  onClose: () => void;
  /** One line under the options, for an order that needs defining. */
  note?: string;
}) {
  const menuRef = useRef<HTMLDivElement | null>(null);
  const groups: SortSection<T>[] = (sections ?? [{ heading: "", options: options ?? [] }]).map((g) => ({
    ...g,
    value: g.value ?? value,
    onChoose: g.onChoose ?? onChoose,
  }));
  const [pos, setPos] = useState<{ top: number; left: number } | null>(null);

  useLayoutEffect(() => {
    const place = () => {
      const pill = anchor.getBoundingClientRect();
      const row = (bar ?? anchor).getBoundingClientRect();
      const vw = document.documentElement.clientWidth;
      const rightAligned = pill.right > vw / 2;
      const raw = rightAligned ? row.right - WIDTH : pill.left;
      const left = Math.min(Math.max(raw, EDGE), Math.max(EDGE, vw - EDGE - WIDTH));
      // Below the bar, as drawn; above the pill when that would run off the
      // bottom of the screen (a pill low on the page, a long sectioned menu) —
      // the page cannot scroll while the menu is open.
      const height = menuRef.current?.offsetHeight ?? 0;
      const below = Math.max(row.bottom, pill.bottom) + GAP;
      const vh = document.documentElement.clientHeight;
      const top = below + height > vh - EDGE && pill.top - GAP - height >= EDGE ? pill.top - GAP - height : below;
      setPos({ top, left });
    };
    place();
    window.addEventListener("resize", onClose);
    return () => window.removeEventListener("resize", onClose);
  }, [anchor, bar, onClose]);

  useEffect(() => {
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = previous;
    };
  }, []);

  useEffect(() => {
    if (!pos) return;
    const items = menuRef.current?.querySelectorAll<HTMLElement>("[role='menuitemradio']");
    (Array.from(items ?? []).find((el) => el.getAttribute("aria-checked") === "true") ?? items?.[0])?.focus();
  }, [pos]);

  const onKeyDown = (e: React.KeyboardEvent<HTMLDivElement>) => {
    const items = Array.from(menuRef.current?.querySelectorAll<HTMLElement>("[role='menuitemradio']") ?? []);
    const at = items.indexOf(document.activeElement as HTMLElement);
    const next: Record<string, number> = { ArrowDown: at + 1, ArrowUp: at - 1, Home: 0, End: items.length - 1 };
    if (e.key in next) {
      e.preventDefault();
      items[(next[e.key] + items.length) % items.length]?.focus();
    } else if (e.key === "Escape" || e.key === "Tab") {
      e.preventDefault();
      onClose();
    }
  };

  return createPortal(
    <>
      <div aria-hidden="true" onClick={onClose} data-menu-scrim className="fixed inset-0 z-40 bg-[var(--overlay-scrim-04)]" />
      <div
        ref={menuRef}
        role="menu"
        aria-label={label}
        onKeyDown={onKeyDown}
        style={pos ? { top: pos.top, left: pos.left } : { visibility: "hidden" }}
        className="fixed z-50 flex w-[220px] flex-col overflow-clip rounded-[16px] bg-[var(--surface-card)] py-2 text-[var(--text-primary)] shadow-[var(--shadow-menu)]"
      >
        {groups.map((g, i) => {
          const items = g.options.map((o) => {
            const current = o.value === g.value;
            return (
              <button
                key={o.value}
                type="button"
                role="menuitemradio"
                aria-checked={current}
                tabIndex={-1}
                onClick={() => (current ? onClose() : g.onChoose?.(o.value))}
                className={`flex h-11 w-full cursor-pointer items-center gap-2 px-4 text-left text-[14px] leading-normal outline-none hover:bg-[var(--surface-app)] focus-visible:bg-[var(--surface-app)] ${
                  current ? "font-medium text-[var(--accent-primary)]" : "font-normal"
                }`}
              >
                <span className="min-w-0 flex-1 truncate">{o.label}</span>
                {current ? <Check size={16} aria-hidden="true" className="shrink-0" /> : null}
              </button>
            );
          });
          if (!g.heading) return items;
          return (
            <div
              key={g.heading}
              role="group"
              aria-label={g.heading}
              className={i > 0 ? "mt-2 border-t border-[var(--border-subtle)] pt-2" : ""}
            >
              <p aria-hidden="true" className="px-4 pb-1 pt-1 text-[12px] font-medium leading-[18px] text-[var(--text-secondary)]">
                {g.heading}
              </p>
              {items}
            </div>
          );
        })}
        {note ? (
          <p className="border-t border-[var(--border-subtle)] px-4 pb-1 pt-2 text-[12px] font-light leading-[18px] text-[var(--text-secondary)]">
            {note}
          </p>
        ) : null}
      </div>
    </>,
    document.body,
  );
}
