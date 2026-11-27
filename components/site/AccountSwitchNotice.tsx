"use client";

import { useEffect, useState } from "react";

import { ACCOUNT_KEY, accountSwitchMessage } from "./account-switch-model";

/**
 * Rendered by every page header (QA-061; see account-switch-model.ts). It
 * records the account this page was rendered for, and tells the reader when
 * another tab of this browser signs in as someone else — compared with THIS
 * page's account, so two tabs of the same account never warn each other.
 */
export function AccountSwitchNotice({ username }: { username: string | null | undefined }) {
  const [message, setMessage] = useState<string | null>(null);

  useEffect(() => {
    if (username) {
      try {
        window.localStorage.setItem(ACCOUNT_KEY, username);
      } catch {
        // Storage blocked (private mode, site data off): the notice stays quiet.
      }
    }
    const onStorage = (event: StorageEvent) => {
      if (event.key !== ACCOUNT_KEY) return;
      setMessage(accountSwitchMessage(username ?? null, event.newValue));
    };
    window.addEventListener("storage", onStorage);
    return () => window.removeEventListener("storage", onStorage);
  }, [username]);

  if (!message) return null;
  return (
    <div
      role="alert"
      data-testid="account-switch-notice"
      className="fixed inset-x-0 top-0 z-[60] flex flex-wrap items-center justify-center gap-3 bg-[var(--text-primary)] px-4 py-3 text-center text-[13px] text-[var(--surface-app)]"
    >
      <p className="max-w-[44rem]">{message}</p>
      <button
        type="button"
        onClick={() => window.location.reload()}
        className="rounded-[var(--radius-pill)] bg-[var(--accent-primary)] px-4 py-1.5 font-semibold text-white"
      >
        Reload
      </button>
      <button type="button" onClick={() => setMessage(null)} className="underline underline-offset-2">
        Dismiss
      </button>
    </div>
  );
}
