"use client";

import Link from "next/link";
import { useState } from "react";

import { unsubscribe } from "@/app/actions/unsubscribe";

import { SCOPE_COPY, type UnsubscribeScope } from "./unsubscribe-model";

/**
 * The button on /unsubscribe. A click, not the page load, turns the email off:
 * mail scanners open links, and an unsubscribe that fires on a GET would turn
 * people's email off behind their back.
 */
export function Unsubscribe({ token, scope, subscribed }: { token: string; scope: UnsubscribeScope; subscribed: boolean }) {
  const [done, setDone] = useState(!subscribed);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const copy = SCOPE_COPY[scope];

  async function go() {
    setBusy(true);
    setError(null);
    const out = await unsubscribe(token);
    setBusy(false);
    if (!out.ok) return setError(out.error ?? "That didn't work. Try again.");
    setDone(true);
  }

  return (
    <div className="flex flex-col items-center gap-4 text-center" data-testid="unsubscribe">
      {done ? (
        <p role="status" className="max-w-[28rem] text-[15px] text-[var(--text-primary)]">
          {copy.done}
        </p>
      ) : (
        <>
          <p className="max-w-[28rem] text-[15px] text-[var(--text-primary)]">Stop {copy.what}?</p>
          <button type="button" onClick={() => void go()} disabled={busy} className="h-10 rounded-full bg-[var(--accent-primary)] px-5 text-[14px] font-medium text-[var(--text-on-brand)] disabled:bg-[var(--disabled-surface)] disabled:text-[var(--disabled-text)]">
            {busy ? "Unsubscribing…" : "Unsubscribe"}
          </button>
        </>
      )}
      {error ? (
        <p role="alert" className="text-[13px] text-[var(--accent-danger)]">
          {error}
        </p>
      ) : null}
      <p className="text-[13px] text-[var(--text-secondary)]">
        You can turn it back on any time in your store&rsquo;s <Link href="/seller/dashboard" className="underline">Settings</Link>.
      </p>
    </div>
  );
}
