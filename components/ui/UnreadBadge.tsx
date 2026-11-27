import { unreadBadge } from "./unread";

/**
 * The count on a top-bar icon (MQA-032), over its top-right corner. The icon's
 * own aria-label says the number in words, so the badge is hidden from
 * assistive tech.
 */
export function UnreadBadge({ count, testId }: { count: number; testId?: string }) {
  const label = unreadBadge(count);
  if (!label) return null;
  return (
    <span
      aria-hidden
      data-testid={testId}
      className="absolute -right-1 -top-1 grid h-[18px] min-w-[18px] place-items-center rounded-full bg-[var(--accent-primary)] px-1 text-[10px] font-semibold leading-none text-white ring-2 ring-[var(--surface-card)]"
    >
      {label}
    </span>
  );
}
