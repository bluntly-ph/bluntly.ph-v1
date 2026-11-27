"use client";

import { useRouter } from "next/navigation";
import { useId, useState } from "react";
import { ArrowBendUpLeft, ArrowFatDown, ArrowFatUp, ChatCircle, Flag, LinkSimple, Trash } from "@phosphor-icons/react";

import { ReportDialog } from "@/components/review/ReportDialog";
import { ShareSheet } from "@/components/share/ShareSheet";
import { OverflowMenu } from "@/components/ui/OverflowMenu";
import { APPEAL_KINDS, appealKind, type AppealKind } from "@/components/seller/console/appeal-kinds";
import { PUBLIC_EDGE_STATES } from "@/components/ui/field-styles";

type Reply = {
  id: string;
  body: string;
  created_at: string;
  author: { id?: string; username: string | null; display_name: string | null } | null;
};

type Mode = "idle" | "respond" | "appeal";

const VOTE =
  "inline-flex min-h-8 cursor-pointer items-center gap-1 rounded-[16px] px-1.5 text-[12px] text-[var(--text-primary)] hover:bg-[var(--line-hairline-10)] disabled:cursor-default disabled:hover:bg-transparent focus-visible:outline focus-visible:outline-2 focus-visible:outline-[var(--accent-primary)]";

const CONTROL =
  "inline-flex cursor-pointer items-center gap-1 text-[12px] text-[var(--text-secondary)] hover:text-[var(--accent-primary)] disabled:opacity-60 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--accent-primary)]";

async function problem(res: Response, fallback: string): Promise<string> {
  const p = (await res.json().catch(() => ({}))) as { detail?: unknown };
  return typeof p.detail === "string" ? p.detail : fallback;
}

/**
 * The controls under one seller review (QA-043), limited to what Business
 * Rules §9–§10 give each person over it:
 *
 *   * everyone — Share, a link straight to this review, through the app's
 *     share sheet (QA-024);
 *   * the store's claimed owner — one public response (editable) and "Flag as
 *     suspected fake", which opens an appeal an admin reviews. A claim grants
 *     nothing more: never removal, hiding or suppression (§9).
 *
 * Owner decision, 2026-09-28 (the retest still found "only Share"): a seller
 * review now carries the same row as any review — Helpful / Not helpful
 * (helpfulness only: they move no rating, trust or money), Reply (one flat
 * thread; the store keeps its single response), Share, and "⋯" with Copy link
 * and Report (the ordinary moderation queue). The author cannot vote on their
 * own review, and the store's owner answers through its response, not a reply
 * or a vote — the API enforces both.
 */
export function SellerReviewActions({
  reviewId,
  sellerId,
  isOwner,
  hasResponse,
  currentResponse,
  viewerId = null,
  reviewerId = null,
  helpful = 0,
  unhelpful = 0,
  myVote = null,
  replies = [],
}: {
  reviewId: string;
  sellerId: string;
  isOwner: boolean;
  hasResponse: boolean;
  currentResponse: string | null;
  /** The signed-in viewer, or null for a visitor. */
  viewerId?: string | null;
  reviewerId?: string | null;
  helpful?: number;
  unhelpful?: number;
  myVote?: "up" | "down" | null;
  replies?: Reply[];
}) {
  const router = useRouter();
  const fieldId = useId();
  const replyId = useId();
  const [mode, setMode] = useState<Mode>("idle");
  const [votes, setVotes] = useState({ up: helpful, down: unhelpful, mine: myVote });
  const [voting, setVoting] = useState(false);
  const [replying, setReplying] = useState(false);
  const [replyText, setReplyText] = useState("");
  const [thread, setThread] = useState<Reply[]>(replies);
  const [copied, setCopied] = useState(false);
  const ownReview = viewerId !== null && viewerId === reviewerId;
  const canVote = !ownReview && !isOwner;

  function toLogin() {
    router.push(`/login?next=${encodeURIComponent(`/sellers/${sellerId}#seller-review-${reviewId}`)}`);
  }

  async function vote(direction: "up" | "down") {
    if (!viewerId) return toLogin();
    if (voting) return;
    setVoting(true);
    setError(null);
    try {
      const undo = votes.mine === direction;
      const res = await fetch(`/api/bff/api/v1/sellers/reviews/${reviewId}/vote`, {
        method: undo ? "DELETE" : "PUT",
        headers: undo ? undefined : { "content-type": "application/json" },
        body: undo ? undefined : JSON.stringify({ direction }),
      });
      if (!res.ok) {
        setError(await problem(res, "Couldn't record your vote."));
        return;
      }
      const out = (await res.json()) as { helpful_votes: number; unhelpful_votes: number; my_vote: "up" | "down" | null };
      setVotes({ up: out.helpful_votes, down: out.unhelpful_votes, mine: out.my_vote });
    } catch {
      setError("Couldn't reach the server.");
    } finally {
      setVoting(false);
    }
  }

  async function sendReply() {
    const body = replyText.trim();
    if (!body || busy) return;
    setBusy(true);
    setError(null);
    try {
      const res = await fetch(`/api/bff/api/v1/sellers/reviews/${reviewId}/replies`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ body }),
      });
      if (!res.ok) {
        setError(await problem(res, "Couldn't post your reply."));
        return;
      }
      const reply = (await res.json()) as Reply;
      setThread((t) => [...t, reply]);
      setReplyText("");
      setReplying(false);
    } catch {
      setError("Couldn't reach the server.");
    } finally {
      setBusy(false);
    }
  }

  async function deleteReply(id: string) {
    setError(null);
    const res = await fetch(`/api/bff/api/v1/sellers/replies/${id}`, { method: "DELETE" }).catch(() => null);
    if (!res || !res.ok) {
      setError("Couldn't delete the reply.");
      return;
    }
    setThread((t) => t.filter((r) => r.id !== id));
  }

  async function copyLink() {
    try {
      await navigator.clipboard.writeText(
        new URL(`/sellers/${sellerId}#seller-review-${reviewId}`, window.location.origin).toString(),
      );
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      /* clipboard refused: nothing to report */
    }
  }
  const [text, setText] = useState("");
  const [kind, setKind] = useState<AppealKind>("never_ordered");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  function open(next: Mode) {
    setError(null);
    setNotice(null);
    setText(next === "respond" ? (currentResponse ?? "") : "");
    setMode(next);
  }

  async function submit() {
    if (busy) return;
    const body = text.trim();
    if (mode === "appeal" && body.length < 10) {
      setError("Say what is wrong with this review (at least 10 characters).");
      return;
    }
    if (mode === "respond" && !body) {
      setError("Write a response first.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const path = mode === "respond" ? "response" : "appeal";
      const res = await fetch(`/api/bff/api/v1/sellers/reviews/${reviewId}/${path}`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(mode === "respond" ? { body } : { reason: body, kind }),
      });
      if (!res.ok) {
        setError(await problem(res, mode === "respond" ? "Couldn't post your response." : "Couldn't send the appeal."));
        return;
      }
      setNotice(
        mode === "respond"
          ? "Your response is posted."
          : "Sent. An admin will review it and may ask the reviewer to back up their review.",
      );
      setMode("idle");
      router.refresh();
    } catch {
      setError("Couldn't reach the server.");
    } finally {
      setBusy(false);
    }
  }

  const menu = [
    {
      key: "copy",
      label: copied ? "Link copied" : "Copy link",
      icon: <LinkSimple size={16} aria-hidden="true" />,
      onSelect: copyLink,
    },
    ...(!ownReview
      ? [
          {
            key: "report",
            label: "Report this review",
            icon: <Flag size={16} aria-hidden="true" />,
            onSelect: () =>
              viewerId ? document.getElementById(`report-trigger-seller-review-${reviewId}`)?.click() : toLogin(),
          },
        ]
      : []),
  ];

  return (
    <div className="mt-3">
      <div className="flex flex-wrap items-center gap-x-6 gap-y-2">
        <div className="flex items-center gap-3">
          <button
            type="button"
            onClick={() => vote("up")}
            disabled={voting || !canVote}
            aria-pressed={votes.mine === "up"}
            aria-label={`Helpful, ${votes.up}`}
            title={!canVote ? (ownReview ? "Your own review" : "Your store") : undefined}
            className={VOTE}
          >
            <ArrowFatUp
              size={18}
              weight="fill"
              aria-hidden="true"
              className={votes.mine === "up" ? "text-[var(--accent-success)]" : "text-[var(--base-gray-400)]"}
            />
            <span aria-hidden="true" className="min-w-[1ch] [font-variant-numeric:tabular-nums]">{votes.up}</span>
          </button>
          <button
            type="button"
            onClick={() => vote("down")}
            disabled={voting || !canVote}
            aria-pressed={votes.mine === "down"}
            aria-label={`Not helpful, ${votes.down}`}
            className={VOTE}
          >
            <ArrowFatDown
              size={18}
              weight="fill"
              aria-hidden="true"
              className={votes.mine === "down" ? "text-[var(--accent-danger)]" : "text-[var(--base-gray-400)]"}
            />
            <span aria-hidden="true" className="min-w-[1ch] [font-variant-numeric:tabular-nums]">{votes.down}</span>
          </button>
        </div>
        {!isOwner ? (
          <button
            type="button"
            onClick={() => (viewerId ? setReplying((v) => !v) : toLogin())}
            aria-expanded={replying}
            className={CONTROL}
          >
            <ArrowBendUpLeft size={18} aria-hidden="true" /> Reply
          </button>
        ) : null}
        {/* QA-024/043: the app's own share sheet, as on reviews. */}
        <ShareSheet
          path={`/sellers/${sellerId}#seller-review-${reviewId}`}
          title="A review of this store"
          variant="inline"
        />
        <OverflowMenu label="More actions for this store review" items={menu} />
        {isOwner ? (
          <>
            <button type="button" onClick={() => open("respond")} className={CONTROL}>
              <ChatCircle size={18} aria-hidden="true" />
              {hasResponse ? "Edit your response" : "Respond as the store"}
            </button>
            <button type="button" onClick={() => open("appeal")} className={CONTROL}>
              <Flag size={18} aria-hidden="true" /> Flag this review
            </button>
          </>
        ) : null}
      </div>

      {thread.length > 0 ? (
        <ul aria-label="Replies" className="mt-3 flex flex-col gap-2 border-l-2 border-[var(--line-hairline-10)] pl-3">
          {thread.map((r) => (
            <li key={r.id} className="text-[12px] text-[var(--text-primary)]" data-testid="seller-reply">
              <p className="flex items-center gap-2 text-[11px] text-[var(--text-secondary)]">
                <span>@{r.author?.username ?? "member"}</span>
                <span aria-hidden="true">·</span>
                <time dateTime={r.created_at}>
                  {new Date(r.created_at).toLocaleDateString("en-PH", { dateStyle: "medium" })}
                </time>
                {viewerId && r.author?.id === viewerId ? (
                  <button
                    type="button"
                    onClick={() => deleteReply(r.id)}
                    aria-label="Delete your reply"
                    className="ml-auto inline-flex cursor-pointer items-center gap-1 text-[var(--text-secondary)] hover:text-[var(--accent-danger)]"
                  >
                    <Trash size={14} aria-hidden="true" /> Delete
                  </button>
                ) : null}
              </p>
              <p className="mt-0.5 whitespace-pre-line font-light leading-[18px] [overflow-wrap:anywhere]">{r.body}</p>
            </li>
          ))}
        </ul>
      ) : null}

      {replying ? (
        <div className="mt-3 flex flex-col gap-2">
          <label htmlFor={replyId} className="sr-only">
            Your reply
          </label>
          <textarea
            id={replyId}
            value={replyText}
            onChange={(e) => setReplyText(e.target.value.slice(0, 1000))}
            rows={2}
            placeholder="Reply to this review. Links aren't allowed."
            className={`w-full resize-y rounded-[var(--radius-sm)] bg-[var(--surface-card)] p-2.5 text-[12px] text-[var(--text-primary)] placeholder:text-[var(--text-muted)] ${PUBLIC_EDGE_STATES}`}
          />
          <div className="flex items-center gap-3">
            <button
              type="button"
              onClick={sendReply}
              disabled={busy || !replyText.trim()}
              className="h-8 cursor-pointer rounded-[var(--radius-pill)] bg-[var(--accent-primary)] px-3 text-[12px] font-semibold text-white disabled:cursor-not-allowed disabled:opacity-60"
            >
              {busy ? "Sending…" : "Post reply"}
            </button>
            <button
              type="button"
              onClick={() => setReplying(false)}
              className="cursor-pointer text-[12px] text-[var(--text-secondary)] underline-offset-4 hover:underline"
            >
              Cancel
            </button>
          </div>
        </div>
      ) : null}

      {viewerId && !ownReview ? (
        <ReportDialog reviewId={reviewId} sellerReviewId={reviewId} canReport hideTrigger />
      ) : null}

      {mode !== "idle" ? (
        <div className="mt-3 flex flex-col gap-2">
          {mode === "appeal" ? (
            <fieldset className="flex flex-wrap gap-2">
              <legend className="pb-1.5 text-[12px] font-medium text-[var(--text-primary)]">What&rsquo;s wrong with it?</legend>
              {APPEAL_KINDS.map((k) => (
                <label key={k.kind} className={`flex cursor-pointer items-center gap-2 rounded-full border px-3 py-1.5 text-[12px] ${kind === k.kind ? "border-[var(--text-primary)]" : "border-[var(--border-subtle)]"}`}>
                  <input type="radio" name={`${fieldId}-kind`} value={k.kind} checked={kind === k.kind} onChange={() => setKind(k.kind)} className="accent-[var(--accent-primary)]" />
                  {k.label}
                </label>
              ))}
            </fieldset>
          ) : null}
          <label htmlFor={fieldId} className="text-[12px] font-medium text-[var(--text-primary)]">
            {mode === "respond" ? "Your public response" : appealKind(kind).prompt}
          </label>
          <textarea
            id={fieldId}
            value={text}
            onChange={(e) => setText(e.target.value.slice(0, 2000))}
            rows={3}
            className={`w-full resize-y rounded-[var(--radius-sm)] bg-[var(--surface-card)] p-2.5 text-[12px] text-[var(--text-primary)] placeholder:text-[var(--text-muted)] ${PUBLIC_EDGE_STATES}`}
            placeholder={
              mode === "respond"
                ? "Shown under the review, with your store's name. Links aren't allowed."
                : `Only an admin sees this. ${appealKind(kind).check}`
            }
          />
          <div className="flex items-center gap-3">
            <button
              type="button"
              onClick={submit}
              disabled={busy}
              className="h-8 cursor-pointer rounded-[var(--radius-pill)] bg-[var(--accent-primary)] px-3 text-[12px] font-semibold text-white disabled:cursor-wait disabled:opacity-60"
            >
              {busy ? "Sending…" : mode === "respond" ? "Post response" : "Send to an admin"}
            </button>
            <button
              type="button"
              onClick={() => setMode("idle")}
              className="cursor-pointer text-[12px] text-[var(--text-secondary)] underline-offset-4 hover:underline"
            >
              Cancel
            </button>
          </div>
        </div>
      ) : null}

      {error ? (
        <p role="alert" className="mt-2 text-[12px] text-[var(--accent-danger)]">
          {error}
        </p>
      ) : null}
      {notice ? (
        <p role="status" className="mt-2 text-[12px] text-[var(--text-secondary)]">
          {notice}
        </p>
      ) : null}
    </div>
  );
}
