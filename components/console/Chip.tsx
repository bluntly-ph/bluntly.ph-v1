/**
 * Figma component Admin/Chip: "Status and meta chips. Tone: Neutral (meta),
 * Muted, Success (done/positive), Warning (needs attention), Critical
 * (flagged/negative), Dark (selected sort)." One tone set for the admin and
 * seller consoles; colours come from the status tokens, never per screen.
 */
export type ChipTone = "neutral" | "muted" | "success" | "warning" | "critical" | "dark";

const TONE: Record<ChipTone, string> = {
  neutral: "bg-[var(--status-neutral-bg)] text-[var(--status-neutral-fg)]",
  muted: "bg-[var(--surface-app)] text-[var(--text-secondary)]",
  success: "bg-[var(--status-baseline-bg)] text-[var(--status-baseline-fg)]",
  warning: "bg-[var(--status-high-bg)] text-[var(--status-high-fg)]",
  critical: "bg-[var(--status-critical-bg)] text-[var(--status-critical-fg)]",
  dark: "bg-[var(--base-ink-800)] text-white",
};

export function Chip({
  tone = "neutral",
  children,
  icon,
  className = "",
}: {
  tone?: ChipTone;
  children: React.ReactNode;
  icon?: React.ReactNode;
  className?: string;
}) {
  return (
    <span
      className={`inline-flex h-6 shrink-0 items-center gap-1 whitespace-nowrap rounded-full px-[10px] text-[12px] font-medium leading-none ${TONE[tone]} ${className}`}
    >
      {icon}
      {children}
    </span>
  );
}
