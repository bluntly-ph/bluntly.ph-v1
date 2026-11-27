"use client";

import { useRouter } from "next/navigation";
import { useEffect, useId, useState } from "react";
import { Bell, ClockCounterClockwise, Coins, EyeSlash, HandHeart, LinkSimple } from "@phosphor-icons/react/dist/ssr";

import { ConfirmDialog, Consequence } from "@/components/admin/ConfirmDialog";
import type { QueueItem } from "@/lib/moderation";
import { countState } from "@/components/console/counted-model";
import { CountedTextarea } from "@/components/console/CountedTextarea";
import { FIELD_STATES } from "@/components/console/fields";

const REASON_MAX = 500;

/**
 * The review modal's footer (Overlay/Queue/Review 8042:13037): Open on site and Take down on the
 * left, the keyboard hints, then Reject earnings, Approve & attach link and
 * Approve earnings. Each verb opens its Confirm/Queue/* dialog first; the
 * endpoints and their rules are the ones ReviewDecision always used:
 *
 *   Approve earnings     POST /admin/reviews/{id}/approve-earnings
 *                        (2 stars or fewer routes to the Honesty Fund)
 *   Approve & attach     POST /admin/reviews/{id}/referral-link
 *   Reject earnings      POST /admin/reviews/{id}/reject    (reason to the author)
 *   Take down            POST /admin/reviews/{id}/unpublish (reason recorded)
 *   Restore              POST /admin/reviews/{id}/restore   (taken-down reviews)
 *
 * A, L and R open the dialogs from the keyboard while the modal is open.
 */

const PLATFORMS = ["shopee", "lazada", "amazon", "other"] as const;
type Dialog = "approve" | "attach" | "reject" | "takedown" | "restore" | null;

export function QueueDecisionBar({ item, onDecided }: { item: QueueItem; onDecided: () => void }) {
  const router = useRouter();
  const ids = { reason: useId(), takedown: useId(), url: useId(), platform: useId() };
  const [dialog, setDialog] = useState<Dialog>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [reason, setReason] = useState("");
  const [url, setUrl] = useState("");
  const [platform, setPlatform] = useState<string>(item.suggested_platform ?? "shopee");

  const reviewId = item.review.id;
  const takenDown = item.review.published_at == null;
  const toFund = item.review.star_rating <= 2;
  const author = item.author?.display_name ?? "The author";

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      const t = e.target as HTMLElement | null;
      if (dialog || e.metaKey || e.ctrlKey || e.altKey) return;
      if (t && (t.tagName === "INPUT" || t.tagName === "TEXTAREA" || t.tagName === "SELECT")) return;
      const key = e.key.toLowerCase();
      if (key === "a") setDialog(takenDown ? "restore" : "approve");
      else if (key === "l" && !takenDown) setDialog("attach");
      else if (key === "r") setDialog("reject");
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [dialog, takenDown]);

  function close() {
    if (busy) return;
    setDialog(null);
    setError(null);
  }

  async function send(path: string, body?: unknown) {
    setBusy(true);
    setError(null);
    try {
      const res = await fetch(`/api/bff/api/v1/admin/reviews/${reviewId}/${path}`, {
        method: "POST",
        headers: body ? { "content-type": "application/json" } : undefined,
        body: body ? JSON.stringify(body) : undefined,
      });
      if (!res.ok) {
        const problem = (await res.json().catch(() => ({}))) as { detail?: string; title?: string };
        setError(problem.detail ?? problem.title ?? "Couldn't record the decision.");
        return;
      }
      setDialog(null);
      setReason("");
      setUrl("");
      onDecided();
      router.refresh();
    } catch {
      setError("Couldn't reach the server.");
    } finally {
      setBusy(false);
    }
  }

  const outline = "h-8 rounded-full border px-3 text-[12px] font-medium disabled:opacity-60";
  const kbd = "rounded-[4px] border border-[var(--border-default)] px-1 text-[10px] leading-[14px]";
  const field = `${FIELD_STATES} h-12 w-full rounded-[12px] px-4 text-[14px]`;

  return (
    <div className="flex flex-wrap items-center gap-x-6 gap-y-3 border-t border-[var(--border-subtle)] px-6 py-4">
      {/* Overlay/Review/Investigate's "Open on site" (8109:17496): the public
          review, in a new tab so the queue keeps its place. A taken-down
          review has no public page, so it has no link. */}
      {!takenDown ? (
        <a
          href={`/reviews/${reviewId}`}
          target="_blank"
          rel="noopener"
          className="text-[12px] font-medium text-[var(--accent-primary)] hover:underline"
        >
          Open on site<span className="sr-only"> (opens in a new tab)</span>
        </a>
      ) : null}
      {takenDown ? (
        <button type="button" onClick={() => setDialog("restore")} className="text-[12px] font-medium text-[var(--accent-primary)]">
          Restore
        </button>
      ) : (
        <button type="button" onClick={() => setDialog("takedown")} className="text-[12px] font-medium text-[var(--accent-primary)]">
          Take down
        </button>
      )}

      <p className="hidden items-center gap-4 text-[12px] text-[var(--text-secondary)] lg:flex" aria-label="Keyboard shortcuts">
        <span className="inline-flex items-center gap-1.5"><kbd className={kbd}>A</kbd> {takenDown ? "restore" : "approve"}</span>
        {!takenDown ? <span className="inline-flex items-center gap-1.5"><kbd className={kbd}>L</kbd> approve &amp; link</span> : null}
        <span className="inline-flex items-center gap-1.5"><kbd className={kbd}>R</kbd> reject</span>
        <span className="inline-flex items-center gap-1.5"><kbd className={kbd}>J/K</kbd> next / previous</span>
      </p>

      <div className="ml-auto flex flex-wrap gap-2">
        <button type="button" onClick={() => setDialog("reject")} className={`${outline} border-[var(--base-ink-800)]`}>
          Reject earnings
        </button>
        {!takenDown ? (
          <>
            <button type="button" onClick={() => setDialog("attach")} className={`${outline} border-[var(--base-ink-800)]`}>
              Approve &amp; attach link
            </button>
            <button
              type="button"
              onClick={() => setDialog("approve")}
              className="h-8 rounded-full bg-[var(--accent-primary)] px-4 text-[12px] font-medium text-white"
            >
              Approve earnings
            </button>
          </>
        ) : null}
      </div>

      <ConfirmDialog
        open={dialog === "approve"}
        title="Approve earnings?"
        confirmLabel="Approve earnings"
        busyLabel="Approving…"
        busy={busy}
        error={error}
        onClose={close}
        onConfirm={() => void send("approve-earnings")}
      >
        {toFund ? (
          <Consequence icon={<HandHeart size={18} />}>
            Two stars or fewer: its earnings go to the Honesty Fund pool.
          </Consequence>
        ) : (
          <Consequence icon={<Coins size={18} />}>
            This review starts earning once an affiliate link is attached.
          </Consequence>
        )}
        <Consequence icon={<Bell size={18} />}>{author} is told it was approved.</Consequence>
        <Consequence icon={<ClockCounterClockwise size={18} />}>The decision is recorded in the Activity log.</Consequence>
      </ConfirmDialog>

      <ConfirmDialog
        open={dialog === "attach"}
        title="Approve & attach link"
        confirmLabel="Approve & attach"
        busyLabel="Attaching…"
        busy={busy}
        disabled={url.trim().length === 0}
        error={error}
        onClose={close}
        onConfirm={() => void send("referral-link", { url: url.trim(), platform, sub_id: item.suggested_sub_id })}
      >
        <Consequence icon={<LinkSimple size={18} />}>
          Approves earnings and attaches the link in one step. One active link per review.
        </Consequence>
        <label htmlFor={ids.platform} className="text-[12px] text-[var(--text-secondary)]">Marketplace</label>
        <select id={ids.platform} value={platform} onChange={(e) => setPlatform(e.target.value)} className={`${field} cursor-pointer`}>
          {PLATFORMS.map((p) => (
            <option key={p} value={p}>{p.charAt(0).toUpperCase() + p.slice(1)}</option>
          ))}
        </select>
        <label htmlFor={ids.url} className="text-[12px] text-[var(--text-secondary)]">Affiliate URL</label>
        <input
          id={ids.url}
          value={url}
          onChange={(e) => setUrl(e.target.value.slice(0, 2048))}
          placeholder="https://…"
          inputMode="url"
          className={field}
        />
        {item.suggested_sub_id ? (
          <p className="text-[12px] text-[var(--text-secondary)]">
            Put sub-ID <code className="text-[var(--text-primary)]">{item.suggested_sub_id}</code> in the affiliate
            dashboard so the commission can be attributed when the report comes back.
          </p>
        ) : null}
      </ConfirmDialog>

      <ConfirmDialog
        open={dialog === "reject"}
        title="Reject earnings?"
        confirmLabel="Reject earnings"
        busyLabel="Rejecting…"
        tone="danger"
        busy={busy}
        disabled={reason.trim().length === 0 || countState(reason, REASON_MAX).over}
        error={error}
        onClose={close}
        onConfirm={() => void send("reject", { reason: reason.trim() })}
      >
        <p>The review stays public; it just won&apos;t earn.</p>
        <CountedTextarea id={ids.reason} label={<>Reason — sent to {author} as written</>} value={reason} onChange={setReason} max={REASON_MAX} rows={3} />
      </ConfirmDialog>

      <ConfirmDialog
        open={dialog === "takedown"}
        title="Take this review down?"
        confirmLabel="Take down"
        busyLabel="Taking down…"
        tone="ink"
        busy={busy}
        disabled={reason.trim().length === 0 || countState(reason, REASON_MAX).over}
        error={error}
        onClose={close}
        onConfirm={() => void send("unpublish", { reason: reason.trim() })}
      >
        <Consequence icon={<EyeSlash size={18} />}>
          Removes it from public view. Its earning decision is left as it is, and Restore brings it back.
        </Consequence>
        <CountedTextarea id={ids.takedown} label={<>Why is it coming down? Recorded, and sent to {author}.</>} value={reason} onChange={setReason} max={REASON_MAX} rows={3} />
      </ConfirmDialog>

      <ConfirmDialog
        open={dialog === "restore"}
        title="Restore this review?"
        confirmLabel="Restore"
        busyLabel="Restoring…"
        busy={busy}
        error={error}
        onClose={close}
        onConfirm={() => void send("restore")}
      >
        <p>It goes back on the public site. Its earnings can be decided once it is public again.</p>
      </ConfirmDialog>
    </div>
  );
}
