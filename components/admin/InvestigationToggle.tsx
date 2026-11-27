"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

/**
 * Business Rules §11 from the Reviewers screen: an Administrator marks an
 * account under investigation (its votes count half) or clears it. An
 * operational action, audited by the API, which also refuses your own account.
 * It lived only on User Management, which is now the Super Admin's alone.
 */
export function InvestigationToggle({
  userId,
  name,
  underInvestigation,
}: {
  userId: string;
  name: string;
  underInvestigation: boolean;
}) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [on, setOn] = useState(underInvestigation);
  const [error, setError] = useState<string | null>(null);

  async function toggle() {
    setBusy(true);
    setError(null);
    try {
      const res = await fetch(`/api/bff/api/v1/admin/users/${encodeURIComponent(userId)}/investigation`, {
        method: "PUT",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ under_investigation: !on }),
      });
      if (!res.ok) {
        const p = (await res.json().catch(() => ({}))) as { detail?: string };
        setError(p.detail ?? "That didn't go through.");
        return;
      }
      setOn(!on);
      router.refresh();
    } catch {
      setError("Couldn't reach the server.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <span className="inline-flex flex-col items-start gap-1">
      <button
        type="button"
        onClick={toggle}
        disabled={busy}
        aria-label={on ? `Clear the investigation of ${name}` : `Mark ${name} under investigation`}
        className={`rounded-[var(--radius-pill)] px-2.5 py-1 text-[11px] font-semibold disabled:opacity-60 ${
          on
            ? "bg-[color-mix(in_srgb,var(--accent-danger)_12%,transparent)] text-[var(--accent-danger)]"
            : "border border-[var(--border-subtle)] text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
        }`}
      >
        {busy ? "Saving…" : on ? "Under investigation" : "Mark"}
      </button>
      {error ? (
        <span role="alert" className="text-[11px] text-[var(--accent-danger)]">
          {error}
        </span>
      ) : null}
    </span>
  );
}
