"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { AttachmentCard } from "@/components/messages/Thread";
import { useAdaptivePoll } from "@/components/ui/useAdaptivePoll";
import { useAutoGrow } from "@/components/ui/useAutoGrow";
import { relativeTime } from "@/lib/relative-time";
import { unfilledTags, unfilledWarning } from "@/components/messages/messages-model";

/**
 * The chat column of Overlay/Seller/Claim (7996:11538) and Overlay/Seller/
 * Appeal (7996:11826): GET/POST /cases/{kind}/{id}/messages. Staff messages
 * sit on the right in an outlined bubble ("You"), the member's on the left on
 * grey; the case's opening line is the first entry. The case is the Inbox
 * conversation (0076), so a file either party sent there shows as a card that
 * opens through a 5-minute signed link (image viewer for images). Sending files
 * from here ("+") is not built; staff attach them from the Inbox.
 */
export type CaseAttachment = { name: string; type: string; size?: number | null; href: string };
export type CaseMessage = {
  id: string;
  author_name: string | null;
  from_staff: boolean;
  body: string;
  sent_at: string;
  attachment?: CaseAttachment | null;
};
type Message = CaseMessage;

export function CaseChat({
  kind,
  caseId,
  opened,
  openedLabel,
  partyName,
  placeholder,
  onSent,
  onMessages,
}: {
  kind: "claim" | "appeal" | "appeal-reviewer";
  caseId: string;
  opened: string;
  openedLabel: string;
  partyName: string;
  placeholder?: string;
  onSent?: () => void;
  /** The loaded thread, for a window that lists the case's files (claim Evidence). */
  onMessages?: (messages: CaseMessage[]) => void;
}) {
  const [messages, setMessages] = useState<Message[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [body, setBody] = useState("");
  // MQA-028: a pasted template's {{tags}} must be filled before it goes out.
  const tagWarning = unfilledWarning(unfilledTags(body));
  const box = useRef<HTMLTextAreaElement>(null);
  useAutoGrow(box, body, 160);
  const [busy, setBusy] = useState(false);
  const end = useRef<HTMLDivElement>(null);
  // The clock the file cards' "sent N ago" reads, taken once when the chat opens.
  const [now] = useState(() => Date.now());

  // The thread on screen, read by `load` to tell a poll that found something
  // new (resolves true, resetting the adaptive poll) from one that did not.
  const shown = useRef<Message[] | null>(null);
  useEffect(() => {
    shown.current = messages;
  }, [messages]);

  // Resolves true when the thread changed, for the adaptive poll's back-off.
  const load = useCallback(async (): Promise<boolean> => {
    const res = await fetch(`/api/bff/api/v1/cases/${kind}/${caseId}/messages`).catch(() => null);
    if (!res || !res.ok) {
      setError("The conversation could not be loaded.");
      return false;
    }
    const next = (await res.json()) as Message[];
    // Only a changed thread re-renders (and scrolls): a poll that found nothing new is a no-op.
    const prev = shown.current;
    if (prev && prev.length === next.length && prev.at(-1)?.id === next.at(-1)?.id) return false;
    setMessages(next);
    return true;
  }, [kind, caseId]);

  useEffect(() => {
    let live = true;
    fetch(`/api/bff/api/v1/cases/${kind}/${caseId}/messages`)
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error("load"))))
      .then((m: Message[]) => live && setMessages(m))
      .catch(() => live && setError("The conversation could not be loaded."));
    return () => {
      live = false;
    };
  }, [kind, caseId]);

  // MQA-014: the case chat reads itself again while the window is visible, so
  // a reply from the other side appears without a reload. Adaptive, like the
  // Inbox thread (components/messages/Thread.tsx useLiveThread): 5 s while
  // active, backing off to 30 s while quiet and 2 min after 10 idle minutes.
  useAdaptivePoll(load, { base: 5000, max: 30_000, idleAfter: 600_000, idleInterval: 120_000 }, load);

  // A block body: newer Chrome's scrollIntoView returns a Promise, and an effect
  // that returns one hands React a "cleanup" that is not a function.
  useEffect(() => {
    end.current?.scrollIntoView({ block: "end" });
  }, [messages]);
  useEffect(() => {
    if (messages) onMessages?.(messages);
  }, [messages, onMessages]);

  async function send(e: React.FormEvent) {
    e.preventDefault();
    const text = body.trim();
    if (!text || busy) return;
    setBusy(true);
    setError(null);
    try {
      const res = await fetch(`/api/bff/api/v1/cases/${kind}/${caseId}/messages`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ body: text }),
      });
      if (!res.ok) {
        const p = (await res.json().catch(() => ({}))) as { detail?: unknown };
        setError(typeof p.detail === "string" ? p.detail : "Couldn't send that.");
        return;
      }
      setBody("");
      await load();
      onSent?.();
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex h-full min-h-[360px] flex-col">
      <div className="flex min-h-0 flex-1 flex-col justify-end gap-3 overflow-y-auto px-6 py-5" aria-live="polite">
        <p className="text-center text-[12px] text-[var(--text-secondary)]" suppressHydrationWarning>
          {openedLabel} · {relativeTime(opened)}
        </p>
        {messages?.map((m) => (
          <div key={m.id} className={`flex max-w-[80%] flex-col gap-1 ${m.from_staff ? "items-end self-end" : "items-start self-start"}`}>
            <p
              className={`whitespace-pre-wrap rounded-[16px] px-3 py-2 text-[14px] leading-[1.45] [overflow-wrap:anywhere] ${m.from_staff ? "border border-[var(--text-primary)] bg-[var(--surface-card)]" : "bg-[var(--surface-app)]"}`}
            >
              {m.body}
            </p>
            {m.attachment ? <AttachmentCard {...m.attachment} at={m.sent_at} now={now} /> : null}
            <span className="text-[11px] text-[var(--text-secondary)]" suppressHydrationWarning>
              {m.from_staff ? "You" : (m.author_name ?? partyName)} · {relativeTime(m.sent_at)}
            </span>
          </div>
        ))}
        {error ? (
          <p role="alert" className="text-center text-[12px] text-[var(--accent-danger)]">
            {error}
          </p>
        ) : null}
        <div ref={end} />
      </div>
      <form onSubmit={send} className="border-t border-[var(--border-subtle)] px-6 py-4">
        {/* Admin/Textarea states (8265:27264) on the composer box. */}
        <div className="flex items-end gap-2 rounded-[12px] border border-[var(--line-hairline-30)] py-1 pl-4 pr-1 hover:border-[var(--border-input-hover)] focus-within:border-[var(--accent-primary)] focus-within:shadow-[var(--ring-field-focus)] focus-within:hover:border-[var(--accent-primary)]">
          {/* A box that grows with the message (MQA-010) - it was one line, so a
              long request for documents could not be read back before sending.
              Enter sends; Shift+Enter starts a new line. */}
          <textarea
            ref={box}
            value={body}
            rows={1}
            onChange={(e) => setBody(e.target.value.slice(0, 2000))}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
                e.preventDefault();
                e.currentTarget.form?.requestSubmit();
              }
            }}
            placeholder={placeholder ?? `Message ${partyName}`}
            aria-label={placeholder ?? `Message ${partyName}`}
            className="min-h-9 min-w-0 flex-1 resize-none bg-transparent py-[7px] text-[14px] leading-[21px] outline-none"
          />
          <button type="submit" disabled={!body.trim() || busy || Boolean(tagWarning)} className="h-8 rounded-full bg-[var(--accent-primary)] px-4 text-[12px] text-white disabled:opacity-50">
            {busy ? "Sending…" : "Send"}
          </button>
        </div>
        {tagWarning ? (
          <p role="alert" className="mt-1 text-[12px] text-[var(--accent-danger)]">
            {tagWarning}
          </p>
        ) : null}
      </form>
    </div>
  );
}
