"use client";

import Link from "next/link";
import { CaretDown, Check } from "@phosphor-icons/react/dist/ssr";

import { MENU, usePopover } from "@/components/console/popover";
import { MENU_ITEM } from "@/components/console/fields";

const PERIODS = [
  { key: "30d", label: "Last 30 days" },
  { key: "3m", label: "Last 3 months" },
  { key: "6m", label: "Last 6 months" },
  { key: "12m", label: "Last 12 months" },
  { key: "all", label: "All time" },
] as const;

/**
 * Menu/Store/Period (Figma 8212:23210): the window of the screen at `base`
 * (the Overview unless given), in the URL.
 */
export function PeriodMenu({ storeId, period, base }: { storeId: string; period: string; base?: string }) {
  const href = base ?? `/seller/${storeId}`;
  const { open, setOpen, ref } = usePopover();
  const current = PERIODS.find((p) => p.key === period) ?? PERIODS[2];
  return (
    <div ref={ref} className="relative">
      <button
        type="button"
        aria-haspopup="menu"
        aria-expanded={open}
        onClick={() => setOpen(!open)}
        className="flex h-9 items-center gap-2 rounded-full border border-[var(--border-subtle)] px-4 text-[12px]"
      >
        {current.label} <CaretDown size={12} aria-hidden />
      </button>
      {open ? (
        <ul role="menu" aria-label="Period" className={`${MENU} w-[220px] p-2`}>
          {PERIODS.map((p) => (
            <li key={p.key} role="none">
              <Link
                role="menuitemradio"
                aria-checked={p.key === current.key}
                href={p.key === "6m" ? href : `${href}?period=${p.key}`}
                onClick={() => setOpen(false)}
                className={MENU_ITEM}
              >
                {p.label}
                {p.key === current.key ? <Check size={16} aria-hidden /> : null}
              </Link>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}
