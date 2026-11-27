/**
 * Figma Compare Row: a figure against its peers on one track. The dot is this
 * store / product, the tick is the comparison (peers, category). `lo`..`hi` is
 * the track's scale. `toned` colours the figure (and the dot) success when it
 * is at or above the comparison and danger when below; only for figures where
 * higher is better. `dense` is the tighter row used inside a product card.
 * A missing figure shows "—" and draws no mark: nothing is placed on a guess.
 */
export function CompareRow({
  label,
  mine,
  theirs,
  lo = 0,
  hi,
  format,
  toned = false,
  dense = false,
}: {
  label: string;
  mine?: number | null;
  theirs?: number | null;
  lo?: number;
  hi: number;
  format: (v: number) => string;
  toned?: boolean;
  dense?: boolean;
}) {
  const at = (v: number) => `${Math.max(0, Math.min(100, ((v - lo) / (hi - lo)) * 100))}%`;
  const below = toned && mine != null && theirs != null && mine < theirs;
  const above = toned && mine != null && theirs != null && mine >= theirs;
  const tone = below ? "text-[var(--accent-danger)]" : above ? "text-[var(--accent-success)]" : "";
  return (
    <li className={`flex flex-col border-t border-[var(--border-subtle)] first:border-t-0 ${dense ? "gap-2 py-3" : "gap-3 py-4"}`}>
      <span className={`flex gap-2 ${dense ? "items-center" : "items-baseline"}`}>
        <span className="flex-1 text-[14px]">{label}</span>
        <span className={`text-[14px] font-medium ${tone}`}>{mine != null ? format(mine) : "—"}</span>
        <span className="text-[12px] text-[var(--text-secondary)]">vs {theirs != null ? format(theirs) : "—"}</span>
      </span>
      <span className="relative h-[4px] rounded-full bg-[var(--surface-app)]" aria-hidden>
        {theirs != null ? (
          <span
            className={`absolute w-[2px] ${dense ? "top-[-4px] h-3 bg-[var(--text-secondary)]" : "top-[-5px] h-[14px] bg-[var(--text-primary)]"}`}
            style={{ left: at(theirs) }}
          />
        ) : null}
        {mine != null ? (
          <span
            className={`absolute top-[-3px] size-[10px] -translate-x-1/2 rounded-full ${below ? "bg-[var(--accent-danger)]" : "bg-[var(--accent-primary)]"}`}
            style={{ left: at(mine) }}
          />
        ) : null}
      </span>
    </li>
  );
}
