"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { Button } from "@/components/ui/Button";

/**
 * The asker awards the Best Answer to their request (dev/QA sync 2026-09-29).
 *
 * The request then leaves the Bounty Board, which lists open requests only,
 * and stays on its own page with this answer pinned first. Only the asker is
 * shown this button; the server refuses anyone else either way.
 */
export function BestAnswerButton({ requestId, reviewId }: { requestId: string; reviewId: string }) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function pick() {
    if (busy) return;
    setBusy(true);
    setError(null);
    try {
      const res = await fetch(`/api/bff/api/v1/requests/${requestId}/best-answer`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ review_id: reviewId }),
      });
      if (!res.ok) {
        const p = (await res.json().catch(() => ({}))) as { detail?: string };
        setError(p.detail ?? "Couldn't pick that answer.");
        return;
      }
      router.refresh();
    } catch {
      setError("Couldn't reach the server.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mt-2 flex flex-col items-start gap-1">
      <Button type="button" size="sm" onClick={() => void pick()} disabled={busy}>
        {busy ? "Picking…" : "Pick as Best Answer"}
      </Button>
      {error ? (
        <p role="alert" className="text-[12px] text-[var(--accent-danger)]">
          {error}
        </p>
      ) : null}
    </div>
  );
}
