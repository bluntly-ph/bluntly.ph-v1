"use client";

import { useRouter } from "next/navigation";
import { useId, useState } from "react";
import { FIELD_STATES } from "@/components/console/fields";

/**
 * Attach an affiliate link to a review whose earnings are already approved.
 *
 * The same backend action as the queue's "Approve & attach affiliate"
 * (`POST /admin/reviews/{id}/referral-link`); here the approval has already
 * happened, so this only completes the affiliate setup. The platform choices
 * are the product's own listings, so a link cannot be filed against a
 * marketplace the product is not on.
 */
export function AttachAffiliateForm({
  reviewId,
  platforms,
  suggestedPlatform,
  subId,
}: {
  reviewId: string;
  platforms: string[];
  suggestedPlatform: string | null;
  subId: string;
}) {
  const router = useRouter();
  const urlId = useId();
  const platformId = useId();
  const [open, setOpen] = useState(false);
  const [url, setUrl] = useState("");
  const [platform, setPlatform] = useState(suggestedPlatform ?? platforms[0] ?? "lazada");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function attach() {
    if (busy) return;
    setBusy(true);
    setError(null);
    try {
      const res = await fetch(`/api/bff/api/v1/admin/reviews/${reviewId}/referral-link`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ url: url.trim(), platform, sub_id: subId }),
      });
      if (!res.ok) {
        const p = (await res.json().catch(() => ({}))) as { detail?: string; title?: string };
        setError(p.detail ?? p.title ?? "Couldn't attach the link.");
        return;
      }
      setOpen(false);
      setUrl("");
      router.refresh();
    } catch {
      setError("Couldn't reach the server.");
    } finally {
      setBusy(false);
    }
  }

  const pill =
    "h-8 cursor-pointer rounded-[var(--radius-pill)] px-3 text-[12px] font-semibold " +
    "disabled:cursor-wait disabled:opacity-60 focus-visible:outline focus-visible:outline-2 " +
    "focus-visible:outline-offset-2 focus-visible:outline-[var(--accent-primary)]";
  const field = `${FIELD_STATES} h-8 w-full rounded-[var(--radius-sm)] px-2.5 text-[12px]`;

  if (!open) {
    return (
      <button
        type="button"
        onClick={() => setOpen(true)}
        className={`${pill} border border-[var(--accent-primary)] text-[var(--accent-primary)]`}
      >
        Attach affiliate link
      </button>
    );
  }
  return (
    <div className="flex w-full flex-col gap-2 rounded-[var(--radius-sm)] bg-[var(--surface-app)] p-3">
      <label htmlFor={urlId} className="text-[11px] text-[var(--text-secondary)]">
        Affiliate link
      </label>
      <input
        id={urlId}
        value={url}
        onChange={(e) => setUrl(e.target.value.slice(0, 2048))}
        placeholder="https://…"
        inputMode="url"
        className={field}
      />
      <label htmlFor={platformId} className="text-[11px] text-[var(--text-secondary)]">
        Marketplace
      </label>
      <select
        id={platformId}
        value={platform}
        onChange={(e) => setPlatform(e.target.value)}
        className={`${field} cursor-pointer`}
      >
        {platforms.map((p) => (
          <option key={p} value={p}>
            {p}
          </option>
        ))}
      </select>
      <p className="text-[10px] text-[var(--text-secondary)]">
        Sub-ID for the affiliate dashboard: <code className="text-[var(--text-primary)]">{subId}</code>.
        Lazada links get it appended automatically; a Shopee link must be generated with it.
      </p>
      <div className="flex gap-2">
        <button
          type="button"
          onClick={() => void attach()}
          disabled={busy || url.trim().length === 0}
          className={`${pill} bg-[var(--accent-primary)] text-white`}
        >
          {busy ? "Attaching…" : "Attach"}
        </button>
        <button
          type="button"
          onClick={() => setOpen(false)}
          disabled={busy}
          className={`${pill} border border-[var(--base-ink-800)] text-[var(--text-primary)]`}
        >
          Cancel
        </button>
      </div>
      {error ? (
        <p role="alert" className="text-[12px] text-[var(--accent-danger)]">
          {error}
        </p>
      ) : null}
    </div>
  );
}

export default AttachAffiliateForm;
