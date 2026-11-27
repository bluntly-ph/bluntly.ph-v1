import { UserCircle } from "@phosphor-icons/react/dist/ssr";

/**
 * The sticky reply bar: Figma "Composer" (7659:6169), as the question page
 * (7731:15782) and the review page (Screen/Product 7660:6153) draw it — a #d9d9d9
 * rule on top, 12px over and 28px under, 16px in, a 32px avatar 12px before the
 * 44px #f2f2f2 pill. It sticks to the foot of its section while that section is
 * on screen and rests at its end. From `md` it is a rounded card.
 *
 * `data-docked-composer` lets QuickActions lift the FAB above it while it is
 * on screen, rather than sitting on its pill.
 */
export function ComposerShell({
  initial,
  children,
  className = "",
}: {
  /** The reader's initial; empty when signed out, which draws the person glyph. */
  initial: string;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <div
      data-docked-composer
      className={`sticky bottom-0 z-10 mt-6 flex items-center gap-3 border-t border-[#d9d9d9] bg-[var(--surface-card)] px-4 pb-7 pt-3 md:rounded-[16px] md:border md:pb-3 ${className}`}
    >
      {initial ? (
        <span aria-hidden className="grid size-8 shrink-0 place-items-center rounded-full bg-[var(--accent-primary)] text-[13px] font-medium text-white">
          {initial}
        </span>
      ) : (
        <UserCircle aria-hidden size={32} weight="light" className="shrink-0 text-[var(--text-secondary)]" />
      )}
      {children}
    </div>
  );
}
