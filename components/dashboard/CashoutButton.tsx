"use client";

import { useRouter } from "next/navigation";
import { useRef, useState } from "react";
import { LockSimple } from "@phosphor-icons/react";

/**
 * The Payout footer's Button/Pill (Figma Screen/Payout 7840:9453, Locked
 * 7840:9530): "Request ₱1,790.04" when the minimum is met, a disabled
 * "Request payout" when it is not. POST /payouts/cashout.
 *
 * Business Rules §15/§19: a request draws only on CLEARED money and the whole
 * cleared balance is requested; there is no cooldown, a second request in the
 * same batch tops up the first. The server re-checks the minimum and the
 * payout account whatever this button shows.
 */
export function CashoutButton({
  canCashOut,
  reason,
  amountLabel,
  minimumMet = false,
  requested = null,
}: {
  canCashOut: boolean;
  /** Why it is disabled, already human-readable. */
  reason: string | null;
  /** The cleared amount, "₱1,790.04". */
  amountLabel: string;
  /** Minimum met but blocked (no wallet, Figma Payout/No wallet 7855:11265): the label keeps the amount. */
  minimumMet?: boolean;
  /** An open request (Figma Payout/Requested 7855:11171): "₱1,790.04 is locked until it's sent to your PayPal". */
  requested?: string | null;
}) {
  const router = useRouter();
  const inFlight = useRef(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<string | null>(null);

  async function request() {
    if (!canCashOut || inFlight.current) return;
    inFlight.current = true;
    setBusy(true);
    setError(null);
    try {
      const res = await fetch("/api/bff/api/v1/payouts/cashout", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({}),
      });
      if (!res.ok) {
        const p = (await res.json().catch(() => ({}))) as { detail?: unknown };
        setError(typeof p.detail === "string" ? p.detail : "Couldn't request the payout.");
        return;
      }
      const payout = (await res.json().catch(() => ({}))) as { scheduled_for?: string };
      const when = payout.scheduled_for
        ? new Date(payout.scheduled_for).toLocaleDateString("en-PH", { dateStyle: "medium" })
        : null;
      setDone(`Requested ${amountLabel}.${when ? ` It's in the batch for ${when}.` : ""}`);
      router.refresh();
    } catch {
      setError("Couldn't reach the server.");
    } finally {
      setBusy(false);
      inFlight.current = false;
    }
  }

  return (
    <div className="flex w-full flex-col items-center gap-2">
      {error ? (
        <p role="alert" className="text-center text-[12px] font-medium text-[var(--accent-danger)]">
          {error}
        </p>
      ) : null}
      {done ? (
        <p role="status" className="text-center text-[12px] text-[var(--text-primary)]">
          {done}
        </p>
      ) : null}
      <button
        type="button"
        onClick={request}
        disabled={!canCashOut || busy}
        aria-describedby={canCashOut ? undefined : requested ? "payout-locked" : "payout-reason"}
        className="flex h-14 w-full cursor-pointer items-center justify-center gap-1 rounded-[var(--radius-pill)] bg-[var(--accent-primary)] px-6 text-[16px] font-semibold leading-none text-[var(--text-on-brand)] transition-transform duration-[120ms] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--accent-primary)] enabled:active:scale-[0.97] disabled:cursor-not-allowed disabled:bg-[var(--disabled-surface)] disabled:text-[var(--disabled-text)] motion-reduce:transition-none motion-reduce:active:scale-100"
      >
        {busy ? "Requesting…" : requested && !canCashOut ? "Payout requested" : canCashOut || minimumMet ? `Request ${amountLabel}` : "Request payout"}
      </button>
      {!canCashOut && requested ? (
        <p id="payout-locked" className="flex items-center gap-1 text-center text-[12px] leading-[1.5] text-[var(--base-gray-400)]">
          <LockSimple size={12} aria-hidden />
          {requested}
        </p>
      ) : null}
      {!canCashOut && !requested && reason && !done ? (
        <p id="payout-reason" className="text-center text-[12px] leading-[1.5] text-[var(--base-gray-400)]">
          {reason}
        </p>
      ) : null}
    </div>
  );
}
