import Link from "next/link";
import { CaretRight } from "@phosphor-icons/react/dist/ssr";

/**
 * An Overview card's header (Screen/Admin/Overview v4, 8444:38623): the title
 * in 16px SemiBold on a 24px line with a 14px CaretRight, linked to the full
 * list; a 12px Regular note at 40% ink on the right.
 */
export function OverviewCardHeader({
  id,
  title,
  href,
  note,
}: {
  id: string;
  title: string;
  href: string;
  note?: React.ReactNode;
}) {
  return (
    <div className="flex min-w-0 items-center gap-1">
      <h2 id={id} className="min-w-0 text-[16px] font-semibold leading-6">
        <Link href={href} className="inline-flex items-center gap-1 hover:text-[var(--accent-primary)]">
          {title}
          <CaretRight size={14} aria-hidden="true" className="shrink-0 text-[var(--text-secondary)]" />
        </Link>
      </h2>
      <span className="flex-1" />
      {note ? <span className="shrink-0 text-[12px] leading-4 text-[var(--text-muted)]">{note}</span> : null}
    </div>
  );
}

export const OVERVIEW_CARD =
  "flex min-w-0 flex-col gap-[10px] rounded-[16px] border border-[var(--border-subtle)] bg-[var(--surface-card)] p-5";
