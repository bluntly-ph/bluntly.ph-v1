"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { CheckCircle, Circle, Clock } from "@phosphor-icons/react/dist/ssr";

import { AdminModal } from "@/components/admin/AdminModal";
import { ConfirmDialog } from "@/components/admin/ConfirmDialog";

/**
 * Overlay/Store/ClaimStatus (Figma 8232:25429) and Confirm/Store/WithdrawClaim
 * (8233:25386): where a store claim stands — sent, being checked, decision —
 * the registration it was filed with, and "Withdraw claim" behind a
 * confirmation (POST /sellers/claims/{id}/withdraw; the caller's own pending
 * claim only — the API answers 404 for anyone else's).
 *
 * The registration number is shown by its last four digits, as drawn.
 */

export type ClaimView = {
  id: string;
  storeName: string;
  platform: string;
  status: string;
  createdAt: string;
  registrationKind: string | null;
  registrationNumber: string | null;
  businessName: string | null;
  shopName: string | null;
};

const PLATFORM: Record<string, string> = { shopee: "Shopee", lazada: "Lazada", tiktok: "TikTok Shop", other: "Other" };

export function ago(iso: string, now: number = Date.now()): string {
  const s = Math.max(0, (now - new Date(iso).getTime()) / 1000);
  if (s < 3600) return `${Math.max(1, Math.round(s / 60))} min ago`;
  if (s < 86400) return `${Math.round(s / 3600)} h ago`;
  const d = Math.round(s / 86400);
  return d === 1 ? "1 day ago" : `${d} days ago`;
}

function lastFour(n: string | null): string {
  if (!n) return "—";
  const digits = n.replace(/\s+/g, "");
  return digits.length > 4 ? `ending ${digits.slice(-4)}` : digits;
}

export function ClaimStatusDialog({ claim, onClose }: { claim: ClaimView; onClose: () => void }) {
  const router = useRouter();
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const platform = PLATFORM[claim.platform] ?? claim.platform;
  const kind = (claim.registrationKind ?? "").toUpperCase() || "Registration";
  const pending = claim.status === "pending";

  async function withdraw() {
    setBusy(true);
    setError(null);
    try {
      const res = await fetch(`/api/bff/api/v1/sellers/claims/${claim.id}/withdraw`, { method: "POST" });
      if (!res.ok) {
        const p = (await res.json().catch(() => ({}))) as { detail?: string };
        setError(p.detail ?? "The claim couldn't be withdrawn.");
        return;
      }
      setConfirming(false);
      onClose();
      router.refresh();
    } catch {
      setError("Couldn't reach the server.");
    } finally {
      setBusy(false);
    }
  }

  const steps: { label: string; note: string; state: "done" | "current" | "todo" }[] = [
    { label: "Claim sent", note: ago(claim.createdAt), state: "done" },
    {
      label: "A moderator is checking your registration",
      note: `${kind} · ${lastFour(claim.registrationNumber)} against the ${platform} shop name`,
      state: pending ? "current" : "done",
    },
    { label: "Decision", note: "You'll be notified either way", state: pending ? "todo" : "done" },
  ];

  return (
    <>
      <AdminModal title={`Claim: ${claim.storeName}`} width={560} onClose={onClose}>
        <div className="flex flex-col gap-5 overflow-y-auto px-6 pb-5 pt-4">
          <div className="flex flex-col gap-1">
            <span className="text-[16px] font-semibold">{claim.storeName}</span>
            <span className="text-[12px] text-[var(--text-secondary)]">
              {platform} · sent {ago(claim.createdAt)}
            </span>
          </div>
          <ol aria-label="Claim progress" className="flex flex-col gap-4">
            {steps.map((s) => (
              <li key={s.label} className="flex items-start gap-3" aria-current={s.state === "current" ? "step" : undefined}>
                {s.state === "done" ? (
                  <CheckCircle size={20} weight="fill" className="shrink-0 text-[var(--status-baseline-fg)]" aria-hidden />
                ) : s.state === "current" ? (
                  <Clock size={20} weight="fill" className="shrink-0 text-[var(--accent-primary)]" aria-hidden />
                ) : (
                  <Circle size={20} className="shrink-0 text-[var(--text-secondary)]" aria-hidden />
                )}
                <span className="flex flex-col gap-1">
                  <span className={`text-[14px] ${s.state === "todo" ? "text-[var(--text-secondary)]" : ""}`}>{s.label}</span>
                  <span className="text-[12px] text-[var(--text-secondary)]">{s.note}</span>
                </span>
              </li>
            ))}
          </ol>
          <dl className="grid grid-cols-[minmax(0,1fr)_minmax(0,1fr)] gap-x-4 gap-y-3 rounded-[16px] border border-[var(--border-subtle)] p-4 text-[14px]">
            <dt className="text-[12px] text-[var(--text-secondary)]">Registration</dt>
            <dd>
              {kind} · {lastFour(claim.registrationNumber)}
            </dd>
            <dt className="text-[12px] text-[var(--text-secondary)]">Registered business name</dt>
            <dd className="[overflow-wrap:anywhere]">{claim.businessName ?? "—"}</dd>
            <dt className="text-[12px] text-[var(--text-secondary)]">Shop name on {platform}</dt>
            <dd className="[overflow-wrap:anywhere]">{claim.shopName ?? "—"}</dd>
          </dl>
        </div>
        <div className="flex items-center gap-3 border-t border-[var(--border-subtle)] px-6 py-4">
          {pending ? (
            <button
              type="button"
              onClick={() => setConfirming(true)}
              className="h-9 rounded-full border border-[var(--status-critical-fg)] px-4 text-[12px] text-[var(--status-critical-fg)]"
            >
              Withdraw claim
            </button>
          ) : null}
          <span className="flex-1" />
          <button type="button" onClick={onClose} className="h-9 rounded-full bg-[var(--accent-primary)] px-5 text-[12px] text-white">
            Done
          </button>
        </div>
      </AdminModal>
      <ConfirmDialog
        open={confirming}
        title={`Withdraw your claim on ${claim.storeName}?`}
        confirmLabel="Withdraw claim"
        busyLabel="Withdrawing…"
        busy={busy}
        tone="danger"
        error={error}
        onConfirm={() => void withdraw()}
        onClose={() => setConfirming(false)}
      >
        <p>The moderator stops checking it.</p>
        <p>You can claim the store again later.</p>
      </ConfirmDialog>
    </>
  );
}
