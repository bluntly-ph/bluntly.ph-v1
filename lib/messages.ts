import "server-only";

import { cache } from "react";

import { apiFetch } from "./api/client";
import { ApiError } from "./api/errors";
import { getSessionToken } from "./session";

/**
 * Reads for the Inbox (staff) and Messages (members), 0076. Every call is the
 * signed-in viewer's own; the API decides who may read what (a member's
 * someone-else conversation is a 404, the Inbox needs staff).
 */

type Schemas = import("@/lib/api-types").components["schemas"];
export type Conversation = Schemas["ConversationDetailOut"];
export type ConversationRow = Schemas["ConversationRowOut"];
export type InboxList = Schemas["InboxListOut"];
export type MemberList = Schemas["MemberListOut"];
export type LinkOption = Schemas["LinkOptionOut"];
export type StaffOption = Schemas["StaffOptionOut"];

export type InboxQuery = {
  tab: "all" | "sellers" | "reviewers" | "closed";
  topic: string;
  status: string;
  handled: string;
  q: string;
  sort: "latest" | "waiting" | "unread";
  page: number;
  size: number;
};

function first(v: string | string[] | undefined): string {
  return (Array.isArray(v) ? v[0] : v) ?? "";
}

export function parseInboxQuery(sp: Record<string, string | string[] | undefined>): InboxQuery {
  const tab = first(sp.tab);
  const sort = first(sp.sort);
  const size = Number(first(sp.size));
  const page = Number(first(sp.page));
  return {
    tab: tab === "sellers" || tab === "reviewers" || tab === "closed" ? tab : "all",
    topic: first(sp.topic),
    status: first(sp.status),
    handled: first(sp.handled),
    q: first(sp.q).slice(0, 120),
    sort: sort === "waiting" || sort === "unread" ? sort : "latest",
    page: Number.isFinite(page) && page > 0 ? Math.floor(page) : 1,
    size: [10, 25, 50].includes(size) ? size : 25,
  };
}

async function read<T>(path: string): Promise<T | null> {
  try {
    return await apiFetch<T>(path, { token: await getSessionToken() });
  } catch (error) {
    if (error instanceof ApiError && (error.status === 404 || error.status === 403 || error.status === 422)) return null;
    throw error;
  }
}

export const getInbox = cache(async (query: InboxQuery): Promise<InboxList | null> => {
  const p = new URLSearchParams();
  p.set("tab", query.tab);
  if (query.topic) p.set("topic", query.topic);
  if (query.status) p.set("status", query.status);
  if (query.handled) p.set("handled", query.handled);
  if (query.q) p.set("q", query.q);
  p.set("sort", query.sort);
  p.set("page", String(query.page));
  p.set("size", String(query.size));
  try {
    return await read<InboxList>(`/api/v1/admin/inbox?${p.toString()}`);
  } catch {
    return null;
  }
});

export const getInboxConversation = cache(async (id: string): Promise<Conversation | null> => {
  try {
    return await read<Conversation>(`/api/v1/admin/inbox/${encodeURIComponent(id)}`);
  } catch {
    return null;
  }
});

export const getInboxStaff = cache(async (): Promise<StaffOption[]> => {
  try {
    return (await read<StaffOption[]>("/api/v1/admin/inbox/staff")) ?? [];
  } catch {
    return [];
  }
});

/** The rail's Inbox pill; 0 when it can't be read. */
export const getInboxUnread = cache(async (): Promise<number> => {
  try {
    return (await read<{ unread: number }>("/api/v1/admin/inbox/unread"))?.unread ?? 0;
  } catch {
    return 0;
  }
});

export const getMyConversations = cache(
  async (status: "open" | "closed", sellerId?: string): Promise<MemberList | null> => {
    const p = new URLSearchParams({ status });
    if (sellerId) p.set("seller_id", sellerId);
    try {
      return await read<MemberList>(`/api/v1/conversations?${p.toString()}`);
    } catch {
      return null;
    }
  },
);

export const getMyConversation = cache(async (id: string): Promise<Conversation | null> => {
  try {
    return await read<Conversation>(`/api/v1/conversations/${encodeURIComponent(id)}`);
  } catch {
    return null;
  }
});

export const getMyUnread = cache(async (sellerId?: string): Promise<number> => {
  try {
    const q = sellerId ? `?seller_id=${encodeURIComponent(sellerId)}` : "";
    return (await read<{ unread: number }>(`/api/v1/conversations/unread${q}`))?.unread ?? 0;
  } catch {
    return 0;
  }
});

export const getLinkOptions = cache(
  async (audience: "seller" | "reviewer", sellerId?: string): Promise<LinkOption[]> => {
    const p = new URLSearchParams({ audience });
    if (sellerId) p.set("seller_id", sellerId);
    try {
      return (await read<LinkOption[]>(`/api/v1/conversations/link-options?${p.toString()}`)) ?? [];
    } catch {
      return [];
    }
  },
);
