"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { CheckCircle, ClockCounterClockwise, Copy, Wallet } from "@phosphor-icons/react/dist/ssr";

import { AdminModal } from "@/components/admin/AdminModal";
import { ConfirmDialog, Consequence } from "@/components/admin/ConfirmDialog";
import { PAYOUT_FILTERS, PAYOUT_SORTS, applyPayouts } from "@/components/admin/list-models";
import { PayoutTabs } from "@/components/admin/payouts/PayoutTabs";
import { ListControls } from "@/components/console/ListControls";
import { Pagination } from "@/components/console/Pagination";
import { PAGE_SIZES, pageCount } from "@/components/console/pagination-model";
import { PersonCell } from "@/components/admin/queue/QueueCells";
import type { AdminPayout, PayoutProviderStatus, PayoutSummary } from "@/lib/moderation";
import { countState } from "@/components/console/counted-model";
import { CountedTextarea } from "@/components/console/CountedTextarea";

const REASON_MAX = 500;

/**
 * The redesigned Payouts screen (Figma Screen/Admin/Payouts 8024:12721,
 * Overlay/Payout/Send 8025:12833, Confirm/Payout/Sent 8025:12896; meeting
 * 2026-10-02, 16:50): the owner transfers each request by hand, then marks it
 * sent with the transaction ID, and it moves to Sent.
 *
 * Manual on purpose: automated payout execution is out of scope for the
 * defense. "Process requests" (the PayPal Payouts API) is offered only when the
 * server says that API is configured; otherwise there is nothing to press.
 *
 * Actions, all existing endpoints: mark-paid (with the reference), fail (with
 * a reason the member sees), cancel (refunds the wallet), retry (failed).
 */

type View = "to_send" | "sent" | "failed";

/** The two middle columns per tab (Figma Payouts 8085:17825 Sent, 8085:18136 Failed). */
const COLUMNS: Record<View, [string, string]> = {
  to_send: ["Requested", "Scheduled for"],
  sent: ["Reference", "Sent on"],
  // No failure time is stored, so the request's age stands in its place.
  failed: ["Reason", "Requested"],
};

function pesoParts(amount: string): [string, string] {
  const [whole, cents] = Number(amount)
    .toLocaleString("en-PH", { minimumFractionDigits: 2, maximumFractionDigits: 2 })
    .split(".");
  return [`₱${whole}`, cents];
}

function Money({ amount, size = 14 }: { amount: string; size?: number }) {
  const [whole, cents] = pesoParts(amount);
  return (
    <span className="whitespace-nowrap font-medium" style={{ fontSize: size }}>
      {whole}
      <span className="text-[var(--text-secondary)]">.{cents}</span>
    </span>
  );
}

/** "carla.m•••@gmail.com": enough to recognise, not enough to copy from the table. */
function mask(address: string | null): string {
  if (!address) return "No payout account";
  const [user, domain] = address.split("@");
  if (!domain) return address;
  return `${user.slice(0, Math.min(6, Math.max(1, user.length - 2)))}•••@${domain}`;
}

function ago(iso: string | null, now: number): string {
  if (!iso) return "—";
  const s = Math.max(0, Math.round((now - new Date(iso).getTime()) / 1000));
  if (s < 3600) return `${Math.max(1, Math.round(s / 60))}m ago`;
  if (s < 86400) return `${Math.round(s / 3600)}h ago`;
  // Past two months a day count stops reading as time; the date says it plainly.
  if (s >= 60 * 86400) return new Date(iso).toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric", timeZone: "Asia/Manila" });
  return `${Math.round(s / 86400)}d ago`;
}

function day(iso: string): string {
  return new Date(iso.length === 10 ? `${iso}T00:00:00` : iso).toLocaleDateString("en-PH", { day: "numeric", month: "short" });
}

function method(m: string): string {
  return m.startsWith("paypal") ? "PayPal" : m === "manual" ? "Manual transfer" : m;
}

export function PayoutsScreen({
  view,
  query = {},
  payouts,
  summary,
  provider,
  now,
}: {
  view: View;
  /** Menu/Payouts/Sort + Filter, Search/Payouts (8288:29926–29976). */
  query?: Record<string, string>;
  payouts: AdminPayout[] | null;
  summary: PayoutSummary | null;
  provider: PayoutProviderStatus | null;
  now: number;
}) {
  const router = useRouter();
  const [openId, setOpenId] = useState<string | null>(null);
  const [reference, setReference] = useState("");
  const [failReason, setFailReason] = useState("");
  const [confirm, setConfirm] = useState<"sent" | "cancel" | "fail" | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [runMessage, setRunMessage] = useState<string | null>(null);

  const inView = (payouts ?? []).filter((p) =>
    view === "to_send" ? p.status === "scheduled" || p.status === "processing"
    : view === "sent" ? p.status === "paid"
    : p.status === "failed",
  );
  const matching = applyPayouts(inView, query);
  // Figma 8024:12721 pages the list (Pagination); the API sends up to 100 per status.
  const size = (PAGE_SIZES as readonly number[]).includes(Number(query.size)) ? Number(query.size) : PAGE_SIZES[0];
  const page = Math.min(Math.max(1, Number(query.page) || 1), pageCount(matching.length, size));
  const rows = matching.slice((page - 1) * size, page * size);
  const open = rows.find((p) => p.id === openId) ?? null;
  const name = (p: AdminPayout) => p.display_name ?? p.username ?? "Member";
  const month = summary
    ? new Date(`${summary.month_start}T00:00:00`).toLocaleDateString("en-PH", { month: "long" })
    : "";

  function close() {
    if (busy) return;
    setOpenId(null);
    setReference("");
    setFailReason("");
    setConfirm(null);
    setError(null);
    setCopied(false);
  }

  async function act(path: string, body?: object) {
    if (!open) return;
    setBusy(true);
    setError(null);
    try {
      const res = await fetch(`/api/bff/api/v1/admin/payouts/${open.id}/${path}`, {
        method: "POST",
        headers: body ? { "content-type": "application/json" } : undefined,
        body: body ? JSON.stringify(body) : undefined,
      });
      if (!res.ok) {
        const problem = (await res.json().catch(() => ({}))) as { detail?: string; title?: string };
        setError(problem.detail ?? problem.title ?? "Couldn't record that.");
        return;
      }
      setBusy(false);
      close();
      router.refresh();
    } catch {
      setError("Couldn't reach the server.");
    } finally {
      setBusy(false);
    }
  }

  async function processRequests() {
    setBusy(true);
    setRunMessage(null);
    try {
      const res = await fetch("/api/bff/api/v1/admin/payouts/run", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ submit: true }),
      });
      const body = (await res.json().catch(() => ({}))) as { scheduled?: number; detail?: string };
      setRunMessage(res.ok ? `${body.scheduled ?? 0} request(s) sent to PayPal.` : (body.detail ?? "PayPal did not accept the batch."));
      router.refresh();
    } finally {
      setBusy(false);
    }
  }

  const views: { key: View; count: number | null }[] = [
    { key: "to_send", count: summary?.to_send_count ?? null },
    { key: "sent", count: summary?.sent_count ?? null },
    { key: "failed", count: summary?.failed_count ?? null },
  ];

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center gap-2">
        <PayoutTabs current={view} counts={summary} />
        <span className="flex-1" />
        <ListControls
          basePath="/admin/payouts"
          params={query}
          sorts={PAYOUT_SORTS}
          defaultSort="oldest"
          filters={PAYOUT_FILTERS}
          search={{ placeholder: "Reviewer or reference", label: "Search payouts" }}
        />
        {provider?.api_submission_available ? (
          <button
            type="button"
            onClick={() => void processRequests()}
            disabled={busy}
            className="h-9 rounded-full border border-[var(--base-ink-800)] px-4 text-[12px] disabled:opacity-60"
          >
            Process requests
          </button>
        ) : (
          <span className="text-[12px] text-[var(--text-secondary)]" title="The PayPal Payouts API is not configured on this server.">
            Manual transfers · minimum ₱{provider?.minimum_cashout ?? "300.00"}
          </span>
        )}
      </div>
      {runMessage ? <p role="status" className="text-[12px] text-[var(--text-secondary)]">{runMessage}</p> : null}

      <div className="grid gap-4 md:grid-cols-3">
        {[
          {
            label: "To send",
            amount: summary?.to_send_total,
            note: summary
              ? `${summary.to_send_count} ${summary.to_send_count === 1 ? "payout" : "payouts"}${summary.oldest_requested_at ? `, oldest requested ${/ago$/.test(ago(summary.oldest_requested_at, now)) ? "" : "on "}${ago(summary.oldest_requested_at, now)}` : ""}`
              : "",
          },
          {
            label: `Sent in ${month}`,
            amount: summary?.sent_month_total,
            note: summary ? `${summary.sent_month_count} ${summary.sent_month_count === 1 ? "payout" : "payouts"} so far` : "",
          },
          { label: "Waiting in wallets", amount: summary?.waiting_in_wallets, note: "Cleared, not yet requested" },
        ].map((card) => (
          <div key={card.label} className="flex flex-col gap-1.5 rounded-[16px] border border-[var(--border-subtle)] p-5">
            <span className="text-[12px] text-[var(--text-secondary)]">{card.label}</span>
            {card.amount !== undefined ? <Money amount={card.amount} size={24} /> : <span className="text-[24px]">—</span>}
            <span className="text-[12px] text-[var(--text-secondary)]">{card.note}</span>
          </div>
        ))}
      </div>

      <div className="overflow-x-auto rounded-[16px] border border-[var(--border-subtle)]">
        <table className="w-full min-w-[900px] border-collapse text-left text-[14px]">
          <caption className="sr-only">Payouts</caption>
          <thead className="bg-[var(--surface-app)] text-[12px] text-[var(--text-secondary)]">
            <tr>
              {["Reviewer", "Amount", "Send to", ...COLUMNS[view], "Action"].map((h) => (
                <th key={h} scope="col" className="h-10 px-3 font-normal">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {payouts === null ? (
              <tr><td colSpan={6} className="border-t border-[var(--border-subtle)] px-3 py-10 text-center text-[var(--text-secondary)]">Payouts could not be loaded.</td></tr>
            ) : rows.length === 0 ? (
              <tr>
                <td colSpan={6} className="border-t border-[var(--border-subtle)] px-3 py-10 text-center text-[var(--text-secondary)]">
                  {view === "to_send" ? "No request is waiting to be sent." : view === "sent" ? "Nothing sent yet." : "No failed payouts."}
                </td>
              </tr>
            ) : (
              rows.map((p) => (
                <tr key={p.id} data-testid="payout-row" className="border-t border-[var(--border-subtle)]">
                  <td className="px-3 py-[10px]">
                    <PersonCell name={name(p)} stage={p.trust_stage ?? undefined} levelName={p.trust_level_name} href={`/admin/people/${p.user_id}`} />
                    {p.qa_tester ? <span className="ml-9 text-[10px] text-[var(--accent-trust)]">QA tester</span> : null}
                  </td>
                  <td className="px-3"><Money amount={p.amount} /></td>
                  <td className="px-3">
                    <span className="flex flex-col gap-1 leading-4 [&>:first-child]:leading-5">
                      <span>{method(p.method)}</span>
                      <span className="text-[12px] text-[var(--text-secondary)]">{mask(p.payout_account)}</span>
                    </span>
                  </td>
                  {view === "sent" ? (
                    <>
                      <td className="px-3 text-[var(--text-secondary)] [overflow-wrap:anywhere]">{p.provider_ref ?? "—"}</td>
                      <td className="px-3 text-[var(--text-secondary)]">{p.paid_at ? day(p.paid_at) : "—"}</td>
                    </>
                  ) : view === "failed" ? (
                    <>
                      <td className="px-3 text-[var(--text-secondary)]">{p.failure_reason ?? "—"}</td>
                      <td className="px-3 text-[var(--text-secondary)]">{ago(p.created_at, now)}</td>
                    </>
                  ) : (
                    <>
                      <td className="px-3 text-[var(--text-secondary)]">{ago(p.created_at, now)}</td>
                      <td className="px-3 text-[var(--text-secondary)]">{day(p.scheduled_for)}</td>
                    </>
                  )}
                  <td className="px-3">
                    {view === "to_send" ? (
                      <button type="button" onClick={() => setOpenId(p.id)} className="rounded-full border border-[var(--border-subtle)] px-3 py-1 text-[12px] hover:border-[var(--text-secondary)]">
                        Open
                      </button>
                    ) : view === "failed" ? (
                      <button type="button" onClick={() => setOpenId(p.id)} className="rounded-full border border-[var(--border-subtle)] px-3 py-1 text-[12px] hover:border-[var(--text-secondary)]">
                        Retry
                      </button>
                    ) : null}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
      <Pagination page={page} size={size} total={matching.length} basePath="/admin/payouts" query={query} label="Payout pages" />
      {(() => {
        const total = views.find((v) => v.key === view)?.count;
        return total != null && total > inView.length ? (
          <p className="text-[12px] text-[var(--text-secondary)]">
            The newest {inView.length.toLocaleString("en-PH")} of {total.toLocaleString("en-PH")} are listed here.
          </p>
        ) : null;
      })()}

      {open && view === "failed" ? (
        <ConfirmDialog
          open
          title="Retry this payout?"
          confirmLabel="Retry"
          busy={busy}
          error={error}
          onClose={close}
          onConfirm={() => void act("retry")}
        >
          <Consequence icon={<ClockCounterClockwise size={18} />}>
            {name(open)}&apos;s {pesoParts(open.amount).join(".")} goes back to To send, to be transferred again.
          </Consequence>
        </ConfirmDialog>
      ) : null}

      {open && view === "to_send" && !confirm ? (
        <AdminModal title="Send payout" width={560} onClose={close}>
          <div className="flex flex-col gap-4 p-6 text-[14px]">
            <div className="flex items-center gap-3">
              <span className="flex-1">
                <PersonCell name={name(open)} stage={open.trust_stage ?? undefined} levelName={open.trust_level_name} />
              </span>
              <Money amount={open.amount} size={24} />
            </div>
            <dl className="divide-y divide-[var(--border-subtle)]">
              <div className="flex items-center gap-3 py-2">
                <dt className="w-[130px] text-[var(--text-secondary)]">Send to</dt>
                <dd className="flex-1 break-all">{method(open.method)} · {open.payout_account ?? "no payout account set"}</dd>
                {open.payout_account ? (
                  <button
                    type="button"
                    onClick={() => {
                      void navigator.clipboard?.writeText(open.payout_account ?? "");
                      setCopied(true);
                    }}
                    className="inline-flex items-center gap-1 text-[var(--accent-trust)]"
                  >
                    <Copy size={14} /> {copied ? "Copied" : "Copy"}
                  </button>
                ) : null}
              </div>
              <div className="flex gap-3 py-2">
                <dt className="w-[130px] text-[var(--text-secondary)]">Requested</dt>
                <dd>{new Date(open.created_at).toLocaleDateString("en-PH", { day: "numeric", month: "short", year: "numeric" })} · {ago(open.created_at, now)}</dd>
              </div>
              <div className="flex gap-3 py-2">
                <dt className="w-[130px] text-[var(--text-secondary)]">Payout ID</dt>
                <dd>{open.payout_id ?? open.id}</dd>
              </div>
            </dl>
            <label htmlFor="payout-ref" className="text-[12px] text-[var(--text-secondary)]">Transfer reference</label>
            <input
              id="payout-ref"
              value={reference}
              onChange={(e) => setReference(e.target.value.slice(0, 128))}
              placeholder="PayPal transaction ID"
              className="h-12 rounded-[12px] border border-[var(--border-subtle)] px-4 text-[14px] outline-none focus-visible:border-[var(--accent-primary)]"
            />
            {error ? <p role="alert" className="text-[12px] text-[var(--accent-danger)]">{error}</p> : null}
          </div>
          <div className="flex flex-wrap items-center gap-2 border-t border-[var(--border-subtle)] px-6 py-4">
            <button type="button" onClick={() => setConfirm("cancel")} className="text-[12px] text-[var(--accent-primary)]">
              Cancel payout
            </button>
            <button type="button" onClick={() => setConfirm("fail")} className="ml-3 text-[12px] text-[var(--text-secondary)]">
              Mark failed
            </button>
            <span className="flex-1" />
            <button type="button" onClick={close} className="h-8 rounded-full border border-[var(--base-ink-800)] px-3 text-[12px]">
              Close
            </button>
            <button
              type="button"
              onClick={() => setConfirm("sent")}
              disabled={reference.trim().length === 0}
              className="h-8 rounded-full bg-[var(--accent-primary)] px-4 text-[12px] text-white disabled:opacity-60"
            >
              Mark as sent
            </button>
          </div>
        </AdminModal>
      ) : null}

      {open && confirm === "sent" ? (
        <ConfirmDialog
          open
          title="Mark as sent?"
          confirmLabel="Mark as sent"
          busyLabel="Recording…"
          busy={busy}
          error={error}
          onClose={() => setConfirm(null)}
          onConfirm={() => void act("mark-paid", { provider_ref: reference.trim() })}
        >
          <Consequence icon={<Wallet size={18} />}>
            {pesoParts(open.amount).join(".")} to {name(open)} is recorded as sent, reference {reference.trim()}.
          </Consequence>
          <Consequence icon={<CheckCircle size={18} />}>It moves to Sent and leaves this queue.</Consequence>
          <Consequence icon={<ClockCounterClockwise size={18} />}>The payout is recorded in the Activity log.</Consequence>
        </ConfirmDialog>
      ) : null}

      {open && confirm === "cancel" ? (
        <ConfirmDialog
          open
          title="Cancel this payout?"
          confirmLabel="Cancel payout"
          busyLabel="Cancelling…"
          tone="danger"
          busy={busy}
          error={error}
          onClose={() => setConfirm(null)}
          onConfirm={() => void act("cancel")}
        >
          <p>The {pesoParts(open.amount).join(".")} goes back to {name(open)}&apos;s wallet. Nothing is sent.</p>
        </ConfirmDialog>
      ) : null}

      {open && confirm === "fail" ? (
        <ConfirmDialog
          open
          title="Mark this payout failed?"
          confirmLabel="Mark failed"
          busyLabel="Recording…"
          tone="danger"
          busy={busy}
          disabled={failReason.trim().length === 0 || countState(failReason, REASON_MAX).over}
          error={error}
          onClose={() => setConfirm(null)}
          onConfirm={() => void act("fail", { reason: failReason.trim() })}
        >
          <p>The money goes back to {name(open)}&apos;s wallet and they see the reason.</p>
          <CountedTextarea
            id="payout-fail-reason"
            label="Why it failed"
            labelHidden
            value={failReason}
            onChange={setFailReason}
            max={REASON_MAX}
            rows={3}
            placeholder="Why it failed (the reviewer sees this)"
          />
        </ConfirmDialog>
      ) : null}
    </div>
  );
}
