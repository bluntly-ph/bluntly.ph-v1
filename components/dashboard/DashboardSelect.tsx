"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { CaretDown } from "@phosphor-icons/react/dist/ssr";
import { DROPDOWN_PILL_STATES } from "@/components/ui/search-styles";

/**
 * Figma Dropdown/Pill (7853:9589): a 12px Medium label and a 12px caret in a
 * white pill with a hairline border. A native <select> underneath, so it is
 * keyboard- and screen-reader-ready; choosing writes the value to the URL
 * (`?period=month`), which the server page reads — reloadable and shareable.
 */
export function DashboardSelect({
  param,
  value,
  label,
  options,
  tone = "pill",
}: {
  param: string;
  value: string;
  label: string;
  options: { value: string; label: string }[];
  /** "brand": Figma Switcher (7761:7896) — the orange 32px pill with a 16px caret. */
  tone?: "pill" | "brand";
}) {
  const router = useRouter();
  const pathname = usePathname() ?? "/dashboard";
  const search = useSearchParams();
  const current = options.find((o) => o.value === value)?.label ?? options[0]?.label ?? "";
  // The visible pill is drawn in the design's 12px; the native <select> lies
  // over it, transparent, at the site's 16px so iOS does not zoom on focus.
  return (
    <label
      className={
        tone === "brand"
          ? "relative inline-flex h-8 min-w-0 shrink items-center gap-[6px] rounded-[16px] bg-[var(--accent-primary)] pl-[14px] pr-[10px] text-[12px] font-medium leading-normal text-white focus-within:outline focus-within:outline-2 focus-within:outline-offset-2 focus-within:outline-[var(--accent-primary)]"
          : // Figma Dropdown/Pill (8267:27483): Default, Hover (30% edge, 5% wash), Pressed (9% wash).
            `relative inline-flex h-[30px] shrink-0 items-center gap-[6px] rounded-[32px] px-[14px] leading-none ${DROPDOWN_PILL_STATES} focus-within:outline focus-within:outline-2 focus-within:outline-offset-2 focus-within:outline-[var(--accent-primary)]`
      }
    >
      <span aria-hidden className="truncate">{current}</span>
      <CaretDown size={tone === "brand" ? 16 : 12} aria-hidden className="shrink-0" />
      <select
        aria-label={label}
        value={value}
        onChange={(e) => {
          const next = new URLSearchParams(search?.toString() ?? "");
          if (e.target.value) next.set(param, e.target.value);
          else next.delete(param);
          router.push(`${pathname}?${next.toString()}`, { scroll: false });
        }}
        className="absolute inset-0 cursor-pointer appearance-none opacity-0"
      >
        {options.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
    </label>
  );
}
