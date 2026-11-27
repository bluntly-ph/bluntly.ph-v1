"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useId, useState } from "react";
import {
  ArrowsClockwise,
  CaretDown,
  CheckCircle,
  Storefront,
  WarningCircle,
  XCircle,
} from "@phosphor-icons/react/dist/ssr";

import { AdminModal } from "@/components/admin/AdminModal";

import { relativeAge } from "@/components/admin/review-queue-model";
import { countState } from "@/components/console/counted-model";
import { CountedTextarea } from "@/components/console/CountedTextarea";
import { categoryLabel, isOpen, statusLabel, waitingOnTeam } from "@/components/sellers/support-model";
import type { AdminSupportRequest } from "@/lib/support";
import { unfilledTags, unfilledWarning } from "@/components/messages/messages-model";
import { DROPDOWN_PILL_STATES } from "@/components/ui/search-styles";

type View = "waiting" | "seller" | "closed" | "all";

// MQA-022: requests waiting on the team, and those waiting on the seller, apart.
const VIEWS: { key: View; label: string }[] = [
  { key: "waiting", label: "Waiting on us" },
  { key: "seller", label: "Waiting for seller" },
  { key: "closed", label: "Closed" },
  { key: "all", label: "All" },
];

const STATUSES = ["open", "in_review", "waiting_for_seller", "resolved", "rejected"] as const;

/** MQA-022: one choice when replying - what happens next. */
const REPLY_ACTIONS: { key: "ask" | "review" | "resolve"; label: string; hint: string }[] = [
  { key: "ask", label: "Ask for more information", hint: "Waiting for seller: they see “Waiting on you”" },
  { key: "review", label: "Keep it in review", hint: "You still have work to do" },
  { key: "resolve", label: "Resolve", hint: "Done; their reply opens it again" },
];
/** The API caps a reply and an internal note at 4,000 characters. */
const TEXT_MAX = 4000;

/**
 * The console's Support tab (owner decision 2026-09-28): claimed sellers'
 * requests to the administrators.
 *
 * The frame (6922:837) draws the tab and nothing behind it, so the body reuses
 * the Answers tab's own layout — a list on the left, the selected item's
 * detail on the right — and this console's panel and pill vocabulary.
 *
 * Three actions, each its own audited API call: take the request, answer the
 * seller (optionally moving the status), and set the status with a note only
 * staff can read. Nothing here acts on content: a takedown that follows is a
 * separate decision on the Reviews tab.
 */
export function SupportQueue({ requests, now }: { requests: AdminSupportRequest[] | null; now: number }) {
  const [view, setView] = useState<View>("waiting");
  const [selectedId, setSelectedId] = useState<string | null>(null);

  if (requests === null) {
    return (
      <p className="mt-4 text-[14px] text-[var(--text-secondary)]" role="status">
        Support requests couldn&rsquo;t be loaded. The API did not answer; this is not an empty queue.
      </p>
    );
  }

  const rows = requests.filter((r) =>
    view === "all"
      ? true
      : view === "waiting"
        ? waitingOnTeam(r.status)
        : view === "seller"
          ? r.status === "waiting_for_seller"
          : !isOpen(r.status),
  );
  const selected = rows.find((r) => r.id === selectedId) ?? null;

  // Screen/Admin/Queue/Support 7943:12025: sellers claiming their store,
  // asking for a takedown, or for reviewers to be investigated. A row opens
  // the request and its response form in a modal.
  return (
    <div className="flex flex-col gap-3">
      <label className="relative inline-flex w-fit items-center">
        <span className="sr-only">Which requests</span>
        <select
          value={view}
          onChange={(e) => setView(e.target.value as View)}
          className={`h-8 appearance-none rounded-full pl-4 pr-8 ${DROPDOWN_PILL_STATES}`}
        >
          {VIEWS.map((v) => (
            <option key={v.key} value={v.key}>
              {v.label}
              {v.key === "seller" ? ` (${requests.filter((r) => r.status === "waiting_for_seller").length})` : ""}
            </option>
          ))}
        </select>
        <CaretDown size={12} className="pointer-events-none absolute right-3" />
      </label>

      <div className="overflow-x-auto rounded-[16px] border border-[var(--border-subtle)]">
        <table className="w-full min-w-[880px] table-fixed border-collapse text-left text-[14px]" data-testid="support-queue">
          <caption className="sr-only">Seller support requests</caption>
          <colgroup>
            <col style={{ width: "40%" }} />
            <col style={{ width: "16%" }} />
            <col style={{ width: "16%" }} />
            <col style={{ width: "16%" }} />
            <col style={{ width: "12%" }} />
          </colgroup>
          <thead className="bg-[var(--surface-app)] text-[12px] text-[var(--text-secondary)]">
            <tr>
              <th scope="col" className="h-10 px-3 font-normal">Request</th>
              <th scope="col" className="px-3 font-normal">Category</th>
              <th scope="col" className="px-3 font-normal">Handled by</th>
              <th scope="col" className="px-3 font-normal">Status</th>
              <th scope="col" className="px-3 font-normal">Updated</th>
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 ? (
              <tr>
                <td colSpan={5} className="border-t border-[var(--border-subtle)] px-3 py-10 text-center text-[var(--text-secondary)]">
                  {view === "waiting" ? "No request is waiting on an administrator." : "Nothing here."}
                </td>
              </tr>
            ) : (
              rows.map((r) => (
                <tr
                  key={r.id}
                  onClick={() => setSelectedId(r.id)}
                  className="cursor-pointer border-t border-[var(--border-subtle)] hover:bg-[var(--surface-app)]/60"
                >
                  <td className="px-3 py-[10px]">
                    <button
                      type="button"
                      onClick={(e) => {
                        e.stopPropagation();
                        setSelectedId(r.id);
                      }}
                      className="flex w-full items-center gap-[10px] text-left focus-visible:outline focus-visible:outline-2 focus-visible:outline-[var(--accent-primary)]"
                    >
                      <span className="grid size-8 shrink-0 place-items-center rounded-[8px] bg-[var(--surface-app)] text-[var(--text-muted)]">
                        <Storefront size={16} aria-hidden />
                      </span>
                      <span className="flex min-w-0 flex-col gap-1 leading-none">
                        <span className="truncate">{r.subject}</span>
                        <span className="truncate text-[12px] text-[var(--text-secondary)]">
                          {r.seller_name ?? "Store"} · {r.reference}
                        </span>
                      </span>
                    </button>
                  </td>
                  <td className="px-3">{categoryLabel(r.category)}</td>
                  <td className="px-3">
                    {r.assigned_admin ? (
                      <span className="flex items-center gap-2">
                        <span className="grid size-6 place-items-center rounded-full bg-[var(--surface-app)] text-[11px]">
                          {r.assigned_admin.slice(0, 1).toUpperCase()}
                        </span>
                        <span className="truncate">{r.assigned_admin}</span>
                      </span>
                    ) : (
                      <span className="text-[var(--text-secondary)]">Unassigned</span>
                    )}
                  </td>
                  <td className="px-3">
                    <span className="inline-flex items-center gap-[6px]">
                      {r.status === "open" ? (
                        <WarningCircle size={14} className="text-[var(--accent-primary)]" />
                      ) : r.status === "in_review" ? (
                        <ArrowsClockwise size={14} className="text-[var(--accent-trust)]" />
                      ) : r.status === "resolved" ? (
                        <CheckCircle size={14} className="text-[var(--accent-success)]" />
                      ) : (
                        <XCircle size={14} className="text-[var(--text-secondary)]" />
                      )}
                      {statusLabel(r.status)}
                    </span>
                  </td>
                  <td className="px-3 text-[var(--text-secondary)]">{relativeAge(r.updated_at, now).replace(" ago", "")}</td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
      {rows.length > 0 ? (
        <p className="text-[12px] text-[var(--text-secondary)]">
          Showing {rows.length} of {requests.length}
        </p>
      ) : null}

      {selected ? (
        <AdminModal
          title={selected.subject}
          subtitle={`${selected.seller_name ?? "Store"} · ${selected.reference} · ${categoryLabel(selected.category)}`}
          onClose={() => setSelectedId(null)}
        >
          <div className="p-6">
            <SupportDetail key={selected.id} request={selected} />
          </div>
        </AdminModal>
      ) : null}
    </div>
  );
}

function StatusPill({ status }: { status: string }) {
  return (
    <span
      className={`inline-block rounded-[var(--radius-pill)] px-2 py-0.5 text-[11px] font-semibold ${
        status === "open"
          ? "bg-[color-mix(in_srgb,var(--accent-primary)_12%,transparent)] text-[var(--accent-primary)]"
          : status === "in_review"
            ? "bg-[var(--line-hairline-10)] text-[var(--text-primary)]"
            : status === "waiting_for_seller"
              ? "bg-[var(--status-high-bg)] text-[var(--status-high-fg)]"
            : "text-[var(--text-secondary)]"
      }`}
    >
      {statusLabel(status, "staff")}
    </span>
  );
}

function SupportDetail({ request: r }: { request: AdminSupportRequest }) {
  const router = useRouter();
  const ids = { reply: useId(), replyStatus: useId(), status: useId(), note: useId() };
  const [reply, setReply] = useState("");
  const [replyAction, setReplyAction] = useState<"ask" | "review" | "resolve">("ask");
  const [status, setStatus] = useState<string>(r.status);
  const [note, setNote] = useState(r.internal_note ?? "");
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<string | null>(null);

  async function call(action: string, path: string, body?: unknown) {
    setBusy(action);
    setError(null);
    setDone(null);
    try {
      const res = await fetch(`/api/bff/api/v1/admin/support-requests/${encodeURIComponent(r.id)}/${path}`, {
        method: "POST",
        headers: body === undefined ? undefined : { "content-type": "application/json" },
        body: body === undefined ? undefined : JSON.stringify(body),
      });
      if (!res.ok) {
        const p = (await res.json().catch(() => ({}))) as { detail?: string };
        setError(p.detail ?? "That didn't go through.");
        return false;
      }
      setDone(action === "reply" ? "Reply sent to the seller." : action === "assign" ? "It's yours." : "Saved.");
      router.refresh();
      return true;
    } catch {
      setError("Couldn't reach the server.");
      return false;
    } finally {
      setBusy(null);
    }
  }

  const field =
    "mt-1 block w-full rounded-[var(--radius-sm)] border border-[var(--border-subtle)] bg-[var(--surface-card)] px-2.5 py-1.5 text-[13px] text-[var(--text-primary)]";
  const button =
    "rounded-[var(--radius-pill)] px-3.5 py-1.5 text-[12px] font-semibold disabled:opacity-60";
  const closed = !isOpen(r.status);

  return (
    <section
      aria-label={`Support request ${r.reference}`}
      className="flex min-h-0 flex-col gap-4 overflow-y-auto rounded-[var(--radius-md)] bg-[var(--surface-card)] p-5 shadow-[var(--shadow-card)]"
      data-testid="support-detail"
    >
      <div>
        <p className="text-[11px] text-[var(--text-muted)]">
          {r.reference} · {categoryLabel(r.category)}
        </p>
        <h3 className="mt-1 text-[16px] font-semibold text-[var(--text-primary)] [overflow-wrap:anywhere]">{r.subject}</h3>
        <p className="mt-1 text-[12px] text-[var(--text-secondary)]">
          <Link href={`/sellers/${r.seller_id}`} className="font-medium text-[var(--accent-primary)] hover:underline">
            {r.seller_name ?? "The store"}
          </Link>
          {r.created_by ? <> · from {r.created_by}</> : null} · <StatusPill status={r.status} />
        </p>
        <p className="mt-1 text-[12px] text-[var(--text-secondary)]">
          Handled by: {r.assigned_admin ?? "nobody yet"}
        </p>
        {r.conversation_id ? (
          // MQA-021: the request IS this thread; replies here land there too.
          <Link href={`/admin/inbox?c=${r.conversation_id}`} className="mt-1 inline-block text-[12px] font-medium text-[var(--accent-primary)] hover:underline">
            Open the conversation · replies from here appear there
          </Link>
        ) : null}
      </div>

      <p className="whitespace-pre-line text-[13px] leading-[20px] text-[var(--text-primary)] [overflow-wrap:anywhere]">{r.message}</p>
      {r.related_seller_review_id ? (
        <Link
          href={`/sellers/${r.seller_id}#review-${r.related_seller_review_id}`}
          className="text-[12px] font-medium text-[var(--accent-primary)] hover:underline"
        >
          Open the review this is about
        </Link>
      ) : null}
      {r.related_review_id ? (
        <Link href={`/reviews/${r.related_review_id}`} className="text-[12px] font-medium text-[var(--accent-primary)] hover:underline">
          Open the product review this is about
        </Link>
      ) : null}

      {r.admin_response ? (
        <div className="rounded-[var(--radius-sm)] bg-[var(--surface-app)] p-3">
          <p className="text-[11px] font-semibold text-[var(--text-muted)]">Last reply to the seller</p>
          <p className="mt-1 whitespace-pre-line text-[13px] text-[var(--text-primary)] [overflow-wrap:anywhere]">{r.admin_response}</p>
        </div>
      ) : null}

      {!closed && !r.assigned_admin_id ? (
        <button
          type="button"
          disabled={busy !== null}
          onClick={() => call("assign", "assign")}
          className={`${button} self-start bg-[var(--accent-primary)] text-[var(--text-on-brand)]`}
        >
          {busy === "assign" ? "Taking…" : "Take this request"}
        </button>
      ) : null}

      <form
        className="flex flex-col gap-2 border-t border-[var(--line-hairline-10)] pt-4"
        aria-label="Reply to the seller"
        onSubmit={async (e) => {
          e.preventDefault();
          if (!reply.trim()) {
            setError("Write the reply first.");
            return;
          }
          if (await call("reply", "respond", { response: reply.trim(), action: replyAction })) setReply("");
        }}
      >
        <CountedTextarea id={ids.reply} label="Reply to the seller · they see this" value={reply} onChange={setReply} max={TEXT_MAX} rows={4} />
        {/* MQA-028: a pasted template's {{tags}} must be filled before it goes out. */}
        {unfilledWarning(unfilledTags(reply)) ? (
          <p role="alert" className="-mt-1 text-[12px] text-[var(--accent-danger)]">
            {unfilledWarning(unfilledTags(reply))}
          </p>
        ) : null}
        <fieldset className="flex flex-col gap-1.5">
          <legend className="mb-1 text-[12px] text-[var(--text-secondary)]">After sending</legend>
          {REPLY_ACTIONS.map((a) => (
            <label key={a.key} className="flex cursor-pointer items-start gap-2 text-[13px]">
              <input type="radio" name={ids.replyStatus} checked={replyAction === a.key} onChange={() => setReplyAction(a.key)} className="mt-1" />
              <span className="flex flex-col">
                {a.label}
                <span className="text-[12px] text-[var(--text-secondary)]">{a.hint}</span>
              </span>
            </label>
          ))}
        </fieldset>
        <button type="submit" disabled={busy !== null || countState(reply, TEXT_MAX).over || unfilledTags(reply).length > 0} className={`${button} self-start bg-[var(--accent-primary)] text-[var(--text-on-brand)]`}>
          {busy === "reply" ? "Sending…" : "Send reply"}
        </button>
      </form>

      <form
        className="flex flex-col gap-2 border-t border-[var(--line-hairline-10)] pt-4"
        aria-label="Status and internal note"
        onSubmit={async (e) => {
          e.preventDefault();
          await call("status", "status", { status, internal_note: note });
        }}
      >
        <label htmlFor={ids.status} className="text-[12px] font-semibold text-[var(--text-primary)]">
          Change the status without replying
          <select id={ids.status} value={status} onChange={(e) => setStatus(e.target.value)} className={field}>
            {STATUSES.map((s) => (
              <option key={s} value={s}>
                {statusLabel(s, "staff")}
              </option>
            ))}
          </select>
        </label>
        <CountedTextarea id={ids.note} label="Internal note · staff only, the seller never sees it" value={note} onChange={setNote} max={TEXT_MAX} rows={3} />
        <button
          type="submit"
          disabled={busy !== null || countState(note, TEXT_MAX).over}
          className={`${button} self-start border border-[var(--border-subtle)] text-[var(--text-primary)]`}
        >
          {busy === "status" ? "Saving…" : "Save status and note"}
        </button>
      </form>

      {error ? (
        <p role="alert" className="text-[12px] text-[var(--accent-danger)]">
          {error}
        </p>
      ) : null}
      {done ? (
        <p role="status" className="text-[12px] text-[var(--accent-success)]">
          {done}
        </p>
      ) : null}
    </section>
  );
}
