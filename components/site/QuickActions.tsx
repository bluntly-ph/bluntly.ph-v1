"use client";

import Link from "next/link";
import { useEffect, useId, useRef, useState } from "react";
import { PencilSimple, Plus, QuestionMark, Storefront } from "@phosphor-icons/react";
import type { Icon } from "@phosphor-icons/react";

import { actionMenuItems, isActionable } from "@/components/site/action-menu-model";

/**
 * The phone's floating "+" and its quick-action menu: Figma
 * QuickActions/Button on the browsing screens (Home, Search, Product,
 * Question, Profile, Dashboard…) and Overlay/QuickActions (8502:40871,
 * signed out 8511:41142; QuickActions/Menu 8502:40863).
 *
 *   FAB         56px accent circle 16px from the right and 24px from the
 *               bottom, a 26px Plus, shadow 0 2 6 10% + 0 8 20 #f05921 32%;
 *               open, the Plus turns 45° into a close mark
 *   Scrim       #141414 at 45%, full screen; tapping it closes
 *   Items       bottom-up from 28px above the FAB, 64px apart, centred on it: "Write a
 *               review" (PencilSimple), "Rate a seller" (Storefront), "Ask a
 *               question" (QuestionMark) — a 14/20 Medium label on a white
 *               12px-radius pill (14×8) beside a 48px white disc with the 22px
 *               glyph in accent, 12px apart, both shadowed 0 4 14 12%
 *
 * Signed in and signed out draw the same three items; the routes they open
 * send a signed-out reader to log in first. Below `md` only — no frame draws
 * it wider, and from `md` the site header carries "Write a review".
 *
 * On a store's page (`sellerId`) "Rate a seller" opens that store's composer
 * (action-menu-model, which the retired ActionMenu used).
 *
 * While a docked composer (ComposerShell, `data-docked-composer`) is on
 * screen it rises by that bar's height, so it never sits on the pill; the
 * frames place it 24px up because they draw the composer at the page's end.
 * `lift` is a fixed minimum for any other bar.
 *
 * Closed, it sits at z-30 so a page's sheets and dialogs (scrims from z-40)
 * cover it; open, it rises with its own menu above its scrim.
 */
const ICON: Record<string, Icon> = { ask: QuestionMark, seller: Storefront, review: PencilSimple };

const SHADOW = "shadow-[0_4px_14px_rgba(0,0,0,0.12)]";

export function QuickActions({ lift = 0, sellerId }: { lift?: number; sellerId?: string }) {
  const [open, setOpen] = useState(false);
  const menuId = useId();
  const fab = useRef<HTMLButtonElement>(null);
  const items = actionMenuItems({ sellerId }).filter(isActionable);
  // The height of a docked composer (ComposerShell) while one is on screen.
  const [dock, setDock] = useState(0);

  useEffect(() => {
    const bars = Array.from(document.querySelectorAll<HTMLElement>("[data-docked-composer]"));
    if (bars.length === 0 || typeof IntersectionObserver === "undefined") return;
    const seen = new Map<Element, number>();
    const io = new IntersectionObserver((entries) => {
      for (const e of entries) seen.set(e.target, e.isIntersecting ? e.boundingClientRect.height : 0);
      setDock(Math.max(0, ...seen.values()));
    });
    bars.forEach((b) => io.observe(b));
    return () => io.disconnect();
  }, []);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== "Escape") return;
      setOpen(false);
      fab.current?.focus();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open]);

  const bottom = 24 + Math.max(lift, Math.round(dock));
  return (
    <div className="md:hidden">
      {open ? (
        <>
          {/* The FAB is the close control; the scrim only catches taps. */}
          <div aria-hidden="true" onClick={() => setOpen(false)} data-quick-actions-scrim className="fixed inset-0 z-40 cursor-pointer bg-[#141414]/45" />
          <nav
            id={menuId}
            aria-label="Quick actions"
            className="fixed right-5 z-50 flex flex-col items-end gap-4"
            style={{ bottom: bottom + 56 + 28 }}
          >
            {items.map(({ key, href, label }) => {
              const Glyph = ICON[key] ?? Plus;
              return (
                <Link key={key} href={href!} onClick={() => setOpen(false)} className="flex items-center gap-3 no-underline">
                  <span className={`rounded-[12px] bg-[var(--surface-card)] px-[14px] py-2 text-[14px] font-medium leading-5 text-[var(--text-primary)] ${SHADOW}`}>
                    {label}
                  </span>
                  <span className={`grid size-12 place-items-center rounded-full bg-[var(--surface-card)] text-[var(--accent-primary)] ${SHADOW}`}>
                    <Glyph size={22} aria-hidden />
                  </span>
                </Link>
              );
            })}
          </nav>
        </>
      ) : null}
      <button
        ref={fab}
        type="button"
        aria-label={open ? "Close quick actions" : "Quick actions"}
        aria-expanded={open}
        aria-controls={open ? menuId : undefined}
        onClick={() => setOpen((v) => !v)}
        className={`fixed right-4 grid size-14 cursor-pointer place-items-center rounded-full bg-[var(--accent-primary)] text-white shadow-[0_2px_6px_rgba(0,0,0,0.1),0_8px_20px_rgba(240,89,33,0.32)] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--accent-primary)] ${open ? "z-50" : "z-30"}`}
        style={{ bottom }}
      >
        <Plus size={26} aria-hidden className={`transition-transform duration-200 ${open ? "rotate-45" : ""}`} />
      </button>
    </div>
  );
}
