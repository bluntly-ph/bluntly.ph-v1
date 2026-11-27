import { Shield } from "@phosphor-icons/react/dist/ssr";

import { formatScore } from "./trust-score-model";

/**
 * People's Trust Score cell (owner, 2026-10-05). Shows the backend's
 * EFFECTIVE score — `reputation_score`, the override when one is set — and,
 * when overridden, an "Override" tag with the system's own score beside it.
 * Nothing here computes a score.
 */
export function TrustScoreCell({ score, computed, overridden }: { score: string | null; computed: string | null; overridden: boolean }) {
  return (
    <span className="flex flex-col gap-1 leading-none">
      <span className="inline-flex items-center gap-1" data-testid="trust-score">
        <Shield size={16} weight="fill" aria-hidden="true" className="text-[var(--accent-trust)]" />
        <span className="tabular-nums">{formatScore(score)}</span>
      </span>
      {overridden ? (
        <span className="text-[12px] text-[var(--text-secondary)]">
          <span className="text-[var(--accent-primary)]">Override</span> · system {formatScore(computed)}
        </span>
      ) : null}
    </span>
  );
}
