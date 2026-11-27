import Image from "next/image";
import Link from "next/link";
import { ArrowLeft } from "@phosphor-icons/react/dist/ssr";

import { change, compact, pesoSplit, share } from "@/components/dashboard/contributor-model";
import type { ContributorReach } from "@/lib/dashboard";

/**
 * The contributor screens' shared pieces (Figma Screen/Dashboard 7833:9534,
 * Screen/Payout 7840:9380): money with smaller cents, and the card — a 3px
 * app-grey frame around a white 32px-radius panel.
 */

export function Money({ value, whole = "text-[24px]", cents = "text-[24px]", tone = "" }: { value: string; whole?: string; cents?: string; tone?: string }) {
  const [w, c] = pesoSplit(value);
  return (
    <span className={`whitespace-nowrap font-semibold leading-none [font-variant-numeric:tabular-nums] ${tone}`}>
      <span className={whole}>{w}</span>
      <span className={cents}>{c}</span>
    </span>
  );
}

export function Panel({ children, className = "" }: { children: React.ReactNode; className?: string }) {
  return <div className={`rounded-[32px] bg-[var(--surface-card)] p-5 ${className}`}>{children}</div>;
}

export function Frame({ children, className = "", label }: { children: React.ReactNode; className?: string; label: string }) {
  return (
    <section aria-label={label} className={`mb-4 break-inside-avoid rounded-[32px] bg-[var(--surface-app)] ${className}`}>
      {children}
    </section>
  );
}

function ReachLine({ value, label, pct, delta, suffix, light = false }: { value: number; label: string; pct: string | null; delta: string | null; suffix: string; light?: boolean }) {
  return (
    <div className="flex items-center justify-center gap-3">
      <span className="flex flex-col items-center gap-[2px] text-center">
        <span className={`text-[16px] font-semibold leading-none ${light ? "text-white" : "text-[#3c2b27]"}`}>{compact(value)}</span>
        <span className={`text-[10px] leading-none ${light ? "text-white/75" : "text-black/50"}`}>{pct ? `${label} · ${pct}` : label}</span>
      </span>
      {delta ? (
        <span className="absolute right-3 rounded-full bg-[var(--surface-card)] px-[10px] py-[5px] text-[12px] leading-none">
          <span className="font-medium text-black/70">{delta}</span> <span className="text-black/40">{suffix}</span>
        </span>
      ) : null}
    </div>
  );
}

/**
 * Chart/Reach rings (Dashboard 7833:9534, Performance 7848:9674): views ->
 * people helped -> link clicks -> purchases as nested rings, each with its
 * share of the ring outside it and its change against `before`.
 */
export function ReachRings({ now, before, suffix, label }: { now: ContributorReach; before: ContributorReach; suffix: string; label: string }) {
  const rows = [
    { size: 268, top: 32, src: "/figma/dashboard/ring-1.svg", value: now.views, label: "Views", pct: null, delta: change(now.views, before.views) },
    { size: 208, top: 92, src: "/figma/dashboard/ring-2.svg", value: now.helped, label: "Helped", pct: share(now.helped, now.views), delta: change(now.helped, before.helped) },
    { size: 154, top: 146, src: "/figma/dashboard/ring-3.svg", value: now.clicks, label: "Clicks", pct: share(now.clicks, now.helped), delta: change(now.clicks, before.clicks) },
    { size: 92, top: 208, src: "/figma/dashboard/ring-4.svg", value: now.bought, label: "Bought", pct: share(now.bought, now.clicks), delta: change(now.bought, before.bought) },
  ];
  return (
    <div className="relative mx-auto h-[280px] w-full max-w-[318px]">
      {rows.map((r) => (
        <Image key={r.src} src={r.src} alt="" width={r.size} height={r.size} className="absolute left-1/2 max-w-none -translate-x-1/2" style={{ top: r.top, width: r.size, height: r.size }} />
      ))}
      <ul aria-label={label} className="absolute inset-0">
        {rows.map((r, i) => (
          <li key={r.label} className="absolute inset-x-0" style={{ top: r.top + 12 }}>
            <ReachLine value={r.value} label={r.label} pct={r.pct} delta={r.delta} suffix={suffix} light={i === 3} />
          </li>
        ))}
      </ul>
    </div>
  );
}

/**
 * QA-016: where the frame's back arrow is not drawn (from `md`, under the site
 * header), a worded link up to the parent page — a plain link, so it works
 * after a direct visit too.
 */
export function ParentLink({ href, label }: { href: string; label: string }) {
  return (
    <Link
      href={href}
      className="mb-3 hidden w-fit items-center gap-1 rounded-[var(--radius-sm)] px-1 text-[14px] font-medium text-[var(--text-secondary)] no-underline hover:text-[var(--accent-primary)] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--accent-primary)] md:inline-flex"
    >
      <ArrowLeft size={18} aria-hidden="true" />
      {label}
    </Link>
  );
}
