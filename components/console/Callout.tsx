import { Info } from "@phosphor-icons/react/dist/ssr";

/**
 * A console callout: a short note on the app grey, icon first (Figma Callout).
 * Default icon Info; pass another (Lock for privacy notes) when it says more.
 */
export function Callout({ icon, className = "", children }: { icon?: React.ReactNode; className?: string; children: React.ReactNode }) {
  return (
    <p className={`flex items-start gap-2 rounded-[12px] bg-[var(--surface-app)] px-4 py-3 text-[12px] leading-[18px] text-[var(--text-secondary)] ${className}`}>
      <span className="mt-px shrink-0">{icon ?? <Info size={16} aria-hidden />}</span>
      <span>{children}</span>
    </p>
  );
}
