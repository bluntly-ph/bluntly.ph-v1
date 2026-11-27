/**
 * Pure helpers shared by the Inbox (staff), the Seller console's Messages and
 * the reviewer's Messages (Figma Screen/Admin/Inbox, Screen/Seller/Inbox,
 * Screen/Messages). No React here, so tests/frontend can import it.
 */

export type Topic = "appeal" | "claim" | "product" | "payout" | "review" | "report" | "account" | "other";

export const TOPIC_LABEL: Record<Topic, string> = {
  appeal: "Appeal",
  claim: "Claim",
  product: "Product request",
  payout: "Payout",
  review: "Review",
  report: "Report",
  account: "Account",
  other: "General",
};

/** Menu/Store/Chat/Topic (seller) and Screen/Messages/New (reviewer) choices. */
export const SELLER_TOPICS: { key: Topic; label: string; link?: "appeal" | "claim" | "product" }[] = [
  { key: "appeal", label: "An appeal", link: "appeal" },
  { key: "claim", label: "A claim", link: "claim" },
  { key: "product", label: "A product page" },
  { key: "account", label: "My store or account" },
  { key: "other", label: "Something else" },
];

export const REVIEWER_TOPICS: { key: Topic; label: string; link?: "payout" | "review" | "report" }[] = [
  { key: "payout", label: "A payout", link: "payout" },
  { key: "review", label: "A review I wrote", link: "review" },
  { key: "report", label: "A report I made", link: "report" },
  { key: "account", label: "My account" },
  { key: "other", label: "Something else" },
];

export const FIRST_MAX = 500;
export const REPLY_MAX = 2000;

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

/** "3 Oct" in Manila. */
export function dayLabel(iso: string): string {
  const d = new Date(new Date(iso).getTime() + 8 * 3600_000);
  return `${d.getUTCDate()} ${MONTHS[d.getUTCMonth()]}`;
}

/** "just now", "12m", "5h", "2d", "1w", then the date. */
export function agoCompact(iso: string, now: number): string {
  const s = Math.max(0, Math.round((now - new Date(iso).getTime()) / 1000));
  if (s < 60) return "just now";
  if (s < 3600) return `${Math.floor(s / 60)}m`;
  if (s < 86_400) return `${Math.floor(s / 3600)}h`;
  if (s < 7 * 86_400) return `${Math.floor(s / 86_400)}d`;
  if (s < 30 * 86_400) return `${Math.floor(s / (7 * 86_400))}w`;
  return dayLabel(iso);
}

/** The time under a bubble: "12m" for today-ish, else the date ("2 Oct"). */
export function stampLabel(iso: string, now: number): string {
  const s = (now - new Date(iso).getTime()) / 1000;
  if (s < 60) return "just now";
  if (s < 86_400) return agoCompact(iso, now);
  return dayLabel(iso);
}

export function firstName(name: string | null | undefined): string {
  const n = (name ?? "").replace(/^@/, "").trim();
  return n.split(/\s+/)[0] || "them";
}

/** "412 KB", "1.2 MB". */
export function fileSize(bytes: number | null | undefined): string {
  if (!bytes) return "";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export function fileKind(type: string | null | undefined): string {
  if (!type) return "File";
  if (type === "application/pdf") return "PDF";
  return (type.split("/")[1] ?? "file").toUpperCase().replace("JPEG", "JPG");
}

/** Overlay/Admin/ImageViewer's line: "Image · PNG · 420 KB · sent 1 day ago". */
export function attachmentMeta(type: string | null | undefined, size: number | null | undefined, at: string, now: number): string {
  const s = Math.max(0, Math.round((now - new Date(at).getTime()) / 1000));
  const when =
    s < 60 ? "just now" : s < 3600 ? `${Math.floor(s / 60)} min ago` : s < 86_400 ? `${Math.floor(s / 3600)} h ago` : Math.floor(s / 86_400) === 1 ? "1 day ago" : `${Math.floor(s / 86_400)} days ago`;
  const image = (type ?? "").startsWith("image/");
  return [image ? "Image" : null, fileKind(type), fileSize(size), `sent ${when}`].filter(Boolean).join(" · ");
}

type Party = { id?: string | null; name?: string | null };

/**
 * An event line ("closed", "reopened", "support:SUP-1A2B3C4D") for a viewer.
 * `side` is who is looking: staff see "you" for their own actions and names for
 * colleagues; members see "Bluntly" for any staff action.
 */
export function eventText(
  body: string,
  author: Party | null,
  fromStaff: boolean,
  viewer: { id: string; side: "staff" | "member" },
  at: string,
  now?: number,
): string {
  const mine = !!author?.id && author.id === viewer.id;
  const who = mine ? "you" : viewer.side === "member" ? (fromStaff ? "Bluntly" : "you") : author?.name || "the member";
  const when = now === undefined ? dayLabel(at) : stampLabel(at, now);
  // Confirm/Messages/Resolve: a member closing their own reads as resolving it.
  if (body === "closed") return fromStaff ? `Closed by ${who} · ${when}` : `Marked as resolved by ${who} · ${when}`;
  if (body === "reopened") return `Opened again by ${who} · ${when}`;
  // MQA-030: the team's queue names and ticket codes are theirs, not the member's.
  if (body.startsWith("support:"))
    return viewer.side === "member"
      ? `Your request was passed to our support team · ${when}`
      : `Moved to Queue → Support (${body.slice(8)}) · ${when}`;
  return `${body} · ${when}`;
}

/** The line under a closed thread (Figma Screen/Admin/Inbox/Closed, Seller/Inbox/Closed). */
export function closedNote(
  closedBy: Party | null | undefined,
  closedAt: string | null | undefined,
  viewer: { id: string; side: "staff" | "member" },
  memberName: string | null | undefined,
): string {
  const when = closedAt ? ` on ${dayLabel(closedAt)}` : "";
  const mine = !!closedBy?.id && closedBy.id === viewer.id;
  if (viewer.side === "staff") {
    const by = mine ? "you" : closedBy?.name || "the member";
    return `Closed by ${by}${when}. If ${firstName(memberName)} replies, it opens again.`;
  }
  const by = mine ? "you" : "Bluntly";
  return `Closed by ${by}${when}. Reply to open it again.`;
}

/** List titles: staff read "{party} · {topic}", members read "{topic} · {subject}". */
export function staffTitle(row: { audience: string; seller_name?: string | null; member: Party; topic: string }): string {
  const party = row.audience === "seller" ? row.seller_name || row.member?.name || "A store" : row.member?.name || "A member";
  return `${party} · ${TOPIC_LABEL[row.topic as Topic] ?? "General"}`;
}

export function memberTitle(row: { topic: string; subject: string }): string {
  return `${TOPIC_LABEL[row.topic as Topic] ?? "General"} · ${row.subject}`;
}

/** "Zient: Thank you…" / "You: …" for staff; "Bluntly: …" / "You: …" for members. */
export function previewLine(
  row: { preview?: string | null; preview_from_staff?: boolean; member: Party },
  side: "staff" | "member",
): string {
  if (!row.preview) return "";
  const staffWrote = !!row.preview_from_staff;
  const who = side === "staff" ? (staffWrote ? "You" : firstName(row.member?.name)) : staffWrote ? "Bluntly" : "You";
  return `${who}: ${row.preview}`;
}

/** Inbox query → href, dropping defaults so URLs stay short. */
export function inboxHref(
  q: { tab: string; topic: string; status: string; handled: string; q: string; sort: string; page: number; size: number },
  patch: Partial<{ tab: string; topic: string; status: string; handled: string; q: string; sort: string; page: number; size: number; c: string }> = {},
): string {
  const next = { ...q, page: 1, ...patch } as Record<string, string | number>;
  const p = new URLSearchParams();
  if (next.tab && next.tab !== "all") p.set("tab", String(next.tab));
  for (const k of ["topic", "status", "handled", "q"]) if (next[k]) p.set(k, String(next[k]));
  if (next.sort && next.sort !== "latest") p.set("sort", String(next.sort));
  if (Number(next.page) > 1) p.set("page", String(next.page));
  if (Number(next.size) !== 25) p.set("size", String(next.size));
  if (next.c) p.set("c", String(next.c));
  const s = p.toString();
  return s ? `/admin/inbox?${s}` : "/admin/inbox";
}

export function activeInboxFilters(q: { topic: string; status: string; handled: string }): number {
  return [q.topic, q.status, q.handled].filter(Boolean).length;
}

/**
 * MQA-011: what the viewer may do to one message. Its sender - on the side
 * they sent it from - may edit or unsend it until `change_until` (the API's
 * window, and it enforces it too); anyone may delete any message for
 * themselves. An event line or an unsent message offers nothing but that.
 */
export type MessageFacts = {
  kind: string;
  author_id?: string | null;
  from_staff: boolean;
  unsent?: boolean;
  change_until?: string | null;
  attachment?: unknown;
};

export function messageActions(
  m: MessageFacts,
  viewer: { id: string; side: "staff" | "member" },
  now: number,
): { edit: boolean; unsend: boolean; hide: boolean } {
  if (m.kind !== "message") return { edit: false, unsend: false, hide: false };
  const sender = m.author_id === viewer.id && m.from_staff === (viewer.side === "staff");
  const open = Boolean(!m.unsent && m.change_until && new Date(m.change_until).getTime() > now);
  return { edit: sender && open, unsend: sender && open, hide: true };
}

/** What a live thread compares to notice a new, edited or unsent message. */
export function threadSignature(
  messages: readonly { id: string; edited_at?: string | null; unsent?: boolean }[],
): string {
  return messages.map((m) => `${m.id}:${m.edited_at ?? ""}:${m.unsent ? 1 : 0}`).join("|");
}

/**
 * MQA-028: template tags. A reply pasted from a template can still say
 * `{{store_name}}`; the team's composers refuse to send one (the API does
 * too), and the Inbox's Templates menu fills the tags it knows from the
 * thread before the text reaches the box.
 */
const TEMPLATE_TAG = /\{\{\s*([A-Za-z0-9_ .-]*?)\s*\}\}/g;

/** The tags still unfilled in `body`, each once, as written ("{{store_name}}"). */
export function unfilledTags(body: string): string[] {
  const out: string[] = [];
  for (const m of body.matchAll(TEMPLATE_TAG)) {
    const tag = `{{${m[1]}}}`;
    if (!out.includes(tag)) out.push(tag);
  }
  return out;
}

/** "Fill in {{store_name}} and {{platform}} before sending." */
export function unfilledWarning(tags: string[]): string | null {
  if (!tags.length) return null;
  const list = tags.length === 1 ? tags[0] : `${tags.slice(0, -1).join(", ")} and ${tags.at(-1)}`;
  return `Fill in ${list} before sending.`;
}

export type TemplateContext = {
  seller_name?: string | null;
  store_name?: string | null;
  platform?: string | null;
  reference?: string | null;
};

/** The tags `ctx` knows, filled; any other tag is left for the warning to catch. */
export function fillTemplate(text: string, ctx: TemplateContext): string {
  return text.replace(TEMPLATE_TAG, (whole, name: string) => {
    const value = ctx[name.trim().toLowerCase() as keyof TemplateContext];
    return value && value.trim() ? value.trim() : whole;
  });
}

export const REPLY_TEMPLATES: { key: string; label: string; text: string }[] = [
  {
    key: "proof",
    label: "Ask for proof of ownership",
    text:
      "Hi {{seller_name}}, thanks for claiming {{store_name}} on {{platform}}. To approve it, please send a " +
      "screenshot of your {{platform}} Seller Centre showing the shop name, or your DTI or SEC registration.",
  },
  {
    key: "received",
    label: "Request received",
    text:
      "Hi {{seller_name}}, we've received your request about {{store_name}}. We'll check it against your " +
      "{{platform}} shop and reply here within one business day.",
  },
  {
    key: "more",
    label: "Ask for more details",
    text: "Hi {{seller_name}}, thanks for your message about {{store_name}}. Could you tell us a little more so we can help?",
  },
  {
    key: "done",
    label: "Done",
    text: "Hi {{seller_name}}, this is done: {{store_name}} is up to date on Bluntly. Thanks for keeping your store accurate.",
  },
];
