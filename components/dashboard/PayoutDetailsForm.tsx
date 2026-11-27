"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { Check, Lock } from "@phosphor-icons/react/dist/ssr";
import { PUBLIC_INPUT } from "@/components/ui/field-styles";

/**
 * Screen/Payout/Details (Figma 7843:9432): where payouts go and the name on
 * that account, saved with PATCH /auth/me/payout-account.
 *
 * Payouts are sent by PayPal (Completion contract X.4: GCash and Maya are only
 * simulated), so PayPal is the one method, drawn as the frame's selected
 * PayoutMethod card; the frame's "Add bank or e-wallet" row is not drawn —
 * there is no other way to be paid yet. The full address is never sent back
 * to the page, so the field shows the masked one and is only needed to change it.
 */
const EMAIL = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

export function PayoutDetailsForm({
  masked,
  accountName,
}: {
  masked: string | null;
  accountName: string | null;
}) {
  const router = useRouter();
  const [name, setName] = useState(accountName ?? "");
  const [email, setEmail] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // Field errors sit under their field (Figma Payout/Details/Error 7855:11365).
  const [nameError, setNameError] = useState<string | null>(null);
  const [emailError, setEmailError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  async function save(e: React.FormEvent) {
    e.preventDefault();
    if (busy) return;
    const body: Record<string, string> = {};
    if (name.trim() && name.trim() !== (accountName ?? "")) body.account_name = name.trim();
    if (email.trim()) body.payout_account = email.trim();
    setNameError(null);
    setEmailError(null);
    if (!masked && !body.payout_account) {
      setEmailError("Enter the PayPal email to send payouts to.");
      return;
    }
    if (body.payout_account && !EMAIL.test(body.payout_account)) {
      setEmailError("That isn't an email address. Use the one you sign in to PayPal with.");
      return;
    }
    if (Object.keys(body).length === 0) {
      setError("Nothing to save yet.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const res = await fetch("/api/bff/api/v1/auth/me/payout-account", {
        method: "PATCH",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(body),
      });
      if (!res.ok) {
        const p = (await res.json().catch(() => ({}))) as { detail?: unknown; errors?: { loc?: unknown[] }[] };
        const fields = (p.errors ?? []).map((x) => x.loc?.[x.loc.length - 1]);
        if (fields.includes("payout_account")) setEmailError("That email address isn't valid. Check it and try again.");
        if (fields.includes("account_name")) setNameError("Use up to 120 characters, as it appears on your PayPal account.");
        if (!fields.includes("payout_account") && !fields.includes("account_name")) {
          setError(typeof p.detail === "string" ? p.detail : "Couldn't save those details.");
        }
        return;
      }
      setSaved(true);
      router.push("/dashboard/transfer");
      router.refresh();
    } catch {
      setError("Couldn't reach the server.");
    } finally {
      setBusy(false);
    }
  }

  // Figma TextField (6808:456): every state, including Error from aria-invalid,
  // from the shared public field classes.
  const field = PUBLIC_INPUT;

  return (
    <form onSubmit={save} className="flex flex-1 flex-col" noValidate>
      <div className="flex flex-col gap-4 px-4 pb-4">
        <section aria-label="Send payouts to" className="rounded-[32px] bg-[var(--surface-app)] p-[3px]">
          <div className="flex flex-col gap-[10px] rounded-[32px] bg-[var(--surface-card)] p-5">
            <h2 className="text-[12px] leading-normal text-[var(--chart-honesty-fund)]">Send payouts to</h2>
            <div
              aria-current="true"
              className="flex items-center gap-3 rounded-[16px] border border-[var(--accent-primary)] bg-[var(--status-high-bg)] p-3"
            >
              <span aria-hidden className="grid size-10 shrink-0 place-items-center rounded-[12px] bg-[#003087] text-[14px] font-semibold leading-none text-white">
                P
              </span>
              <span className="flex min-w-0 flex-1 flex-col gap-[2px] leading-none text-[var(--accent-primary)]">
                <span className="text-[14px] font-medium">PayPal</span>
                <span className="truncate text-[12px]">{masked ?? "Not set yet"}</span>
              </span>
              <Check size={20} aria-hidden className="text-[var(--accent-primary)]" />
            </div>
          </div>
        </section>

        <section aria-label="PayPal account" className="rounded-[32px] bg-[var(--surface-app)] p-[3px]">
          <div className="flex flex-col gap-3 rounded-[32px] bg-[var(--surface-card)] p-5">
            <h2 className="text-[12px] leading-normal text-[var(--chart-honesty-fund)]">PayPal account</h2>
            <label className="flex flex-col gap-[6px]">
              <span className="text-[12px] leading-none text-[var(--base-gray-400)]">Account name</span>
              <input
                className={field}
                aria-invalid={nameError ? true : undefined}
                aria-describedby={nameError ? "payout-name-error" : undefined}
                value={name}
                onChange={(e) => setName(e.target.value)}
                autoComplete="name"
                maxLength={120}
                placeholder="Name on the account"
              />
              {nameError ? (
                <span id="payout-name-error" role="alert" className="text-[12px] leading-[1.4] text-[var(--accent-danger)]">
                  {nameError}
                </span>
              ) : null}
            </label>
            <label className="flex flex-col gap-[6px]">
              <span className="text-[12px] leading-none text-[var(--base-gray-400)]">PayPal email</span>
              <input
                className={field}
                aria-invalid={emailError ? true : undefined}
                aria-describedby={emailError ? "payout-email-error" : undefined}
                type="email"
                inputMode="email"
                autoComplete="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder={masked ? `${masked} (unchanged)` : "you@example.com"}
              />
              {emailError ? (
                <span id="payout-email-error" role="alert" className="text-[12px] leading-[1.4] text-[var(--accent-danger)]">
                  {emailError}
                </span>
              ) : null}
            </label>
            <p className="flex items-start gap-2 text-[12px] leading-[1.5] text-[var(--base-gray-400)]">
              <Lock size={16} aria-hidden className="mt-px shrink-0" />
              Use the name on your PayPal account. Payouts to a different name are sent back.
            </p>
          </div>
        </section>
        {error ? (
          <p role="alert" className="px-1 text-[12px] font-medium text-[var(--accent-danger)]">
            {error}
          </p>
        ) : null}
        {saved ? (
          <p role="status" className="px-1 text-[12px] text-[var(--text-primary)]">
            Saved.
          </p>
        ) : null}
      </div>
      <div className="flex-1" />
      <div className="sticky bottom-0 bg-[var(--surface-card)] px-4 pb-6 pt-2">
        <button
          type="submit"
          disabled={busy}
          className="flex h-14 w-full cursor-pointer items-center justify-center rounded-[var(--radius-pill)] bg-[var(--accent-primary)] px-6 text-[16px] font-semibold leading-none text-[var(--text-on-brand)] transition-transform duration-[120ms] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--accent-primary)] enabled:active:scale-[0.97] disabled:cursor-not-allowed disabled:opacity-60 motion-reduce:transition-none motion-reduce:active:scale-100"
        >
          {busy ? "Saving…" : "Save"}
        </button>
      </div>
    </form>
  );
}
