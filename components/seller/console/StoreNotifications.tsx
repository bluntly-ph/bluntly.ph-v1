"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { Bell } from "@phosphor-icons/react/dist/ssr";

import { usePopover } from "@/components/console/popover";
import { Bar, SkeletonRegion } from "@/components/ui/Skeleton";
import { UnreadBadge } from "@/components/ui/UnreadBadge";

import { agoShort, notificationsQuery, type NoteTab } from "./overview-model";

/**
 * Overlay/Store/Notifications (Figma 8212:23136; tabs Reviews 8232:25498,
 * Questions 8232:25556, Appeals 8232:25614): the owner's own notifications
 * (GET /notifications, filtered on the server by each tab's kinds); "Mark all seen" marks them read
 * (POST /notifications/read-all) and closes the panel.
 *
 * A store owner hears of a new store review (store_review_new), a new store
 * question (store_question_new) and an administrator's message on a claim or
 * an appeal (case_message); everything else they receive shows under All.
 */

type Note = { id: string; kind: string; title: string; body: string | null; link: string | null; read_at: string | null; created_at: string };
const TABS: { key: NoteTab; label: string }[] = [
  { key: "all", label: "All" },
  { key: "reviews", label: "Reviews" },
  { key: "questions", label: "Questions" },
  { key: "appeals", label: "Appeals" },
];

export function StoreNotifications({ storeId, unread }: { storeId: string; unread: number }) {
  const router = useRouter();
  const { open, setOpen, ref } = usePopover();
  const [tab, setTab] = useState<NoteTab>("all");
  const [loaded, setLoaded] = useState<{ tab: NoteTab; notes: Note[] | null; failed: boolean } | null>(null);
  // "Mark all seen" clears the count at once; the next server figure that
  // differs (a new notification) shows again.
  const [clearedFrom, setClearedFrom] = useState<number | null>(null);
  const unseen = clearedFrom !== null && clearedFrom === unread ? 0 : unread;

  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    fetch(notificationsQuery(tab), { cache: "no-store" })
      .then((r) => (r.ok ? (r.json() as Promise<Note[]>) : Promise.reject(new Error("load"))))
      .then((rows) => {
        if (!cancelled) setLoaded({ tab, notes: rows, failed: false });
      })
      .catch(() => {
        if (!cancelled) setLoaded({ tab, notes: null, failed: true });
      });
    return () => {
      cancelled = true;
    };
  }, [open, tab]);
  const current = loaded?.tab === tab ? loaded : null;
  const notes = current?.notes ?? null;
  const failed = current?.failed ?? false;

  async function markAllSeen() {
    const res = await fetch("/api/bff/api/v1/notifications/read-all", { method: "POST" }).catch(() => null);
    if (res?.ok) {
      setClearedFrom(unread);
      setLoaded((l) => (l && l.notes ? { ...l, notes: l.notes.map((n) => ({ ...n, read_at: n.read_at ?? new Date().toISOString() })) } : l));
      setOpen(false);
      router.refresh();
    }
  }

  const shown = notes ?? [];
  // eslint-disable-next-line react-hooks/purity -- ages are read when the panel renders.
  const now = Date.now();

  return (
    <div ref={ref} className="relative">
      <button
        type="button"
        aria-label={unseen ? `Notifications, ${unseen} unread` : "Notifications"}
        aria-expanded={open}
        aria-haspopup="dialog"
        onClick={() => setOpen(!open)}
        className="relative grid size-9 place-items-center rounded-full border border-[var(--border-subtle)] hover:bg-[var(--surface-app)]"
      >
        <Bell size={18} />
        <UnreadBadge count={unseen} testId="notifications-unread" />
      </button>
      {open ? (
        <div
          role="dialog"
          aria-label="Notifications"
          className="absolute right-0 top-[calc(100%+6px)] z-40 flex w-[360px] max-w-[calc(100vw-32px)] flex-col rounded-[16px] border border-[var(--border-subtle)] bg-[var(--surface-card)] shadow-[var(--shadow-modal)]"
        >
          <div className="flex items-center gap-2 px-4 pb-2 pt-4">
            <h2 className="flex-1 text-[16px] font-semibold leading-none">Notifications</h2>
            <button type="button" onClick={() => void markAllSeen()} className="text-[12px] text-[var(--chart-honesty-fund)] hover:underline">
              Mark all seen
            </button>
          </div>
          <div role="tablist" aria-label="Notification types" className="flex gap-4 border-b border-[var(--border-subtle)] px-4">
            {TABS.map((t) => (
              <button
                key={t.key}
                type="button"
                role="tab"
                aria-selected={tab === t.key}
                onClick={() => setTab(t.key)}
                className={`-mb-px border-b-2 pb-2 pt-1 text-[12px] font-medium ${
                  tab === t.key ? "border-[var(--text-primary)]" : "border-transparent text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
                }`}
              >
                {t.label}
              </button>
            ))}
          </div>
          <ul className="flex max-h-[360px] flex-col overflow-y-auto" aria-live="polite">
            {failed ? (
              <li className="px-4 py-6 text-center text-[12px] text-[var(--text-secondary)]">Notifications could not be loaded.</li>
            ) : notes === null ? (
              <li>
                <SkeletonRegion label="Loading notifications">
                  {Array.from({ length: 3 }, (_, i) => (
                    <span key={i} className="flex items-start gap-3 border-t border-[var(--border-subtle)] px-4 py-3 first:border-t-0">
                      <span className="flex min-w-0 flex-1 flex-col gap-2">
                        <Bar size={10} className="w-3/5" />
                        <Bar size={8} className="w-4/5" />
                      </span>
                      <Bar size={8} className="w-8" />
                    </span>
                  ))}
                </SkeletonRegion>
              </li>
            ) : shown.length === 0 ? (
              <li className="px-4 py-6 text-center text-[12px] text-[var(--text-secondary)]">Nothing here yet.</li>
            ) : (
              shown.map((n) => {
                const row = (
                  <span className="flex items-start gap-3 px-4 py-3">
                    <span aria-hidden className={`mt-1.5 size-[7px] shrink-0 rounded-full ${n.read_at ? "bg-transparent" : "bg-[var(--accent-primary)]"}`} />
                    <span className="flex min-w-0 flex-1 flex-col gap-1 leading-none">
                      <span className="truncate text-[14px]">{n.title}</span>
                      {n.body ? <span className="line-clamp-2 text-[12px] leading-4 text-[var(--text-secondary)]">{n.body}</span> : null}
                    </span>
                    <span className="shrink-0 text-[12px] text-[var(--text-secondary)]">{agoShort(n.created_at, now).replace(" ago", "")}</span>
                  </span>
                );
                return (
                  <li key={n.id} data-testid="store-notification" className="border-t border-[var(--border-subtle)] first:border-t-0">
                    {n.link ? (
                      <Link href={n.link} onClick={() => setOpen(false)} className="block hover:bg-[var(--surface-app)]">
                        {row}
                      </Link>
                    ) : (
                      row
                    )}
                  </li>
                );
              })
            )}
          </ul>
          <Link
            href={`/seller/${storeId}#waiting`}
            onClick={() => setOpen(false)}
            className="border-t border-[var(--border-subtle)] px-4 py-3 text-center text-[12px] text-[var(--chart-honesty-fund)] hover:underline"
          >
            See everything waiting on you
          </Link>
        </div>
      ) : null}
    </div>
  );
}
