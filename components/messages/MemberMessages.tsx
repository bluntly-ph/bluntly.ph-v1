"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { ArrowLeft, ChatCircleDots } from "@phosphor-icons/react/dist/ssr";

import { AdminModal } from "@/components/admin/AdminModal";
import { Chip } from "@/components/console/Chip";

import { agoCompact, closedNote, firstName, memberTitle, previewLine, threadSignature, type Topic } from "./messages-model";
import { NewMessageForm } from "./NewMessageForm";
import { isOpen, statusLabel } from "@/components/sellers/support-model";
import { Composer, ContextBar, TOPIC_ICON, ThreadMessages, postMessage, useLiveThread, useSender } from "./Thread";

/**
 * Screen/Seller/Inbox (Figma 8304:32524; Closed 8305:31810, Empty 8314:32768,
 * Loading 8314:32250): a store owner's conversations with the Bluntly team, in
 * the Seller console. Open / Closed, New message (Overlay/Store/Chat/New), the
 * list and the thread; replying to a closed conversation opens it again.
 */

type Schemas = import("@/lib/api-types").components["schemas"];
type MemberList = Schemas["MemberListOut"];
type Conversation = Schemas["ConversationDetailOut"];
type Row = Schemas["ConversationRowOut"];
type LinkOption = Schemas["LinkOptionOut"];

export function SellerMessages({
  storeId,
  status,
  list,
  conversation,
  selectedId,
  explicit,
  options,
  me,
  now,
  compose,
}: {
  storeId: string;
  status: "open" | "closed";
  list: MemberList | null;
  conversation: Conversation | null;
  selectedId: string | null;
  explicit: boolean;
  options: LinkOption[];
  me: { id: string };
  now: number;
  /** ?new=1 (Contact support, "Message the team" elsewhere) opens the overlay. */
  compose: { topic?: Topic; link?: string } | null;
}) {
  const router = useRouter();
  const [composing, setComposing] = useState(compose !== null);
  const base = `/seller/${storeId}/messages`;
  const href = (p: { status?: string; c?: string }) => {
    const q = new URLSearchParams();
    const s = p.status ?? status;
    if (s !== "open") q.set("status", s);
    if (p.c) q.set("c", p.c);
    const qs = q.toString();
    return qs ? `${base}?${qs}` : base;
  };
  const items = list?.items ?? [];
  const nothingAtAll = list !== null && list.counts.open + list.counts.closed === 0;

  function closeCompose() {
    setComposing(false);
    if (compose) router.replace(href({ c: selectedId ?? undefined }), { scroll: false });
  }

  return (
    <div className="flex h-full min-h-[520px] flex-col gap-4">
      <h1 className="text-[24px] font-semibold leading-none">Messages</h1>
      <div className="flex items-center gap-3">
        <nav aria-label="Message views" className="flex w-fit gap-[2px] rounded-[10px] bg-[var(--surface-app)] p-[3px]">
          {(["open", "closed"] as const).map((s) => (
            <Link
              key={s}
              href={href({ status: s })}
              aria-current={status === s ? "page" : undefined}
              className={`flex items-center gap-[6px] rounded-[8px] px-3 py-[5px] leading-none ${
                status === s ? "bg-[var(--surface-card)] shadow-[var(--shadow-segment)]" : "text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
              }`}
            >
              <span className="text-[14px] font-medium">{s === "open" ? "Open" : "Closed"}</span>
              {list && list.counts[s] ? <span className="text-[12px] text-[var(--text-secondary)]">{list.counts[s]}</span> : null}
            </Link>
          ))}
        </nav>
        <span className="flex-1" />
        <button type="button" onClick={() => setComposing(true)} className="h-9 rounded-full bg-[var(--accent-primary)] px-4 text-[12px] text-white">
          New message
        </button>
      </div>

      <div className="flex min-h-0 flex-1 overflow-hidden rounded-[16px] border border-[var(--border-subtle)]">
        {/* MQA-031: list and thread side by side from md (the console's own
            rail is a drawer below lg, so the content has the width); a phone
            opens one conversation full screen with a back arrow. */}
        <section aria-label="Conversations" className={`${explicit ? "hidden md:flex" : "flex"} w-full min-w-0 flex-col border-[var(--border-subtle)] md:w-[280px] md:shrink-0 md:border-r xl:w-[340px]`}>
          {list === null ? (
            <p className="p-6 text-[14px] text-[var(--text-secondary)]">Your messages couldn’t be loaded. Try again in a moment.</p>
          ) : items.length === 0 ? (
            <div className="flex flex-1 flex-col items-center justify-center gap-2 p-8 text-center" data-testid="messages-empty">
              <ChatCircleDots size={24} aria-hidden />
              <p className="text-[14px] font-medium">{nothingAtAll ? "No messages yet" : status === "closed" ? "Nothing closed yet" : "Nothing open"}</p>
              <p className="max-w-[240px] text-[12px] text-[var(--text-secondary)]">
                {nothingAtAll ? "Questions about an appeal, a claim or a product page? Ask the Bluntly team." : "Use New message to start one."}
              </p>
            </div>
          ) : (
            <ul className="flex min-h-0 flex-1 flex-col gap-1 overflow-y-auto p-2">
              {items.map((row) => (
                <MemberRow key={row.id} row={row} active={row.id === selectedId} href={href({ c: row.id })} now={now} />
              ))}
            </ul>
          )}
        </section>
        <section aria-label="Conversation" className={`${explicit ? "flex" : "hidden md:flex"} min-w-0 flex-1 flex-col`}>
          {conversation ? (
            <MemberThread key={conversation.id} conversation={conversation} me={me} now={now} backHref={href({})} />
          ) : (
            <div className="flex flex-1 flex-col items-center justify-center gap-2 p-8 text-center">
              <p className="text-[16px] font-semibold">Start a conversation</p>
              <p className="text-[12px] text-[var(--text-secondary)]">Use New message. We reply within 1 business day.</p>
            </div>
          )}
        </section>
      </div>

      {composing ? (
        <AdminModal title="New message" subtitle="To the Bluntly team" width={400} onClose={closeCompose}>
          <NewMessageForm
            audience="seller"
            sellerId={storeId}
            options={options}
            initialTopic={compose?.topic}
            initialLink={compose?.link}
            onCancel={closeCompose}
            onDone={() => setComposing(false)}
            doneHref={`${base}?c=:id`}
          />
        </AdminModal>
      ) : null}
    </div>
  );
}

export function MemberRow({ row, active, href, now, card = false }: { row: Row; active: boolean; href: string; now: number; card?: boolean }) {
  const Icon = TOPIC_ICON[row.topic as Topic] ?? TOPIC_ICON.other;
  return (
    <li>
      <Link
        href={href}
        scroll={false}
        aria-current={active ? "true" : undefined}
        data-testid="message-row"
        className={`flex gap-3 px-3 py-3 ${card ? "rounded-[16px] border border-[var(--border-subtle)]" : "rounded-[12px]"} ${active ? "bg-[var(--surface-app)]" : "hover:bg-[var(--surface-app)]"}`}
      >
        <span aria-hidden className={`grid size-8 shrink-0 place-items-center rounded-full ${active ? "bg-[var(--status-high-bg)] text-[var(--accent-primary)]" : "bg-[var(--surface-app)]"}`}>
          <Icon size={16} />
        </span>
        <span className="flex min-w-0 flex-1 flex-col gap-1 leading-none">
          <span className="flex items-start gap-2">
            <span className={`min-w-0 flex-1 truncate text-[14px] ${row.unread ? "font-semibold" : "font-medium"}`}>{memberTitle(row)}</span>
            <span className="shrink-0 text-[11px] text-[var(--text-secondary)]" suppressHydrationWarning>
              {agoCompact(row.last_message_at, now)}
            </span>
          </span>
          <span className="flex items-center gap-2">
            <span className="min-w-0 flex-1 truncate text-[12px] text-[var(--text-secondary)]">{previewLine(row, "member")}</span>
            {row.unread ? (
              <span className="size-[7px] shrink-0 rounded-full bg-[var(--accent-primary)]">
                <span className="sr-only">Unread</span>
              </span>
            ) : null}
          </span>
        </span>
      </Link>
    </li>
  );
}

const STATUS_CHIP: Record<string, { label: string; tone: "success" | "warning" | "muted" }> = {
  open: { label: "Open", tone: "success" },
  waiting: { label: "Waiting on you", tone: "warning" },
  closed: { label: "Closed", tone: "muted" },
};

function MemberThread({ conversation: c, me, now, backHref }: { conversation: Conversation; me: { id: string }; now: number; backHref: string }) {
  const sender = useSender((body, file) => postMessage(`/api/v1/conversations/${c.id}/messages`, body, file));
  useLiveThread(`/api/v1/conversations/${c.id}`, threadSignature(c.messages));
  const closed = c.status === "closed";
  const handler = c.assigned_admin?.name ? `${firstName(c.assigned_admin.name)} is handling this · replies within 1 business day` : "We reply within 1 business day";
  // MQA-024: a thread that is a support request shows the request's status, in
  // the same words as the request page.
  const chip = c.support_status
    ? { label: statusLabel(c.support_status), tone: (c.support_status === "waiting_for_seller" ? "warning" : isOpen(c.support_status) ? "success" : "muted") as "success" | "warning" | "muted" }
    : (STATUS_CHIP[c.status] ?? STATUS_CHIP.open);
  return (
    <>
      <header className="flex items-center gap-3 border-b border-[var(--border-subtle)] px-5 py-3">
        <Link href={backHref} aria-label="Back to messages" className="grid size-8 place-items-center rounded-full hover:bg-[var(--surface-app)] md:hidden">
          <ArrowLeft size={18} />
        </Link>
        <span aria-hidden className="grid size-8 shrink-0 place-items-center rounded-full bg-[var(--surface-app)] text-[12px] font-medium">
          B
        </span>
        <span className="flex min-w-0 flex-1 flex-col gap-1 leading-none">
          <span className="truncate text-[16px]">Bluntly team</span>
          <span className="truncate text-[12px] text-[var(--text-secondary)]">{closed ? closedNote(c.closed_by, c.closed_at, { id: me.id, side: "member" }, null).split(".")[0] : handler}</span>
        </span>
        <Chip tone={chip.tone}>{chip.label}</Chip>
      </header>
      {c.link ? <ContextBar link={c.link} /> : null}
      {sender.error ? (
        <p role="alert" className="border-b border-[var(--border-subtle)] px-5 py-2 text-[12px] text-[var(--accent-danger)]">
          {sender.error}
        </p>
      ) : null}
      <div className="min-h-0 flex-1 overflow-y-auto">
        <ThreadMessages
          messages={c.messages}
          viewer={{ id: me.id, side: "member" }}
          actionsBase={`/api/bff/api/v1/conversations/${c.id}`}
          now={now}
          pending={sender.pending}
          onRetry={sender.retry}
          nameOf={(m) => `${firstName(m.author_name)} · Bluntly`}
        />
      </div>
      <Composer placeholder={closed ? "Reply to open it again" : "Message the Bluntly team"} onSend={sender.send} />
    </>
  );
}
