"use client";

import { useSyncExternalStore } from "react";

/**
 * The signed-in account's unread notification count, shared (QA-064).
 *
 * The header badge fetched its own count once per page load and nothing told
 * it when a notification was opened on the Notifications page, so the badge
 * stayed "3" beside a list that said "All read" until a manual refresh. Every
 * surface now reads and writes this one value: opening, marking or clearing a
 * notification adjusts it immediately (optimistically), and the server's
 * answer then replaces the estimate. Other tabs of the same site hear the new
 * value over a BroadcastChannel, so a badge in another tab does not go stale.
 */

type Listener = () => void;

let count: number | null = null;
const listeners = new Set<Listener>();
const CHANNEL = "bluntly-notifications";
let channel: BroadcastChannel | null = null;

function ensureChannel(): BroadcastChannel | null {
  if (channel || typeof window === "undefined" || typeof BroadcastChannel === "undefined") return channel;
  channel = new BroadcastChannel(CHANNEL);
  channel.onmessage = (event: MessageEvent<{ count?: unknown }>) => {
    if (typeof event.data?.count === "number") write(event.data.count, false);
  };
  return channel;
}

function write(next: number, broadcast: boolean): void {
  const value = Math.max(0, Math.floor(next));
  if (value === count) return;
  count = value;
  listeners.forEach((fn) => fn());
  if (broadcast) ensureChannel()?.postMessage({ count: value });
}

export function setUnread(next: number): void {
  write(next, true);
}

/** An optimistic change; ignored until a real count has been read. */
export function adjustUnread(delta: number): void {
  if (count === null) return;
  write(count + delta, true);
}

/** Ask the server. The answer replaces any optimistic estimate. */
export async function refreshUnread(): Promise<void> {
  try {
    const res = await fetch("/api/bff/api/v1/notifications/unread-count", { cache: "no-store" });
    if (!res.ok) return;
    const data = (await res.json()) as { count?: unknown };
    if (typeof data.count === "number") setUnread(data.count);
  } catch {
    /* the badge keeps its last value */
  }
}

function subscribe(fn: Listener): () => void {
  ensureChannel();
  listeners.add(fn);
  return () => {
    listeners.delete(fn);
  };
}

/** The shared count; null until the first read (and on the server). */
export function useUnreadCount(): number | null {
  return useSyncExternalStore(
    subscribe,
    () => count,
    () => null,
  );
}
