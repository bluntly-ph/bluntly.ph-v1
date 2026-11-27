"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { ArrowRight, WarningCircle } from "@phosphor-icons/react";

import { Chip } from "@/components/console/Chip";
import { CHANGE_STATUS } from "@/components/seller/console/profile-model";

type Change = import("@/lib/api-types").components["schemas"]["StoreChangeOut"];

/**
 * The store changes a seller's thread asks for (MQA-019/025): each with the
 * store's value now and the value asked for, a check that a new link is on the
 * store's own marketplace (MQA-020), and Approve - which applies it to the
 * store and tells the seller in this thread - or Reject with a reason.
 * Nothing renders for a thread that asks for no change.
 */
export function StoreChangesPanel({ conversationId }: { conversationId: string }) {
  const router = useRouter();
  const [changes, setChanges] = useState<Change[]>([]);
  const [arming, setArming] = useState<{ id: string; action: "approve" | "reject" } | null>(null);
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    const res = await fetch(`/api/bff/api/v1/admin/inbox/${conversationId}/changes`).catch(() => null);
    if (res?.ok) setChanges((await res.json()) as Change[]);
  }, [conversationId]);

  useEffect(() => {
    let live = true;
    fetch(`/api/bff/api/v1/admin/inbox/${conversationId}/changes`)
      .then((r) => (r.ok ? r.json() : []))
      .then((list: Change[]) => live && setChanges(list))
      .catch(() => undefined);
    return () => {
      live = false;
    };
  }, [conversationId]);

  if (!changes.length) return null;

  async function decide(id: string, decision: "approve" | "reject") {
    setBusy(true);
    setError(null);
    const res = await fetch(`/api/bff/api/v1/admin/store-changes/${id}/decision`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ decision, note: reason.trim() || null }),
    }).catch(() => null);
    setBusy(false);
    if (!res?.ok) {
      const p = res ? ((await res.json().catch(() => ({}))) as { detail?: unknown }) : {};
      setError(typeof p.detail === "string" ? p.detail : "Couldn't record that.");
      return;
    }
    setArming(null);
    setReason("");
    await load();
    router.refresh();
  }

  const pending = changes.filter((c) => c.status === "pending").length;
  return (
    <section aria-label="Store changes asked for" data-testid="store-changes" className="border-b border-[var(--border-subtle)] bg-[var(--surface-app)] px-5 py-3">
      <p className="text-[12px] font-medium text-[var(--text-secondary)]">
        {pending ? `${pending} store change${pending === 1 ? "" : "s"} to decide` : "Store changes"} · Approve applies it to the store and tells the seller here
      </p>
      <ul className="mt-2 flex flex-col gap-2">
        {changes.map((c) => {
          const link = c.field === "store_url";
          const armed = arming?.id === c.id ? arming.action : null;
          return (
            <li key={c.id} className="rounded-[12px] border border-[var(--border-subtle)] bg-[var(--surface-card)] p-3 text-[14px]">
              <div className="flex flex-wrap items-center gap-2">
                <span className="font-medium">{c.label}</span>
                <Chip tone={CHANGE_STATUS[c.status].tone}>{CHANGE_STATUS[c.status].label}</Chip>
              </div>
              <div className="mt-2 grid grid-cols-[minmax(0,1fr)_auto_minmax(0,1fr)] items-start gap-2 text-[13px]">
                <span className="min-w-0 [overflow-wrap:anywhere]">
                  <span className="block text-[11px] uppercase tracking-[0.06em] text-[var(--text-secondary)]">Now</span>
                  {(c.status === "pending" ? c.live_value : c.current_value) ?? <span className="text-[var(--text-secondary)]">Not set</span>}
                </span>
                <ArrowRight size={14} aria-hidden className="mt-5 text-[var(--text-secondary)]" />
                <span className="min-w-0 [overflow-wrap:anywhere]">
                  <span className="block text-[11px] uppercase tracking-[0.06em] text-[var(--text-secondary)]">Asked for</span>
                  {link ? (
                    <a href={c.requested_value} target="_blank" rel="noreferrer nofollow" className="text-[var(--chart-honesty-fund)] underline-offset-4 hover:underline">
                      {c.requested_value}
                    </a>
                  ) : (
                    c.requested_value
                  )}
                </span>
              </div>
              {c.link_problem ? (
                <p className="mt-2 flex items-start gap-1.5 text-[12px] text-[var(--accent-danger)]">
                  <WarningCircle size={14} aria-hidden className="mt-px shrink-0" /> {c.link_problem}
                </p>
              ) : null}
              {c.decision_note ? <p className="mt-2 text-[12px] text-[var(--text-secondary)] [overflow-wrap:anywhere]">“{c.decision_note}”</p> : null}
              {c.status === "pending" ? (
                <div className="mt-3 flex flex-wrap items-center gap-2">
                  {armed === "reject" ? (
                    <>
                      <label htmlFor={`reason-${c.id}`} className="sr-only">
                        Why not · sent to the seller
                      </label>
                      <input
                        id={`reason-${c.id}`}
                        value={reason}
                        onChange={(e) => setReason(e.target.value.slice(0, 1000))}
                        placeholder="Why not · sent to the seller"
                        className="h-8 min-w-0 flex-1 rounded-full border border-[var(--line-hairline-30)] bg-[var(--surface-card)] px-3 text-[12px] outline-none focus:border-[var(--accent-primary)]"
                      />
                      <button type="button" disabled={busy || !reason.trim()} onClick={() => void decide(c.id, "reject")} className="h-8 rounded-full border border-[var(--accent-danger)] px-3 text-[12px] text-[var(--accent-danger)] disabled:opacity-50">
                        {busy ? "Sending…" : "Reject"}
                      </button>
                    </>
                  ) : armed === "approve" ? (
                    <button type="button" disabled={busy} onClick={() => void decide(c.id, "approve")} className="h-8 rounded-full bg-[var(--accent-primary)] px-3 text-[12px] text-white disabled:opacity-50">
                      {busy ? "Applying…" : `Apply to the store`}
                    </button>
                  ) : (
                    <>
                      <button type="button" disabled={Boolean(c.link_problem)} onClick={() => setArming({ id: c.id, action: "approve" })} className="h-8 rounded-full bg-[var(--accent-primary)] px-3 text-[12px] text-white disabled:opacity-50">
                        Approve
                      </button>
                      <button type="button" onClick={() => setArming({ id: c.id, action: "reject" })} className="h-8 rounded-full border border-[var(--text-primary)] px-3 text-[12px]">
                        Reject
                      </button>
                    </>
                  )}
                  {armed ? (
                    <button type="button" onClick={() => { setArming(null); setReason(""); }} className="text-[12px] text-[var(--text-secondary)] hover:underline">
                      Cancel
                    </button>
                  ) : null}
                </div>
              ) : null}
            </li>
          );
        })}
      </ul>
      {error ? (
        <p role="alert" className="mt-2 text-[12px] text-[var(--accent-danger)]">
          {error}
        </p>
      ) : null}
    </section>
  );
}
