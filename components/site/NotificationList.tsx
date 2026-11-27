"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { Check, EnvelopeSimple, Trash } from "@phosphor-icons/react";

import { OverflowMenu } from "@/components/ui/OverflowMenu";

import {
  applyNotificationAction,
  notificationActionRequest,
  notificationHref,
  type NotificationAction,
  type NotificationItem,
} from "./notification-model";
import { adjustUnread, refreshUnread, setUnread } from "./unread-store";

/** How long opening a notice waits for "read" to reach the server before it
 *  navigates anyway (QA-064): long enough for the normal case, short enough
 *  that a slow network never traps the reader on this page. */
const READ_BEFORE_NAVIGATE_MS = 1500;

const WHEN = new Intl.DateTimeFormat("en-PH", {
  dateStyle: "medium",
  timeStyle: "short",
  timeZone: "Asia/Manila",
});

/**
 * The signed-in account's notifications (FR-1 1.6).
 *
 * Opening one marks it read and follows its link. The row, the "N unread"
 * line and the header badge change at once (QA-064) — all three read the same
 * shared count — and the read is sent to the server BEFORE navigating, waited
 * for up to READ_BEFORE_NAVIGATE_MS, so the page the reader lands on already
 * agrees. Each row's "⋯" menu marks it read or unread again, or clears it from
 * the list (QA-065): a soft dismissal on the server, which deletes nothing the
 * notice was about. A failed call puts the row back as it was.
 */
export function NotificationList({ initial }: { initial: NotificationItem[] }) {
  const router = useRouter();
  const [items, setItems] = useState(initial);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");
  const unread = items.filter((n) => !n.read_at).length;

  // The page arrived with the server's list; the badge learns the server's
  // count too, rather than keeping whatever it read on an earlier page.
  useEffect(() => {
    void refreshUnread();
  }, []);

  async function act(item: NotificationItem, action: NotificationAction): Promise<boolean> {
    const before = items;
    const { items: next, unreadDelta } = applyNotificationAction(items, item.id, action, new Date().toISOString());
    setItems(next);
    adjustUnread(unreadDelta);
    const { path, method } = notificationActionRequest(item.id, action);
    try {
      const res = await fetch(path, { method, keepalive: true });
      if (!res.ok && res.status !== 404) throw new Error(String(res.status));
      void refreshUnread();
      return true;
    } catch {
      setItems(before);
      adjustUnread(-unreadDelta);
      setNotice("That didn't save. Try again.");
      return false;
    }
  }

  async function open(item: NotificationItem) {
    if (!item.read_at) {
      await Promise.race([
        act(item, "read"),
        new Promise((resolve) => setTimeout(resolve, READ_BEFORE_NAVIGATE_MS)),
      ]);
    }
    router.push(notificationHref(item.link));
  }

  async function markAll() {
    if (busy || unread === 0) return;
    setBusy(true);
    try {
      const res = await fetch("/api/bff/api/v1/notifications/read-all", { method: "POST" });
      if (res.ok) {
        const now = new Date().toISOString();
        setItems((list) => list.map((n) => (n.read_at ? n : { ...n, read_at: now })));
        setUnread(0);
        void refreshUnread();
        router.refresh();
      }
    } catch {
      /* the read state is a convenience; leave the list as it was */
    } finally {
      setBusy(false);
    }
  }

  if (items.length === 0) {
    return (
      <p className="mt-6 text-[14px] text-[var(--text-secondary)]">
        Nothing here. This is where you hear when someone finds your review helpful, comments,
        replies or mentions you, when a request you made is answered, when a question you asked
        is answered, and when an administrator decides something you sent.
      </p>
    );
  }

  return (
    <>
      <div className="mt-4 flex items-center justify-between gap-3">
        <p className="text-[13px] text-[var(--text-secondary)]" aria-live="polite">
          {unread === 0 ? "All read" : `${unread} unread`}
        </p>
        <button
          type="button"
          onClick={markAll}
          disabled={busy || unread === 0}
          className="cursor-pointer text-[13px] font-medium text-[var(--accent-primary)] underline-offset-4 hover:underline disabled:cursor-default disabled:text-[var(--text-muted)] disabled:no-underline"
        >
          {busy ? "Marking…" : "Mark all read"}
        </button>
      </div>

      <p role="status" aria-live="polite" className="mt-2 text-[12px] text-[var(--accent-danger)] empty:hidden">
        {notice}
      </p>
      <ul className="mt-3 border-t border-[var(--line-hairline-10)]">
        {items.map((item) => {
          const isUnread = !item.read_at;
          return (
            <li
              key={item.id}
              data-notification-id={item.id}
              data-unread={isUnread ? "true" : "false"}
              // QA-055: unread is a tinted row with an accent edge, not just a
              // dot and a heavier title; read rows sit back in muted ink. The
              // tint covers the whole row, the "⋯" column included.
              className={`flex items-start gap-1 border-b border-l-[3px] border-b-[var(--line-hairline-10)] ${
                isUnread
                  ? "border-l-[var(--accent-primary)] bg-[color-mix(in_srgb,var(--accent-primary)_7%,transparent)]"
                  : "border-l-transparent"
              }`}
            >
              <button
                type="button"
                onClick={() => open(item)}
                className="flex min-w-0 flex-1 cursor-pointer items-start gap-3 py-4 pl-3 pr-2 text-left hover:bg-[var(--line-hairline-10)] focus-visible:outline focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-[var(--accent-primary)]"
              >
                <span
                  aria-hidden="true"
                  className={`mt-1.5 h-2 w-2 shrink-0 rounded-full ${
                    isUnread ? "bg-[var(--accent-primary)]" : "bg-transparent"
                  }`}
                />
                <span className="min-w-0 flex-1">
                  <span
                    className={`block text-[14px] ${
                      isUnread ? "font-semibold text-[var(--text-primary)]" : "font-normal text-[var(--text-secondary)]"
                    }`}
                  >
                    {item.title}
                    {/* QA-055: a worded label, not only a tint and a dot — the
                        state reads without colour, and is announced. */}
                    {isUnread ? (
                      <span className="ml-2 inline-flex translate-y-[-1px] items-center rounded-[var(--radius-pill)] bg-[var(--accent-primary)] px-2 py-0.5 align-middle text-[10px] font-semibold uppercase leading-none tracking-[0.4px] text-[var(--text-on-brand)]">
                        New<span className="sr-only">, unread</span>
                      </span>
                    ) : (
                      <span className="sr-only"> (read)</span>
                    )}
                  </span>
                  {item.body ? (
                    <span className="mt-0.5 block text-[13px] text-[var(--text-secondary)]">
                      {item.body}
                    </span>
                  ) : null}
                  <span className="mt-1 block text-[12px] text-[var(--text-muted)]">
                    <time dateTime={item.created_at}>{WHEN.format(new Date(item.created_at))}</time>
                  </span>
                </span>
              </button>
              <div className="pt-3 pr-1">
                <OverflowMenu
                  label={`Actions for “${item.title}”`}
                  items={[
                    isUnread
                      ? {
                          key: "read",
                          label: "Mark as read",
                          icon: <Check size={16} />,
                          onSelect: () => void act(item, "read"),
                        }
                      : {
                          key: "unread",
                          label: "Mark as unread",
                          icon: <EnvelopeSimple size={16} />,
                          onSelect: () => void act(item, "unread"),
                        },
                    {
                      key: "dismiss",
                      label: "Remove from list",
                      icon: <Trash size={16} />,
                      onSelect: () => void act(item, "dismiss"),
                    },
                  ]}
                />
              </div>
            </li>
          );
        })}
      </ul>
    </>
  );
}

export default NotificationList;
