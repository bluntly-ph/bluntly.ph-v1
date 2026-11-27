"use client";

import Image from "next/image";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { ArrowLeft, Bell, ChatCircleDots, CheckCircle, DotsThree } from "@phosphor-icons/react/dist/ssr";

import { ConfirmDialog } from "@/components/admin/ConfirmDialog";

import { MemberRow } from "./MemberMessages";
import { memberTitle, threadSignature } from "./messages-model";
import { Composer, ContextBar, ThreadMessages, postMessage, useLiveThread, useSender } from "./Thread";

/**
 * Screen/Messages (Figma 8296:31219) and its states — Empty 8296:31548, Thread
 * 8296:31305, Sent 8296:31467, Closed 8313:31715 / Thread/Closed 8313:31853,
 * Thread/Sending 8313:31785, Thread/Failed 8313:31818, Loading 8313:31968 —
 * with Sheet/Messages/More (8313:32059), Confirm/Messages/Resolve
 * (8313:32146) and Toast/Messages/Copy sent (8313:32156): a reviewer and the
 * Bluntly team, on a phone first.
 */

type Schemas = import("@/lib/api-types").components["schemas"];
type MemberList = Schemas["MemberListOut"];
type Conversation = Schemas["ConversationDetailOut"];

/** The light top bar of the Messages frames: back, and the member's avatar. */
export function MessagesNav({ backHref, avatarUrl, name }: { backHref: string; avatarUrl: string | null; name: string }) {
  return (
    <div className="flex h-[64px] items-center justify-between bg-[var(--surface-app)] px-5">
      <Link href={backHref} aria-label="Back" className="-ml-1 rounded-full p-1">
        <ArrowLeft size={26} />
      </Link>
      <Link href="/profile" aria-label="Your profile" className="block size-9 overflow-hidden rounded-full bg-[var(--surface-card)]">
        {avatarUrl ? (
          <Image src={avatarUrl} alt="" width={36} height={36} unoptimized className="size-9 object-cover" />
        ) : (
          <span className="grid size-9 place-items-center text-[14px] font-medium">{name.replace(/^@/, "").slice(0, 1).toUpperCase()}</span>
        )}
      </Link>
    </div>
  );
}

export function ReviewerMessagesList({ status, list, now }: { status: "open" | "closed"; list: MemberList | null; now: number }) {
  const items = list?.items ?? [];
  const none = list !== null && list.counts.open + list.counts.closed === 0;
  const chip = (on: boolean) =>
    `rounded-full border px-3 py-[7px] text-[12px] ${on ? "border-[var(--accent-primary)] bg-[var(--status-high-bg)] text-[var(--accent-primary)]" : "border-[var(--border-subtle)]"}`;
  return (
    <div className="flex flex-1 flex-col gap-4 px-4 pb-28 pt-2">
      <div className="flex flex-col gap-2">
        <h1 className="text-[24px] font-semibold leading-none">Messages</h1>
        <p className="text-[14px] text-[var(--text-secondary)]">Talk to the Bluntly team. We reply within 1 business day.</p>
      </div>
      {none ? (
        <div className="flex flex-col items-center gap-2 rounded-[16px] border border-[var(--border-subtle)] px-6 py-10 text-center" data-testid="messages-empty">
          <ChatCircleDots size={24} aria-hidden />
          <p className="text-[14px] font-medium">No messages yet</p>
          <p className="text-[12px] text-[var(--text-secondary)]">Questions about a payout, a review you wrote or your account? Ask us here.</p>
        </div>
      ) : (
        <>
          <nav aria-label="Message views" className="flex gap-2">
            <Link href="/messages" aria-current={status === "open" ? "page" : undefined} className={chip(status === "open")}>
              Open · {list?.counts.open ?? 0}
            </Link>
            <Link href="/messages?status=closed" aria-current={status === "closed" ? "page" : undefined} className={chip(status === "closed")}>
              Closed · {list?.counts.closed ?? 0}
            </Link>
          </nav>
          {list === null ? (
            <p role="alert" className="text-[14px] text-[var(--text-secondary)]">Your messages couldn’t be loaded. Try again in a moment.</p>
          ) : items.length === 0 ? (
            <p className="rounded-[16px] border border-[var(--border-subtle)] px-4 py-6 text-center text-[12px] text-[var(--text-secondary)]">
              {status === "open" ? "Nothing open. Use New message to ask something." : "Nothing closed yet."}
            </p>
          ) : (
            <ul className="flex flex-col gap-2">
              {items.map((row) => (
                <MemberRow key={row.id} row={row} active={false} href={`/messages/${row.id}`} now={now} card />
              ))}
            </ul>
          )}
          <p className="text-[12px] text-[var(--text-secondary)]">Questions about another reviewer or a product? Report it from the review instead.</p>
        </>
      )}
      <div className="fixed inset-x-0 bottom-0 z-20 mx-auto w-full max-w-[480px] bg-gradient-to-t from-[var(--surface-card)] via-[var(--surface-card)] px-4 pb-6 pt-4">
        <Link href="/messages/new" className="block h-12 w-full rounded-full bg-[var(--accent-primary)] text-center text-[16px] font-medium leading-[48px] text-white">
          New message
        </Link>
      </div>
    </div>
  );
}

/**
 * MQA-031: the list beside the conversation on a wide screen (lg and up) -
 * the same rows, the open one marked, each a link so the URL follows the
 * conversation. A phone never shows it: there a conversation is its own page
 * with a back arrow.
 */
export function MessagesRail({
  status,
  list,
  activeId,
  now,
}: {
  status: "open" | "closed";
  list: MemberList | null;
  activeId: string | null;
  now: number;
}) {
  const items = list?.items ?? [];
  const chip = (on: boolean) =>
    `rounded-full border px-3 py-[5px] text-[12px] ${on ? "border-[var(--accent-primary)] bg-[var(--status-high-bg)] text-[var(--accent-primary)]" : "border-[var(--border-subtle)]"}`;
  return (
    <nav aria-label="Your conversations" data-testid="messages-rail" className="flex min-h-0 flex-1 flex-col gap-3">
      <div className="flex items-center gap-2">
        <h2 className="flex-1 text-[20px] font-semibold leading-none">Messages</h2>
        <Link href="/messages/new" className="h-8 rounded-full bg-[var(--accent-primary)] px-3 text-[12px] leading-8 text-white">
          New message
        </Link>
      </div>
      <div className="flex gap-2">
        <Link href="/messages" aria-current={status === "open" ? "page" : undefined} className={chip(status === "open")}>
          Open · {list?.counts.open ?? 0}
        </Link>
        <Link href="/messages?status=closed" aria-current={status === "closed" ? "page" : undefined} className={chip(status === "closed")}>
          Closed · {list?.counts.closed ?? 0}
        </Link>
      </div>
      {list === null ? (
        <p role="alert" className="text-[13px] text-[var(--text-secondary)]">Your messages couldn’t be loaded.</p>
      ) : items.length === 0 ? (
        <p className="text-[12px] text-[var(--text-secondary)]">{status === "open" ? "Nothing open." : "Nothing closed yet."}</p>
      ) : (
        <ul className="-mx-2 flex min-h-0 flex-1 flex-col gap-1 overflow-y-auto">
          {items.map((row) => (
            <MemberRow key={row.id} row={row} active={row.id === activeId} href={`/messages/${row.id}${status === "closed" ? "?status=closed" : ""}`} now={now} />
          ))}
        </ul>
      )}
    </nav>
  );
}

export function ReviewerThread({ conversation: c, me, now }: { conversation: Conversation; me: { id: string }; now: number }) {
  const router = useRouter();
  const sender = useSender((body, file) => postMessage(`/api/v1/conversations/${c.id}/messages`, body, file));
  useLiveThread(`/api/v1/conversations/${c.id}`, threadSignature(c.messages));
  const [sheet, setSheet] = useState(false);
  const [resolving, setResolving] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [toast, setToast] = useState<string | null>(null);
  const closed = c.status === "closed";
  const words = c.messages.filter((m) => m.kind === "message");
  const awaitingFirstReply = !closed && words.length > 0 && words.every((m) => !m.from_staff);

  useEffect(() => {
    if (!toast) return;
    const t = setTimeout(() => setToast(null), 4000);
    return () => clearTimeout(t);
  }, [toast]);

  async function emailCopy() {
    setSheet(false);
    const res = await fetch(`/api/bff/api/v1/conversations/${c.id}/email-copy`, { method: "POST" }).catch(() => null);
    if (res?.ok) setToast("We emailed you a copy of this conversation.");
    else {
      const p = res ? ((await res.json().catch(() => ({}))) as { detail?: unknown }) : {};
      setToast(typeof p.detail === "string" ? p.detail : "We couldn’t email a copy right now.");
    }
  }

  async function resolve() {
    setBusy(true);
    setError(null);
    const res = await fetch(`/api/bff/api/v1/conversations/${c.id}/resolve`, { method: "POST" }).catch(() => null);
    setBusy(false);
    if (res?.ok) {
      setResolving(false);
      router.refresh();
    } else setError("That didn’t work. Try again.");
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="flex items-start gap-3 px-4 pt-2">
        <h1 className="min-w-0 flex-1 text-[24px] font-semibold leading-[1.15] [overflow-wrap:anywhere]">{memberTitle(c)}</h1>
        <button
          type="button"
          aria-label="More"
          aria-haspopup="dialog"
          onClick={() => setSheet(true)}
          className="grid size-9 shrink-0 place-items-center rounded-full bg-[var(--surface-app)]"
        >
          <DotsThree size={20} weight="bold" />
        </button>
      </div>
      {c.link ? (
        <div className="px-4 pt-3">
          <ContextBar link={c.link} compact />
        </div>
      ) : null}
      {sender.error ? (
        <p role="alert" className="mx-4 mt-3 rounded-[12px] bg-[var(--status-high-bg)] px-3 py-2 text-[12px] text-[var(--accent-danger)]">
          {sender.error}
        </p>
      ) : null}
      <div className="min-h-0 flex-1 overflow-y-auto [&_ol]:px-4">
        <ThreadMessages
          messages={c.messages}
          viewer={{ id: me.id, side: "member" }}
          actionsBase={`/api/bff/api/v1/conversations/${c.id}`}
          now={now}
          pending={sender.pending}
          onRetry={sender.retry}
          nameOf={() => "Bluntly team"}
        />
        {awaitingFirstReply ? (
          <p className="px-4 pb-4 text-center text-[12px] text-[var(--text-secondary)]" data-testid="messages-sent-note">
            Sent. We reply within 1 business day, here and by email.
          </p>
        ) : null}
      </div>
      <div className="sticky bottom-0 bg-[var(--surface-card)] [&>div]:border-t-0 [&>div]:px-4">
        <Composer placeholder={closed ? "Reply to open it again" : "Message the Bluntly team"} onSend={sender.send} />
      </div>

      {sheet ? (
        <div className="fixed inset-0 z-50 flex items-end justify-center" role="dialog" aria-modal="true" aria-label="Conversation options">
          <div className="absolute inset-0 bg-black/40" onClick={() => setSheet(false)} aria-hidden />
          <div className="relative w-full max-w-[480px] rounded-t-[24px] bg-[var(--surface-card)] px-4 pb-6 pt-3">
            <span aria-hidden className="mx-auto mb-3 block h-1 w-10 rounded-full bg-[var(--border-subtle)]" />
            <p className="mb-2 text-[12px] text-[var(--text-secondary)]">{memberTitle(c)}</p>
            <button type="button" onClick={() => void emailCopy()} className="flex w-full items-center gap-3 py-3 text-left text-[16px]">
              <Bell size={20} aria-hidden />
              Email me a copy
            </button>
            {!closed ? (
              <button
                type="button"
                onClick={() => {
                  setSheet(false);
                  setResolving(true);
                }}
                className="flex w-full items-center gap-3 py-3 text-left text-[16px]"
              >
                <CheckCircle size={20} aria-hidden />
                Mark as resolved
              </button>
            ) : null}
          </div>
        </div>
      ) : null}

      <ConfirmDialog
        open={resolving}
        title="Mark as resolved?"
        confirmLabel="Mark as resolved"
        busyLabel="Saving…"
        busy={busy}
        error={error}
        onConfirm={() => void resolve()}
        onClose={() => setResolving(false)}
      >
        <p>The conversation moves to Closed. Reply any time to open it again.</p>
      </ConfirmDialog>

      {toast ? (
        <div role="status" className="fixed inset-x-0 bottom-24 z-50 mx-auto w-fit max-w-[calc(100%-32px)] rounded-full bg-[var(--text-primary)] px-4 py-3 text-[14px] text-[var(--surface-card)] shadow-[var(--shadow-modal)]">
          {toast}
        </div>
      ) : null}
    </div>
  );
}
