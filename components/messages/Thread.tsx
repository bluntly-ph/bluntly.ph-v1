"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import {
  ArrowSquareOut,
  ChatCircle,
  ChatText,
  DotsThree,
  FileText,
  Flag,
  Package,
  Paperclip,
  Plus,
  Storefront,
  Users,
  Wallet,
  Warning,
  X,
} from "@phosphor-icons/react/dist/ssr";

import { usePopover } from "@/components/console/popover";

import { ImageViewer } from "@/components/console/ImageViewer";

import { useAdaptivePoll } from "@/components/ui/useAdaptivePoll";
import { useAutoGrow } from "@/components/ui/useAutoGrow";
import {
  REPLY_MAX,
  attachmentMeta,
  eventText,
  fileKind,
  fileSize,
  messageActions,
  stampLabel,
  threadSignature,
  unfilledTags,
  unfilledWarning,
  type Topic,
} from "./messages-model";

/**
 * The thread every side shares (Figma Screen/Admin/Inbox, Screen/Seller/Inbox,
 * Screen/Messages/Thread): the other side's messages on the left in grey, the
 * viewer's side on the right in an outlined bubble, event lines centred,
 * attachments as file cards, and a composer that shows Sending… and Not sent
 * (Screen/Messages/Thread/Sending 8313:31785, /Failed 8313:31818).
 */

type Schemas = import("@/lib/api-types").components["schemas"];
type Message = Schemas["ConversationMessageOut"];
type ConversationLink = Schemas["ConversationLinkOut"];
export type Viewer = { id: string; side: "staff" | "member" };

export const TOPIC_ICON: Record<Topic, typeof Flag> = {
  appeal: Flag,
  claim: Storefront,
  product: Package,
  payout: Wallet,
  review: ChatText,
  report: Warning,
  account: Users,
  other: ChatCircle,
};

const LINK_ICON: Record<ConversationLink["type"], typeof Flag> = {
  appeal: Flag,
  claim: Storefront,
  payout: Wallet,
  review: ChatText,
  report: Warning,
  product: Package,
};

/** The grey bar under the header: what this conversation is about. */
export function ContextBar({ link, compact = false }: { link: ConversationLink; compact?: boolean }) {
  const Icon = LINK_ICON[link.type] ?? Flag;
  return (
    <div
      className={`flex items-center gap-2 bg-[var(--surface-app)] text-[12px] ${compact ? "rounded-[12px] px-3 py-2" : "px-5 py-2"}`}
      data-testid="conversation-context"
    >
      <Icon size={16} aria-hidden className="shrink-0" />
      <span className="min-w-0 flex-1 truncate">
        {link.label}
        {link.status ? ` · ${link.status}` : ""}
      </span>
      {link.href ? (
        <Link href={link.href} className="shrink-0 text-[var(--chart-honesty-fund)] hover:underline">
          {link.action ?? "Open"}
        </Link>
      ) : null}
    </div>
  );
}

async function signedUrl(href: string, download = false): Promise<string | null> {
  const res = await fetch(`/api/bff${href}${download ? "?download=true" : ""}`, { cache: "no-store" }).catch(() => null);
  return res?.ok ? (((await res.json()) as { url?: string }).url ?? null) : null;
}

/**
 * A file sent with a message. An image opens in the image viewer
 * (Overlay/Admin/ImageViewer 8237:25416); a PDF opens in a new tab. Either way
 * the link is a 5-minute signed URL fetched on click, never kept in the page.
 */
export function AttachmentCard({ href, name, type, size, at, now }: { href: string; name: string; type: string; size?: number | null; at: string; now: number }) {
  const [error, setError] = useState(false);
  const [viewer, setViewer] = useState<{ src: string | null; error: string | null } | null>(null);
  const image = type.startsWith("image/");
  async function open() {
    setError(false);
    if (image) {
      setViewer({ src: null, error: null });
      const url = await signedUrl(href);
      setViewer(url ? { src: url, error: null } : { src: null, error: "This image couldn’t be opened. It may no longer be available." });
      return;
    }
    const url = await signedUrl(href);
    if (url) window.open(url, "_blank", "noopener");
    else setError(true);
  }
  return (
    <>
      <button
        type="button"
        onClick={() => void open()}
        className="mt-2 flex w-full max-w-[256px] items-center gap-3 rounded-[12px] border border-[var(--border-subtle)] bg-[var(--surface-card)] p-2 text-left hover:border-[var(--text-secondary)]"
      >
        <span className="grid size-10 shrink-0 place-items-center rounded-[8px] bg-[var(--surface-app)]" aria-hidden>
          <FileText size={18} />
        </span>
        <span className="flex min-w-0 flex-1 flex-col gap-1 leading-none">
          <span className="truncate text-[14px]">{name}</span>
          <span className="text-[12px] text-[var(--text-secondary)]">
            {error ? "Couldn’t open it" : [fileKind(type), fileSize(size)].filter(Boolean).join(" · ")}
          </span>
        </span>
        {image ? null : <ArrowSquareOut size={16} aria-hidden className="shrink-0" />}
        <span className="sr-only">{image ? "(opens the image)" : "(opens in a new tab)"}</span>
      </button>
      {viewer ? (
        <ImageViewer
          title={name}
          src={viewer.src}
          alt={`Attachment: ${name}`}
          meta={attachmentMeta(type, size, at, now)}
          error={viewer.error}
          onDownload={() => signedUrl(href, true)}
          onClose={() => setViewer(null)}
        />
      ) : null}
    </>
  );
}

/**
 * MQA-014: new messages appear without a page refresh. While the page is
 * visible, read the open thread and refresh the server component (the list,
 * the counts and the thread) only when its newest message changed — a quiet
 * thread costs one small read per tick and no re-render. Paused in a
 * background tab; caught up as soon as the tab is visible again.
 *
 * Adaptive (components/ui/useAdaptivePoll.ts): every `every` ms while the
 * reader is active or the thread is changing, backing off to 30 s while it is
 * quiet, and to 2 min once the reader has been idle for 10 min. Each tick is a
 * billed function call on both services, so the old fixed 4 s poll cost
 * ~900 per hour per open tab even when nobody was typing.
 */
export function useLiveThread(path: string | null, signature: string | null, every = 5000) {
  const router = useRouter();
  useAdaptivePoll(
    async () => {
      if (!path) return false;
      const res = await fetch(`/api/bff${path}`, { cache: "no-store" }).catch(() => null);
      if (!res?.ok) return false;
      type Row = { id: string; edited_at?: string | null; unsent?: boolean };
      const body = (await res.json().catch(() => null)) as { messages?: Row[] } | Row[] | null;
      const list = Array.isArray(body) ? body : (body?.messages ?? []);
      // MQA-011: an edit or an unsend on the other side refreshes it too.
      if (threadSignature(list) === signature) return false;
      router.refresh();
      return true;
    },
    { base: every, max: 30_000, idleAfter: 600_000, idleInterval: 120_000, enabled: Boolean(path) },
    `${path}|${signature}`,
  );
}

export type Pending = { key: string; body: string; fileName: string | null; state: "sending" | "failed" };

/**
 * One message, and what its viewer may do to it (MQA-011): Edit and Unsend
 * for its sender while the API's window is open, Delete for me for anyone.
 * Unsend and Delete for me ask once more in the menu; Edit opens the words in
 * place. Each answer refreshes the thread from the server.
 */
function MessageItem({
  m,
  mine,
  label,
  viewer,
  now,
  actionsBase,
}: {
  m: Message;
  mine: boolean;
  label: string;
  viewer: Viewer;
  now: number;
  actionsBase?: string;
}) {
  const router = useRouter();
  const { open, setOpen, ref } = usePopover();
  const [confirm, setConfirm] = useState<"unsend" | "hide" | null>(null);
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(m.body);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const editRef = useRef<HTMLTextAreaElement>(null);
  useAutoGrow(editRef, draft, 200);
  const can = actionsBase ? messageActions(m, viewer, now) : { edit: false, unsend: false, hide: false };
  const any = can.edit || can.unsend || can.hide;

  async function act(path: string, init: RequestInit) {
    setBusy(true);
    setError(null);
    const res = await fetch(`${actionsBase}/messages/${m.id}${path}`, init).catch(() => null);
    setBusy(false);
    if (!res?.ok) {
      const p = res ? ((await res.json().catch(() => ({}))) as { detail?: unknown }) : {};
      setError(typeof p.detail === "string" ? p.detail : "Couldn't do that. Try again.");
      return false;
    }
    setOpen(false);
    setConfirm(null);
    setEditing(false);
    router.refresh();
    return true;
  }

  const save = () =>
    void act("", {
      method: "PATCH",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ body: draft.trim() }),
    });

  return (
    <li className={`flex flex-col gap-1 ${mine ? "items-end" : "items-start"}`} data-testid="thread-message" data-message-id={m.id} data-mine={mine} data-unsent={m.unsent || undefined}>
      {editing ? (
        <div className="flex w-[min(420px,85%)] flex-col gap-2">
          <label htmlFor={`edit-${m.id}`} className="sr-only">
            Edit your message
          </label>
          <textarea
            id={`edit-${m.id}`}
            ref={editRef}
            value={draft}
            maxLength={REPLY_MAX}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Escape") setEditing(false);
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                save();
              }
            }}
            rows={2}
            className="w-full resize-none rounded-[16px] border border-[var(--accent-primary)] bg-[var(--surface-card)] px-3 py-[10px] text-[14px] leading-[21px] outline-none [overflow-wrap:anywhere]"
          />
          <span className="flex justify-end gap-2">
            <button type="button" onClick={() => setEditing(false)} className="h-8 rounded-full px-3 text-[12px] text-[var(--text-secondary)] hover:text-[var(--text-primary)]">
              Cancel
            </button>
            <button
              type="button"
              disabled={busy || (!draft.trim() && !m.attachment) || draft.trim() === m.body}
              onClick={save}
              className="h-8 rounded-full bg-[var(--accent-primary)] px-3 text-[12px] text-white disabled:opacity-50"
            >
              {busy ? "Saving…" : "Save"}
            </button>
          </span>
        </div>
      ) : m.unsent ? (
        <div className="max-w-[min(420px,85%)] rounded-[16px] border border-dashed border-[var(--border-subtle)] px-3 py-[10px] text-[14px] italic leading-[21px] text-[var(--text-secondary)]">
          {mine && m.author_id === viewer.id ? "You unsent a message." : "This message was unsent."}
        </div>
      ) : (
        <div
          className={`max-w-[min(420px,85%)] whitespace-pre-wrap break-words rounded-[16px] px-3 py-[10px] text-[14px] leading-[21px] ${
            mine ? "border border-[var(--text-primary)] bg-[var(--surface-card)]" : "bg-[var(--surface-app)]"
          }`}
        >
          {m.body}
          {m.attachment ? <AttachmentCard {...m.attachment} at={m.created_at} now={now} /> : null}
        </div>
      )}
      <span className={`flex items-center gap-1 text-[12px] text-[var(--text-secondary)] ${mine ? "flex-row-reverse" : ""}`}>
        <span suppressHydrationWarning>
          {label} · {stampLabel(m.created_at, now)}
          {m.edited_at && !m.unsent ? " · Edited" : ""}
        </span>
        {any && !editing ? (
          <span ref={ref} className="relative">
            <button
              type="button"
              aria-label="Message options"
              aria-haspopup="menu"
              aria-expanded={open}
              onClick={() => {
                setOpen(!open);
                setConfirm(null);
                setError(null);
              }}
              className="grid size-6 place-items-center rounded-full hover:bg-[var(--surface-app)] focus-visible:outline focus-visible:outline-2 focus-visible:outline-[var(--accent-primary)]"
            >
              <DotsThree size={16} weight="bold" />
            </button>
            {open ? (
              <span
                role="menu"
                className={`absolute bottom-[calc(100%+4px)] z-30 flex w-[220px] flex-col rounded-[12px] border border-[var(--border-subtle)] bg-[var(--surface-card)] py-1 text-[13px] text-[var(--text-primary)] shadow-[var(--shadow-modal)] ${mine ? "right-0" : "left-0"}`}
              >
                {confirm ? (
                  <span className="flex flex-col gap-2 px-3 py-2">
                    <span>
                      {confirm === "unsend"
                        ? "Unsend for everyone? The message and its file leave the thread."
                        : "Delete for you? Others in the thread still see it."}
                    </span>
                    <span className="flex justify-end gap-2">
                      <button type="button" onClick={() => setConfirm(null)} className="h-7 rounded-full px-2 text-[12px] text-[var(--text-secondary)]">
                        Cancel
                      </button>
                      <button
                        type="button"
                        role="menuitem"
                        disabled={busy}
                        onClick={() => void act(confirm === "unsend" ? "/unsend" : "/hide", { method: "POST" })}
                        className="h-7 rounded-full bg-[var(--accent-danger)] px-3 text-[12px] text-white disabled:opacity-50"
                      >
                        {busy ? "…" : confirm === "unsend" ? "Unsend" : "Delete"}
                      </button>
                    </span>
                  </span>
                ) : (
                  <>
                    {can.edit ? (
                      <button type="button" role="menuitem" onClick={() => { setDraft(m.body); setEditing(true); setOpen(false); }} className="px-3 py-2 text-left hover:bg-[var(--surface-app)]">
                        Edit
                      </button>
                    ) : null}
                    {can.unsend ? (
                      <button type="button" role="menuitem" onClick={() => setConfirm("unsend")} className="px-3 py-2 text-left hover:bg-[var(--surface-app)]">
                        Unsend for everyone
                      </button>
                    ) : null}
                    {can.hide ? (
                      <button type="button" role="menuitem" onClick={() => setConfirm("hide")} className="px-3 py-2 text-left hover:bg-[var(--surface-app)]">
                        Delete for me
                      </button>
                    ) : null}
                    {can.edit ? (
                      <span className="px-3 pb-1 pt-1 text-[11px] text-[var(--text-secondary)]">You can edit or unsend for 15 minutes after sending.</span>
                    ) : null}
                  </>
                )}
                {error ? (
                  <span role="alert" className="px-3 pb-2 text-[12px] text-[var(--accent-danger)]">
                    {error}
                  </span>
                ) : null}
              </span>
            ) : null}
          </span>
        ) : null}
      </span>
      {error && !open ? (
        <span role="alert" className="text-[12px] text-[var(--accent-danger)]">
          {error}
        </span>
      ) : null}
    </li>
  );
}

/** The messages, oldest first, scrolled to the newest. */
export function ThreadMessages({
  messages,
  viewer,
  now,
  nameOf,
  pending = [],
  onRetry,
  actionsBase,
}: {
  messages: Message[];
  viewer: Viewer;
  now: number;
  /**
   * MQA-011: the conversation's API path through the BFF
   * (`/api/bff/api/v1/conversations/<id>` or `/api/bff/api/v1/admin/inbox/<id>`).
   * With it each message offers Edit / Unsend to its sender and Delete for me
   * to anyone; without it the thread is read-only.
   */
  actionsBase?: string;
  /** The label under the other side's bubbles ("Zient P. · Jisulife Official", "Mara · Bluntly"). */
  nameOf: (m: Message) => string;
  pending?: Pending[];
  onRetry?: (p: Pending) => void;
}) {
  const end = useRef<HTMLDivElement>(null);
  const count = messages.length + pending.length;
  useEffect(() => {
    end.current?.scrollIntoView({ block: "end" });
  }, [count]);
  return (
    <ol className="flex flex-col gap-4 px-5 py-4" aria-label="Messages" aria-live="polite">
      {messages.map((m) => {
        if (m.kind === "event") {
          return (
            <li key={m.id} className="text-center text-[12px] text-[var(--text-secondary)]" data-testid="thread-event" suppressHydrationWarning>
              {eventText(m.body, { id: m.author_id, name: m.author_name }, m.from_staff, viewer, m.created_at, now)}
            </li>
          );
        }
        const mine = viewer.side === "staff" ? m.from_staff : !m.from_staff;
        const label = mine
          ? viewer.side === "staff" && m.author_id !== viewer.id
            ? `${m.author_name ?? "Staff"}`
            : "You"
          : nameOf(m);
        return (
          <MessageItem key={m.id} m={m} mine={mine} label={label} viewer={viewer} now={now} actionsBase={actionsBase} />
        );
      })}
      {pending.map((p) => (
        <li key={p.key} className="flex flex-col items-end gap-1" data-testid="thread-pending">
          <div
            className={`max-w-[min(420px,85%)] whitespace-pre-wrap break-words rounded-[16px] border px-3 py-[10px] text-[14px] leading-[21px] ${
              p.state === "failed" ? "border-[var(--accent-danger)]" : "border-[var(--text-primary)] opacity-60"
            }`}
          >
            {p.body}
            {p.fileName ? <span className="mt-1 block text-[12px] text-[var(--text-secondary)]">+ {p.fileName}</span> : null}
          </div>
          {p.state === "failed" ? (
            <button type="button" onClick={() => onRetry?.(p)} className="text-[12px] text-[var(--accent-danger)] hover:underline">
              Not sent · Tap to retry
            </button>
          ) : (
            <span className="text-[12px] text-[var(--text-secondary)]">Sending…</span>
          )}
        </li>
      ))}
      <div ref={end} />
    </ol>
  );
}

/**
 * The reply box. `post` sends one message (multipart: body, optional file);
 * the parent shows the pending bubble and refreshes on success.
 */
export function Composer({
  placeholder,
  onSend,
  disabled = false,
  attachMenu,
  templates,
  guardTags = false,
}: {
  placeholder: string;
  onSend: (body: string, file: File | null) => void;
  disabled?: boolean;
  /** Extra items under "+" (Menu/Composer/Attach: Link a review, Link a product). */
  attachMenu?: { label: string; onSelect: () => void }[];
  /** MQA-028: replies to insert, their tags already filled from the thread. */
  templates?: { label: string; text: string }[];
  /** MQA-028: refuse to send while a `{{tag}}` is unfilled (the team's side). */
  guardTags?: boolean;
}) {
  const [body, setBody] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const input = useRef<HTMLInputElement>(null);
  const box = useRef<HTMLTextAreaElement>(null);
  useAutoGrow(box, body, 160);
  const { open, setOpen, ref } = usePopover();
  const { open: pickerOpen, setOpen: setPickerOpen, ref: pickerRef } = usePopover();
  const tags = guardTags ? unfilledTags(body) : [];
  const warning = unfilledWarning(tags);
  // Words, a file, or both (MQA-009: proof sent with nothing to add).
  const ready = (body.trim().length > 0 || file !== null) && !disabled && tags.length === 0;

  function insert(text: string) {
    setBody((now) => (now.trim() ? `${now.trimEnd()}\n\n${text}` : text));
    setPickerOpen(false);
    box.current?.focus();
  }

  function send() {
    if (!ready) return;
    onSend(body.trim(), file);
    setBody("");
    setFile(null);
  }

  return (
    <div className="border-t border-[var(--border-subtle)] px-5 py-4">
      {file ? (
        <div className="mb-2 flex w-fit items-center gap-2 rounded-full bg-[var(--surface-app)] py-1 pl-3 pr-1 text-[12px]">
          <Paperclip size={14} aria-hidden />
          <span className="max-w-[220px] truncate">{file.name}</span>
          <button type="button" aria-label="Remove attachment" onClick={() => setFile(null)} className="grid size-6 place-items-center rounded-full hover:bg-[var(--surface-card)]">
            <X size={12} />
          </button>
        </div>
      ) : null}
      {templates?.length ? (
        <div ref={pickerRef} className="relative mb-2">
          <button
            type="button"
            aria-haspopup="menu"
            aria-expanded={pickerOpen}
            onClick={() => setPickerOpen(!pickerOpen)}
            className="inline-flex h-7 items-center gap-1 rounded-full border border-[var(--border-subtle)] px-3 text-[12px] hover:bg-[var(--surface-app)]"
          >
            <ChatText size={14} aria-hidden /> Templates
          </button>
          {pickerOpen ? (
            <ul role="menu" className="absolute bottom-[calc(100%+6px)] left-0 z-30 w-[300px] max-w-[calc(100vw-48px)] rounded-[16px] border border-[var(--border-subtle)] bg-[var(--surface-card)] p-2 shadow-[var(--shadow-modal)]">
              {templates.map((t) => (
                <li key={t.label} role="none">
                  <button
                    type="button"
                    role="menuitem"
                    onClick={() => insert(t.text)}
                    className="flex w-full flex-col gap-0.5 rounded-[10px] px-3 py-2 text-left hover:bg-[var(--surface-app)]"
                  >
                    <span className="text-[14px]">{t.label}</span>
                    <span className="line-clamp-2 text-[12px] text-[var(--text-secondary)]">{t.text}</span>
                  </button>
                </li>
              ))}
            </ul>
          ) : null}
        </div>
      ) : null}
      <div
        className={`flex items-end gap-2 rounded-[16px] border py-1 pl-4 pr-1 focus-within:border-[var(--accent-primary)] ${
          warning ? "border-[var(--accent-danger)]" : "border-[var(--line-hairline-30)]"
        }`}
      >
        <textarea
          ref={box}
          value={body}
          rows={1}
          maxLength={REPLY_MAX}
          aria-invalid={warning ? true : undefined}
          aria-describedby={warning ? "composer-tags" : undefined}
          aria-label={placeholder}
          placeholder={placeholder}
          onChange={(e) => setBody(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              send();
            }
          }}
          className="min-h-[38px] min-w-0 flex-1 resize-none bg-transparent py-[8px] text-[14px] leading-[21px] outline-none"
        />
        <div ref={ref} className="relative">
          <button
            type="button"
            aria-label="Attach"
            aria-expanded={attachMenu ? open : undefined}
            onClick={() => (attachMenu ? setOpen(!open) : input.current?.click())}
            className="grid size-9 place-items-center rounded-full hover:bg-[var(--surface-app)]"
          >
            <Plus size={18} />
          </button>
          {attachMenu && open ? (
            <ul role="menu" className="absolute bottom-[calc(100%+6px)] right-0 z-30 w-[240px] rounded-[16px] border border-[var(--border-subtle)] bg-[var(--surface-card)] p-2 shadow-[var(--shadow-modal)]">
              <li role="none">
                <button
                  type="button"
                  role="menuitem"
                  onClick={() => {
                    setOpen(false);
                    input.current?.click();
                  }}
                  className="w-full rounded-[10px] px-3 py-[10px] text-left text-[14px] hover:bg-[var(--surface-app)]"
                >
                  Upload a file or photo
                </button>
              </li>
              {attachMenu.map((item) => (
                <li key={item.label} role="none">
                  <button
                    type="button"
                    role="menuitem"
                    onClick={() => {
                      setOpen(false);
                      item.onSelect();
                    }}
                    className="w-full rounded-[10px] px-3 py-[10px] text-left text-[14px] hover:bg-[var(--surface-app)]"
                  >
                    {item.label}
                  </button>
                </li>
              ))}
            </ul>
          ) : null}
        </div>
        <input
          ref={input}
          type="file"
          accept="image/png,image/jpeg,image/webp,application/pdf"
          aria-label="Attachment"
          className="hidden"
          onChange={(e) => {
            setFile(e.target.files?.[0] ?? null);
            e.target.value = "";
          }}
        />
        <button
          type="button"
          disabled={!ready}
          onClick={send}
          className={`h-9 shrink-0 rounded-full px-4 text-[12px] ${ready ? "bg-[var(--accent-primary)] text-white" : "bg-[var(--surface-app)] text-[var(--text-secondary)]"}`}
        >
          Send
        </button>
      </div>
      {warning ? (
        <p id="composer-tags" role="alert" data-testid="composer-tags" className="mt-1 text-[12px] text-[var(--accent-danger)]">
          {warning}
        </p>
      ) : null}
    </div>
  );
}

/** Pending bubbles + posting, for a thread whose messages come from the server. */
export function useSender(post: (body: string, file: File | null) => Promise<{ ok: true } | { ok: false; error: string }>) {
  const router = useRouter();
  const [pending, setPending] = useState<Pending[]>([]);
  const [error, setError] = useState<string | null>(null);
  const files = useRef(new Map<string, File | null>());

  async function run(p: Pending) {
    setPending((list) => [...list.filter((x) => x.key !== p.key), { ...p, state: "sending" }]);
    const result = await post(p.body, files.current.get(p.key) ?? null);
    if (result.ok) {
      files.current.delete(p.key);
      router.refresh();
      setPending((list) => list.filter((x) => x.key !== p.key));
      setError(null);
    } else {
      setError(result.error);
      setPending((list) => list.map((x) => (x.key === p.key ? { ...x, state: "failed" } : x)));
    }
  }

  function send(body: string, file: File | null) {
    const key = `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
    files.current.set(key, file);
    void run({ key, body, fileName: file?.name ?? null, state: "sending" });
  }

  return { pending, error, send, retry: (p: Pending) => void run(p) };
}

/** POST a message (multipart) to a BFF path; the API's sentence on failure. */
export async function postMessage(path: string, body: string, file: File | null): Promise<{ ok: true } | { ok: false; error: string }> {
  const form = new FormData();
  form.append("body", body);
  if (file) form.append("file", file);
  try {
    const res = await fetch(`/api/bff${path}`, { method: "POST", body: form });
    if (res.ok) return { ok: true };
    const p = (await res.json().catch(() => ({}))) as { detail?: unknown };
    return { ok: false, error: typeof p.detail === "string" ? p.detail : "Your message wasn’t sent." };
  } catch {
    return { ok: false, error: "You’re offline. Messages send when you’re back online." };
  }
}
