"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { cancelEmailChange, confirmEmailChange, startEmailChange } from "@/app/actions/email-change";
import { FIELD_HINT, FIELD_INPUT_COMPACT, FIELD_LABEL } from "@/components/console/fields";

import { emailLooksValid, maskEmail } from "./email-change-model";

type Step = "idle" | "address" | "codes" | "done";

/**
 * Change the address you sign in with (backend 0084; owner decision 2026-10-04
 * over the read-only email of Overlay/Store/Account 8232:25342).
 *
 * Two codes, because two things need proving: one goes to the CURRENT address
 * (it is really you), one to the NEW address (you own it). Nothing changes until
 * both are entered. On success every other signed-in browser is signed out and
 * the old address gets a notice; this browser keeps going on a fresh session.
 *
 * Not a <form>: it sits inside the Account window, which has its own Save.
 */
export function EmailChange({ email }: { email: string }) {
  const router = useRouter();
  const [step, setStep] = useState<Step>("idle");
  const [newEmail, setNewEmail] = useState("");
  const [currentCode, setCurrentCode] = useState("");
  const [newCode, setNewCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<string | null>(null);

  const addressOk = emailLooksValid(newEmail) && newEmail.trim().toLowerCase() !== email.toLowerCase();
  const codesOk = /^\d{6}$/.test(currentCode) && /^\d{6}$/.test(newCode);

  async function send() {
    if (!addressOk) return;
    setBusy(true);
    setError(null);
    const out = await startEmailChange(newEmail);
    setBusy(false);
    if (!out.ok) return setError(out.error ?? "The codes weren't sent. Try again.");
    setNewEmail(out.newEmail ?? newEmail);
    setCurrentCode("");
    setNewCode("");
    setStep("codes");
  }

  async function confirm() {
    if (!codesOk) return;
    setBusy(true);
    setError(null);
    const out = await confirmEmailChange(currentCode, newCode);
    setBusy(false);
    if (!out.ok) {
      // Spent or expired: the codes can't be retried, so go back to the address.
      if (out.code === "otp_attempts_exceeded" || out.code === "otp_expired") setStep("address");
      return setError(out.error ?? "That didn't work. Try again.");
    }
    setDone(out.email ?? newEmail);
    setStep("done");
    router.refresh();
  }

  async function stop() {
    setBusy(true);
    await cancelEmailChange();
    setBusy(false);
    setError(null);
    setStep("idle");
  }

  const digits = (v: string) => v.replace(/\D/g, "").slice(0, 6);

  return (
    <div className="flex flex-col gap-2" data-testid="email-change">
      <span className={FIELD_LABEL}>Email</span>
      {step === "idle" || step === "done" ? (
        <div className="flex flex-wrap items-center gap-3">
          <p className="flex-1 text-[14px]">{maskEmail(done ?? email)}</p>
          <button type="button" onClick={() => setStep("address")} className="h-8 rounded-full border border-[var(--border-subtle)] px-3 text-[12px] hover:border-[var(--text-secondary)]">
            Change email
          </button>
        </div>
      ) : null}
      {step === "done" ? (
        <p role="status" className="text-[12px] text-[var(--accent-success)]">
          You now sign in with {done}. Other browsers were signed out, and your old address got a notice.
        </p>
      ) : null}

      {step === "address" ? (
        <div className="flex flex-col gap-2 rounded-[12px] bg-[var(--surface-app)] p-3">
          <label htmlFor="email-change-new" className={FIELD_HINT}>
            New email. We&rsquo;ll send one code there and one to {maskEmail(email)}.
          </label>
          <input
            id="email-change-new"
            type="email"
            autoComplete="email"
            className={FIELD_INPUT_COMPACT}
            value={newEmail}
            maxLength={320}
            onChange={(e) => setNewEmail(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                e.preventDefault();
                void send();
              }
            }}
          />
          <div className="flex gap-2">
            <button type="button" onClick={() => void send()} disabled={!addressOk || busy} className="h-8 rounded-full bg-[var(--accent-primary)] px-3 text-[12px] font-medium text-[var(--text-on-brand)] disabled:bg-[var(--disabled-surface)] disabled:text-[var(--disabled-text)]">
              {busy ? "Sending…" : "Send codes"}
            </button>
            <button type="button" onClick={() => setStep("idle")} disabled={busy} className="h-8 rounded-full px-3 text-[12px]">
              Cancel
            </button>
          </div>
        </div>
      ) : null}

      {step === "codes" ? (
        <div className="flex flex-col gap-3 rounded-[12px] bg-[var(--surface-app)] p-3">
          <p className={FIELD_HINT}>Enter both codes. They expire in a few minutes.</p>
          <div className="grid grid-cols-[minmax(0,1fr)] gap-3 sm:grid-cols-2">
            <div className="flex flex-col gap-1">
              <label htmlFor="email-change-current-code" className={FIELD_HINT}>
                Code sent to {maskEmail(email)}
              </label>
              <input id="email-change-current-code" inputMode="numeric" autoComplete="one-time-code" className={FIELD_INPUT_COMPACT} value={currentCode} onChange={(e) => setCurrentCode(digits(e.target.value))} />
            </div>
            <div className="flex flex-col gap-1">
              <label htmlFor="email-change-new-code" className={FIELD_HINT}>
                Code sent to {newEmail}
              </label>
              <input id="email-change-new-code" inputMode="numeric" autoComplete="one-time-code" className={FIELD_INPUT_COMPACT} value={newCode} onChange={(e) => setNewCode(digits(e.target.value))} />
            </div>
          </div>
          <div className="flex flex-wrap gap-2">
            <button type="button" onClick={() => void confirm()} disabled={!codesOk || busy} className="h-8 rounded-full bg-[var(--accent-primary)] px-3 text-[12px] font-medium text-[var(--text-on-brand)] disabled:bg-[var(--disabled-surface)] disabled:text-[var(--disabled-text)]">
              {busy ? "Confirming…" : "Change email"}
            </button>
            <button type="button" onClick={() => setStep("address")} disabled={busy} className="h-8 rounded-full px-3 text-[12px]">
              Send new codes
            </button>
            <button type="button" onClick={() => void stop()} disabled={busy} className="h-8 rounded-full px-3 text-[12px]">
              Keep my email
            </button>
          </div>
        </div>
      ) : null}

      {error ? (
        <p role="alert" className="text-[12px] text-[var(--accent-danger)]">
          {error}
        </p>
      ) : null}
    </div>
  );
}
