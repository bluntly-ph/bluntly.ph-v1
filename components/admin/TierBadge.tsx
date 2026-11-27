"use client";

import {
  tierLabel,
  tierSummary,
  TIER_LABELS,
  type PriorityTier,
  type Triage,
} from "./review-queue-model";

/**
 * The admin priority tier (dev note 2026-09-26) as a badge that explains
 * itself: its tooltip and accessible name carry the reasons — "Highest: Wilson
 * near threshold + 2 fraud reports" — never a bare number. A triage label only;
 * any item can still be opened and decided in any order.
 */
const TONE: Record<PriorityTier, string> = {
  highest: "bg-[var(--accent-danger)] text-white",
  high: "bg-[color-mix(in_srgb,var(--accent-danger)_16%,transparent)] text-[var(--accent-danger)]",
  neutral: "bg-[var(--line-hairline-10)] text-[var(--text-primary)]",
  low: "bg-[color-mix(in_srgb,var(--accent-success)_14%,transparent)] text-[var(--accent-success)]",
  lowest: "bg-[color-mix(in_srgb,var(--accent-success)_8%,transparent)] text-[var(--text-secondary)]",
};

export function tierTone(tier: PriorityTier): string {
  return TONE[tier] ?? TONE.neutral;
}

export function TierBadge({ triage, compact = false }: { triage: Triage | null | undefined; compact?: boolean }) {
  if (!triage) {
    return <span className="text-[11px] text-[var(--text-muted)]">—</span>;
  }
  const why = tierSummary(triage);
  const label = compact ? (TIER_LABELS[triage.tier] ?? triage.tier) : tierLabel(triage);
  return (
    <span
      data-tier={triage.tier}
      title={`${tierLabel(triage)}: ${why}`}
      aria-label={`Priority ${tierLabel(triage)}: ${why}`}
      className={`inline-flex items-center whitespace-nowrap rounded-[var(--radius-pill)] px-2 py-0.5 text-[11px] font-medium ${tierTone(triage.tier)}`}
    >
      {label}
      {triage.aged ? <span aria-hidden="true" className="ml-1">↑</span> : null}
    </span>
  );
}

/** The full explanation, for the detail pane and the report rows. */
export function TierReasons({ triage }: { triage: Triage }) {
  return (
    <ul className="mt-1 flex flex-col gap-1 text-[12px] text-[var(--text-secondary)]">
      {triage.reasons.map((r) => (
        <li key={r.code}>
          <span className="font-medium text-[var(--text-primary)]">{r.label}.</span> {r.detail}
        </li>
      ))}
    </ul>
  );
}
