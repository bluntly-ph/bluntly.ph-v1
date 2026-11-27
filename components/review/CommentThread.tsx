"use client";

import { useRouter } from "next/navigation";
import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import {
  ArrowBendDownRight,
  ArrowFatDown,
  ArrowFatUp,
  ArrowsDownUp,
  BellSimple,
  BellSimpleSlash,
  BookmarkSimple,
  DotsThree,
  Flag,
  PaperPlaneRight,
  Trash,
} from "@phosphor-icons/react/dist/ssr";

import type { Comment } from "@/lib/comments";
import { AuthorHeader } from "@/components/review/AuthorHeader";
import {
  DEFAULT_COMMENT_SORT,
  arrangeByOrder,
  sortComments,
  type CommentSort,
} from "@/components/review/comment-sort-model";
import { ReportDialog } from "@/components/review/ReportDialog";
import { OverflowMenu } from "@/components/ui/OverflowMenu";
import { SortCommentsMenu } from "@/components/review/SortCommentsMenu";
import { removeFromThread, replyOpening, visibleThread } from "@/components/review/comment-tree-model";
import { ShareSheet } from "@/components/share/ShareSheet";
import { ComposerShell } from "@/components/ui/ComposerShell";
import { usablePhoto } from "@/lib/image";
import { markInteraction } from "@/lib/reading-telemetry-events";
import { PUBLIC_EDGE_STATES } from "@/components/ui/field-styles";

/**
 * Local copies — lib/reviews is server-only, so it can't be imported here.
 *
 * `now` is the instant the server rendered the page, passed down. Read from the
 * clock here, the server's "1m" and the hydrating client's "2m" disagreed
 * whenever a comment's age crossed a unit in between: React error #418, the
 * same fault the seller page had (`shortAge`, 2026-09-29).
 */
function ageLabel(iso: string, now: number): string {
  const secs = Math.max(0, (now - new Date(iso).getTime()) / 1000);
  const h = Math.floor(secs / 3600);
  if (h < 1) return `${Math.max(1, Math.floor(secs / 60))}m`;
  if (h < 24) return `${h}h`;
  const d = Math.floor(h / 24);
  if (d < 7) return `${d}d`;
  return `${Math.floor(d / 7)}w`;
}

function compact(n: number): string {
  if (n < 1000) return String(n);
  if (n < 1_000_000) return `${(n / 1000).toFixed(1).replace(/\.0$/, "")}k`;
  return `${(n / 1_000_000).toFixed(1).replace(/\.0$/, "")}m`;
}

const MAX_BODY = 2000;

/** Apply `fn` to the matching comment anywhere in the two-level tree. */
function mapTree(
  list: Comment[],
  id: string,
  fn: (c: Comment) => Comment,
): Comment[] {
  return list.map((c) =>
    c.id === id
      ? fn(c)
      : { ...c, replies: c.replies.map((r) => (r.id === id ? fn(r) : r)) },
  );
}

/**
 * Discussion under a review (BUG-014) — the page had no comment surface at all.
 *
 * Renders server-fetched comments immediately, then owns them client-side so a
 * post, vote, or removal lands without a full page round trip. Signed-out
 * visitors read the whole thread and are sent to log in the moment they try to
 * take part, matching how voting on the review itself behaves.
 */
export function CommentThread({
  reviewId,
  initial,
  viewerId,
  viewerInitial = "",
  now,
}: {
  reviewId: string;
  initial: Comment[];
  /** null when signed out — also what decides "is this mine to delete?". */
  viewerId: string | null;
  /** The reader's initial for the docked composer's avatar. */
  viewerInitial?: string;
  /** When the server rendered the page, for every comment's age. */
  now: number;
}) {
  // Removed replies and empty tombstones never show (QA-039, comment-tree-model).
  const [comments, setComments] = useState<Comment[]>(() => visibleThread(initial));
  const [error, setError] = useState<string | null>(null);
  const [sort, setSort] = useState<CommentSort>(DEFAULT_COMMENT_SORT);
  // The pill the sort menu hangs from while it is open.
  const [sortAnchor, setSortAnchor] = useState<HTMLElement | null>(null);
  // QA-068: the order is decided when the page loads and when the reader picks
  // a sort — never by a vote. Deriving it from the counts on every render
  // re-sorted the thread on each vote, so the comment just voted on jumped.
  const [order, setOrder] = useState<string[]>(() =>
    sortComments(visibleThread(initial), DEFAULT_COMMENT_SORT).map((c) => c.id),
  );

  const sortPill = useRef<HTMLElement | null>(null);
  // Stable: SortMenu re-places itself whenever its onClose changes.
  const closeSort = useCallback(() => {
    sortPill.current?.focus();
    setSortAnchor(null);
  }, []);

  const total = comments.reduce((n, c) => n + 1 + c.replies.length, 0);
  const ordered = arrangeByOrder(comments, order);

  return (
    // `comments` is the target of the comment-count pill in the review's action
    // row. Figma "Screen/Product" → Body (7651:5838, read 2026-10-05): the count
    // in 16px Medium beside the sort chip (its current order, as the frame's
    // "Most helpful"), then each thread as a white ReplyCard, 16px apart.
    <section id="comments" className="mt-6 scroll-mt-24">
      <div className="flex items-center gap-3">
        <h2 className="flex-1 text-[16px] font-medium leading-none text-[var(--text-primary)]">
          {/* The frame's wording: a review's comments are its "replies". */}
          {total === 0 ? "Replies" : `${compact(total)} ${total === 1 ? "reply" : "replies"}`}
        </h2>
        {total > 1 ? (
          // Figma "Chip/Action" with the ArrowsDownUp glyph, as on /search.
          <button
            type="button"
            aria-haspopup="menu"
            aria-expanded={sortAnchor !== null}
            onClick={(e) => {
              sortPill.current = e.currentTarget;
              setSortAnchor(e.currentTarget);
            }}
            className="inline-flex h-8 shrink-0 cursor-pointer items-center gap-1 rounded-[var(--radius-md)] border border-[var(--text-primary)] px-[11px] text-[12px] leading-none text-[var(--text-primary)] hover:border-[var(--accent-primary)] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--accent-primary)]"
          >
            <ArrowsDownUp size={16} aria-hidden="true" />
            {sort.rating === "least_helpful" ? "Least helpful" : "Most helpful"}
            <span className="sr-only"> — change the order</span>
          </button>
        ) : null}
      </div>

      {sortAnchor ? (
        <SortCommentsMenu
          anchor={sortAnchor}
          value={sort}
          onApply={(next) => {
            setSort(next);
            setOrder(sortComments(comments, next).map((c) => c.id));
            closeSort();
          }}
          onClose={closeSort}
        />
      ) : null}

      {comments.length === 0 ? (
        <p className="mt-6 text-[12px] font-light leading-[18px] text-[var(--text-secondary)]">
          No replies yet. Ask the reviewer something, or add what you know.
        </p>
      ) : (
        <ul className="mt-4 flex flex-col gap-4">
          {ordered.map((c) => (
            <li key={c.id} className="min-w-0 rounded-[16px] bg-[var(--surface-card)] p-5">
              <CommentRow
                comment={c}
                reviewId={reviewId}
                viewerId={viewerId}
                now={now}
                onChange={(next) => setComments((prev) => mapTree(prev, next.id, () => next))}
                onRemoved={(id) => setComments((prev) => removeFromThread(prev, id))}
                onReplied={(reply) =>
                  setComments((prev) =>
                    mapTree(prev, c.id, (parent) => ({
                      ...parent,
                      replies: [...parent.replies, reply],
                    })),
                  )
                }
                onError={setError}
              />
            </li>
          ))}
        </ul>
      )}

      {error ? (
        <p role="alert" className="mt-3 text-[12px] text-[var(--accent-danger)]">
          {error}
        </p>
      ) : null}

      {/* Figma Composer (Screen/Product 7660:6153): the thread's last element,
          docked to the foot of the screen while the thread is on it. */}
      <CommentComposer
        reviewId={reviewId}
        viewerId={viewerId}
        docked
        viewerInitial={viewerInitial}
        onPosted={(c) => setComments((prev) => [...prev, c])}
        onError={setError}
      />
    </section>
  );
}

function CommentComposer({
  reviewId,
  viewerId,
  parentId,
  autoFocus = false,
  onPosted,
  onError,
  onCancel,
  initialBody = "",
  docked = false,
  viewerInitial = "",
}: {
  reviewId: string;
  viewerId: string | null;
  parentId?: string;
  /** The top-level composer, drawn as the sticky Composer bar. */
  docked?: boolean;
  viewerInitial?: string;
  autoFocus?: boolean;
  onPosted: (c: Comment) => void;
  onError: (message: string | null) => void;
  onCancel?: () => void;
  /** Pre-filled text: a reply to a reply opens addressed to that person. */
  initialBody?: string;
}) {
  const router = useRouter();
  const [body, setBody] = useState(initialBody);
  const [pending, setPending] = useState(false);

  if (!viewerId && docked) {
    return (
      <ComposerShell initial="" className="-mx-4 md:mx-0">
        <Link
          href={`/login?next=/reviews/${reviewId}`}
          className="flex h-11 min-w-0 flex-1 items-center rounded-full bg-[#f2f2f2] px-4 text-[14px] font-light text-[rgba(32,32,32,0.5)] no-underline"
        >
          Log in to join the discussion
        </Link>
      </ComposerShell>
    );
  }

  if (!viewerId) {
    return (
      <p className="mt-4 text-[12px] font-light leading-[18px] text-[var(--text-secondary)]">
        <Link
          href={`/login?next=/reviews/${reviewId}`}
          className="font-medium text-[var(--accent-primary)] underline underline-offset-2"
        >
          Log in
        </Link>{" "}
        to join the discussion.
      </p>
    );
  }

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    const trimmed = body.trim();
    if (!trimmed || pending) return;
    setPending(true);
    onError(null);
    try {
      const res = await fetch(`/api/bff/api/v1/reviews/${reviewId}/comments`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          body: trimmed,
          ...(parentId ? { parent_id: parentId } : {}),
        }),
      });
      if (!res.ok) {
        const problem = (await res.json().catch(() => ({}))) as { detail?: string };
        onError(problem.detail ?? "Couldn't post your comment.");
        return;
      }
      const posted = (await res.json()) as Comment;
      // The API omits `replies` on a freshly created comment; the tree needs it.
      onPosted({ ...posted, replies: posted.replies ?? [] });
      // A reply is a comment too — same endpoint, same marker. There is no
      // separate "reply" interaction kind.
      markInteraction(reviewId, "comment");
      setBody("");
      onCancel?.();
      // Keep the server's copy of the page in step for the next navigation.
      router.refresh();
    } catch {
      onError("Couldn't reach the server.");
    } finally {
      setPending(false);
    }
  }

  const over = body.length > MAX_BODY;

  if (docked) {
    return (
      <ComposerShell initial={viewerInitial} className="-mx-4 md:mx-0">
        <form onSubmit={submit} className="flex min-w-0 flex-1 items-end gap-2">
          <textarea
            value={body}
            onChange={(e) => setBody(e.target.value)}
            rows={1}
            placeholder="Join the discussion..."
            aria-label="Add a comment"
            aria-invalid={over || undefined}
            className={`own-focus field-sizing-content block max-h-40 min-h-11 min-w-0 flex-1 resize-none rounded-[22px] bg-[#f2f2f2] px-4 py-[11px] text-[14px] font-light leading-[22px] text-[var(--text-primary)] outline-none [overflow-wrap:anywhere] placeholder:text-[rgba(32,32,32,0.5)] focus-visible:ring-1 focus-visible:ring-inset ${over ? "ring-1 ring-inset ring-[var(--accent-danger)]" : "focus-visible:ring-[var(--accent-primary)]"}`}
          />
          {body.trim() ? (
            <button
              type="submit"
              aria-label="Comment"
              disabled={pending || over}
              className="grid size-11 shrink-0 cursor-pointer place-items-center rounded-full bg-[var(--accent-primary)] text-white hover:bg-[var(--accent-primary-strong)] disabled:cursor-not-allowed disabled:bg-[rgba(32,32,32,0.14)] disabled:text-[rgba(32,32,32,0.52)]"
            >
              <PaperPlaneRight size={20} aria-hidden="true" />
            </button>
          ) : null}
        </form>
        {over ? (
          <span role="status" className="sr-only">
            {body.length} of {MAX_BODY} characters: shorten it to post.
          </span>
        ) : null}
      </ComposerShell>
    );
  }

  return (
    <form onSubmit={submit} className={parentId ? "mt-3" : "mt-4"}>
      <textarea
        value={body}
        onChange={(e) => setBody(e.target.value)}
        autoFocus={autoFocus}
        rows={parentId ? 2 : 3}
        // "Join the discussion!" is the reference's own wording for the
        // collapsed composer (the "Group 410" export). Replies keep their own
        // prompt — the reference only draws the top-level field.
        placeholder={parentId ? "Write a reply…" : "Join the discussion!"}
        aria-label={parentId ? "Write a reply" : "Add a comment"}
        className={`w-full resize-y rounded-[var(--radius-sm)] bg-[var(--surface-card)] px-4 py-3 text-[14px] text-[var(--text-primary)] placeholder:text-[var(--text-muted)] ${PUBLIC_EDGE_STATES}`}
      />
      <div className="mt-2 flex items-center gap-3">
        <button
          type="submit"
          disabled={pending || !body.trim() || over}
          className="inline-flex items-center rounded-[var(--radius-pill)] bg-[var(--accent-primary)] px-5 py-2 text-[13px] font-semibold text-white hover:bg-[var(--accent-primary-strong)] disabled:bg-[rgba(32,32,32,0.14)] disabled:text-[rgba(32,32,32,0.52)]"
        >
          {pending ? "Posting…" : parentId ? "Reply" : "Comment"}
        </button>
        {onCancel ? (
          <button
            type="button"
            onClick={onCancel}
            className="text-[13px] text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
          >
            Cancel
          </button>
        ) : null}
        {over ? (
          <span className="text-[12px] text-[var(--accent-danger)]">
            {body.length}/{MAX_BODY}
          </span>
        ) : null}
      </div>
    </form>
  );
}

function CommentRow({
  comment,
  reviewId,
  viewerId,
  now,
  isReply = false,
  rootId,
  onChange,
  onRemoved,
  onReplied,
  onError,
}: {
  comment: Comment;
  reviewId: string;
  viewerId: string | null;
  now: number;
  isReply?: boolean;
  /** The thread's top comment: where a reply to a reply is posted (two levels). */
  rootId?: string;
  onChange: (next: Comment) => void;
  onRemoved: (id: string) => void;
  onReplied?: (reply: Comment) => void;
  onError: (message: string | null) => void;
}) {
  const router = useRouter();
  const [replying, setReplying] = useState(false);
  const [pending, setPending] = useState(false);
  // QA-039: deleting takes two deliberate taps — Delete, then "Yes, delete".
  const [confirmingDelete, setConfirmingDelete] = useState(false);
  // §8: a heavily downvoted comment starts collapsed; the reader may open it.
  const [expanded, setExpanded] = useState(false);
  const collapsed = Boolean(comment.is_collapsed) && !expanded && !comment.is_removed;

  const name =
    comment.author?.display_name || comment.author?.username || "someone";
  const isMine = viewerId !== null && comment.author?.id === viewerId;

  async function vote(dir: "up" | "down") {
    if (!viewerId) {
      router.push(`/login?next=/reviews/${reviewId}`);
      return;
    }
    if (pending) return;
    setPending(true);
    onError(null);
    const remove = comment.my_vote === dir;
    try {
      const res = await fetch(`/api/bff/api/v1/comments/${comment.id}/vote`, {
        method: remove ? "DELETE" : "POST",
        headers: remove ? undefined : { "content-type": "application/json" },
        body: remove ? undefined : JSON.stringify({ vote: dir }),
      });
      if (!res.ok) {
        const problem = (await res.json().catch(() => ({}))) as { detail?: string };
        onError(problem.detail ?? "Couldn't record your vote.");
        return;
      }
      const updated = (await res.json()) as Comment;
      onChange({
        ...comment,
        helpful_votes: updated.helpful_votes,
        unhelpful_votes: updated.unhelpful_votes,
        my_vote: remove ? null : dir,
      });
    } catch {
      onError("Couldn't reach the server.");
    } finally {
      setPending(false);
    }
  }

  async function remove() {
    if (pending) return;
    setPending(true);
    onError(null);
    try {
      const res = await fetch(`/api/bff/api/v1/comments/${comment.id}`, {
        method: "DELETE",
      });
      if (!res.ok) {
        const problem = (await res.json().catch(() => ({}))) as { detail?: string };
        onError(problem.detail ?? "Couldn't remove your comment.");
        return;
      }
      // QA-039: gone from the thread at once — only a top comment that still
      // has live replies stays, as a tombstone, so they keep their context.
      onRemoved(comment.id);
      router.refresh();
    } catch {
      onError("Couldn't reach the server.");
    } finally {
      setPending(false);
    }
  }

  const level = comment.is_removed ? null : comment.author?.trust_level_name;
  const control =
    "inline-flex cursor-pointer items-center gap-1 text-[12px] font-light leading-none disabled:opacity-60 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--accent-primary)]";

  // Figma "Screen/Product" ReplyCard (7651:5951, read 2026-10-05): the shared
  // Author header (36px avatar, name and age, stage · Honesty Score, the
  // DotsThree at the right); 16px down, the body in 14px Light on a 1.5 line;
  // 16px down, the same row on EVERY comment and reply: VoteBar (20px arrows,
  // the count with the upvote), Reply, Share, 24px apart. A reply from a
  // claimed seller sits in the grey SellerReply panel; other replies sit 36px
  // in under a curved 30% ink connector.
  //
  // QA-020: the row is identical for everyone because a comment's own extra
  // action — Delete, for its author — lives in the header's DotsThree, as the
  // frame places it. QA-069: on anyone else's comment the same DotsThree holds
  // Report, Follow and Save.
  // Share links to the comment itself, `#comment-<id>` on the review's page.
  return (
    <div id={`comment-${comment.id}`} className="min-w-0 scroll-mt-24 text-[var(--text-primary)]">
      {comment.is_removed ? (
        <div className="flex items-center gap-2.5">
          <span aria-hidden="true" className="grid h-9 w-9 shrink-0 place-items-center rounded-full bg-[var(--base-gray-200)] text-[13px] font-semibold text-white">
            –
          </span>
          <span className="flex flex-col gap-1 text-[12px] leading-[normal]">
            <span className="font-medium text-[var(--text-muted)]">removed</span>
            <span className="font-extralight text-[var(--text-primary)]">{ageLabel(comment.created_at, now)}</span>
          </span>
        </div>
      ) : (
        <AuthorHeader
          name={comment.author?.username ?? name}
          href={comment.author?.id ? `/u/${comment.author.id}` : null}
          avatarUrl={usablePhoto(comment.author?.avatar_url ?? null)}
          age={ageLabel(comment.created_at, now)}
          levelName={level}
          stage={comment.author?.trust_stage}
          score={comment.author?.reputation_score ?? null}
          seller={Boolean(comment.author?.is_claimed_seller)}
          badges={
            <>
              {comment.author?.is_new_account ? (
                <span className="shrink-0 rounded-[var(--radius-pill)] bg-[var(--line-hairline-10)] px-2 py-0.5 text-[10px] font-medium text-[var(--text-secondary)]">
                  New account
                </span>
              ) : null}
            </>
          }
          trailing={
            <>
              {isMine && !comment.is_removed ? (
                <CommentMenu
                  disabled={pending}
                  onDelete={() => setConfirmingDelete(true)}
                />
              ) : null}
              {!isMine && !comment.is_removed && comment.author ? (
                <OthersCommentMenu comment={comment} reviewId={reviewId} viewerId={viewerId} onChange={onChange} onError={onError} />
              ) : null}
            </>
          }
        />
      )}

      {collapsed ? (
        <p className="mt-3 text-[12px] font-light leading-[18px] text-[var(--text-muted)]">
          Hidden after many downvotes.{" "}
          <button
            type="button"
            onClick={() => setExpanded(true)}
            className="cursor-pointer font-medium text-[var(--accent-primary)] hover:underline"
          >
            Show
          </button>
        </p>
      ) : (
        <p
          className={`mt-4 whitespace-pre-line text-[14px] font-light leading-[1.5] [overflow-wrap:anywhere] ${
            comment.is_removed ? "italic text-[var(--text-muted)]" : ""
          }`}
        >
          {comment.body}
        </p>
      )}

      {!comment.is_removed && !collapsed ? (
        <div className="mt-4 flex flex-wrap items-center gap-x-6 gap-y-2">
          <div className="flex items-center gap-3">
            <button
              type="button"
              onClick={() => vote("up")}
              disabled={pending}
              aria-pressed={comment.my_vote === "up"}
              aria-label={`Helpful, ${compact(comment.helpful_votes)}`}
              className={control}
            >
              <ArrowFatUp
                size={20}
                weight="fill"
                aria-hidden="true"
                className={comment.my_vote === "up" ? "text-[var(--accent-success)]" : "text-[var(--base-gray-400)]"}
              />
              <span aria-hidden="true">{compact(comment.helpful_votes)}</span>
            </button>
            <button
              type="button"
              onClick={() => vote("down")}
              disabled={pending}
              aria-pressed={comment.my_vote === "down"}
              aria-label={`Not helpful, ${compact(comment.unhelpful_votes)}`}
              className={control}
            >
              <ArrowFatDown
                size={20}
                weight="fill"
                aria-hidden="true"
                className={comment.my_vote === "down" ? "text-[var(--accent-danger)]" : "text-[var(--base-gray-400)]"}
              />
              <span aria-hidden="true">{compact(comment.unhelpful_votes)}</span>
            </button>
          </div>

          {/* QA-029: every comment can be answered. Threads are two levels
              (the API refuses a third), so a reply to a reply joins the same
              thread, opened with the person it answers. */}
          {onReplied ? (
            <button
              type="button"
              onClick={() => setReplying((v) => !v)}
              aria-expanded={replying}
              className={`${control} hover:text-[var(--accent-primary)]`}
            >
              <ArrowBendDownRight size={20} aria-hidden="true" className="text-[var(--base-gray-400)]" />
              Reply
            </button>
          ) : null}

          <ShareSheet
            path={`/reviews/${reviewId}#comment-${comment.id}`}
            title={`A comment by ${name}`}
            excerpt={comment.body}
            variant="inline"
          />
        </div>
      ) : null}

      {isMine && confirmingDelete && !comment.is_removed ? (
        <div role="group" aria-label="Confirm deleting your comment"
             className="mt-3 flex flex-wrap items-center gap-3 text-[12px]">
          <span className="text-[var(--text-secondary)]">Delete this comment?</span>
          <button
            type="button"
            onClick={() => {
              setConfirmingDelete(false);
              void remove();
            }}
            disabled={pending}
            className={`${control} font-medium text-[var(--accent-danger)]`}
          >
            Yes, delete
          </button>
          <button
            type="button"
            onClick={() => setConfirmingDelete(false)}
            className={`${control} text-[var(--text-secondary)]`}
          >
            Cancel
          </button>
        </div>
      ) : null}

      {replying && onReplied ? (
        <CommentComposer
          reviewId={reviewId}
          viewerId={viewerId}
          parentId={isReply && rootId ? rootId : comment.id}
          initialBody={isReply ? replyOpening(comment.author?.username) : ""}
          autoFocus
          onPosted={(reply) => {
            onReplied(reply);
            setReplying(false);
          }}
          onError={onError}
          onCancel={() => setReplying(false)}
        />
      ) : null}

      {comment.replies.length > 0 ? (
        <ul className="mt-5 flex flex-col gap-5">
          {comment.replies.map((r) => (
            <li
              key={r.id}
              className={
                // Figma "SellerReply" (7659:6109): "Seller response panel: grey
                // inset" — #f9f9f9 with a #e9e9e9 line at radius 12, 16px in.
                r.author?.is_claimed_seller && !r.is_removed
                  ? "rounded-[12px] border border-[#e9e9e9] bg-[#f9f9f9] p-4"
                  : "relative pl-9"
              }
            >
              {r.author?.is_claimed_seller && !r.is_removed ? null : (
                <span
                  aria-hidden="true"
                  className="absolute left-[18px] top-[-12px] h-[30px] w-3 rounded-bl-[12px] border-b border-l border-[var(--line-hairline-30)]"
                />
              )}
              <CommentRow
                comment={r}
                reviewId={reviewId}
                viewerId={viewerId}
                now={now}
                isReply
                rootId={comment.id}
                onChange={onChange}
                onRemoved={onRemoved}
                onReplied={onReplied}
                onError={onError}
              />
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}

/**
 * QA-069: the DotsThree on another member's comment — Report (the moderation
 * pipeline reviews go through, via the same dialog), Follow (hear about
 * replies to it) and Save (a private list on your profile). Follow and Save
 * show only the viewer's own state; the API never says who else did either.
 * Signed out, each item goes to log in first.
 */
function OthersCommentMenu({
  comment,
  reviewId,
  viewerId,
  onChange,
  onError,
}: {
  comment: Comment;
  reviewId: string;
  viewerId: string | null;
  onChange: (next: Comment) => void;
  onError: (message: string | null) => void;
}) {
  const router = useRouter();
  const [status, setStatus] = useState("");
  const followed = Boolean(comment.followed_by_me);
  const saved = Boolean(comment.saved_by_me);

  function signIn() {
    router.push(`/login?next=${encodeURIComponent(`/reviews/${reviewId}#comment-${comment.id}`)}`);
  }

  async function mark(kind: "follow" | "save", on: boolean) {
    if (!viewerId) return signIn();
    onError(null);
    const field = kind === "follow" ? "followed_by_me" : "saved_by_me";
    onChange({ ...comment, [field]: on });
    try {
      const res = await fetch(`/api/bff/api/v1/comments/${encodeURIComponent(comment.id)}/${kind}`, {
        method: on ? "PUT" : "DELETE",
      });
      if (!res.ok) throw new Error(String(res.status));
      setStatus(
        kind === "follow"
          ? on ? "Following this comment. You'll hear about replies." : "Stopped following this comment."
          : on ? "Saved. Find it under Saved comments on your profile." : "Removed from your saved comments.",
      );
    } catch {
      onChange({ ...comment, [field]: !on });
      onError("That didn't save. Try again.");
    }
  }

  return (
    <div className="-my-1 shrink-0 self-start">
      <OverflowMenu
        label="More actions for this comment"
        items={[
          {
            key: "report",
            label: "Report",
            icon: <Flag size={16} aria-hidden="true" />,
            onSelect: () =>
              viewerId ? document.getElementById(`report-trigger-comment-${comment.id}`)?.click() : signIn(),
          },
          {
            key: "follow",
            label: followed ? "Unfollow comment" : "Follow comment",
            icon: followed ? <BellSimpleSlash size={16} aria-hidden="true" /> : <BellSimple size={16} aria-hidden="true" />,
            onSelect: () => void mark("follow", !followed),
          },
          {
            key: "save",
            label: saved ? "Unsave comment" : "Save comment",
            icon: <BookmarkSimple size={16} weight={saved ? "fill" : "regular"} aria-hidden="true" />,
            onSelect: () => void mark("save", !saved),
          },
        ]}
      />
      {viewerId ? <ReportDialog reviewId={reviewId} commentId={comment.id} canReport hideTrigger /> : null}
      <span role="status" aria-live="polite" className="sr-only">
        {status}
      </span>
    </div>
  );
}

/**
 * The comment header's DotsThree (Figma 7140:3330): a small menu holding the
 * author's own action, Delete. Choosing it only ARMS the delete — the
 * "Yes, delete" step under the comment still has to be taken (QA-039).
 * Escape or a click elsewhere closes it; focus returns to the trigger.
 */
function CommentMenu({ onDelete, disabled }: { onDelete: () => void; disabled: boolean }) {
  const [open, setOpen] = useState(false);
  const wrap = useRef<HTMLDivElement | null>(null);
  const trigger = useRef<HTMLButtonElement | null>(null);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setOpen(false);
        trigger.current?.focus();
      }
    };
    const onDown = (e: MouseEvent) => {
      if (!wrap.current?.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("keydown", onKey);
    document.addEventListener("mousedown", onDown);
    wrap.current?.querySelector<HTMLElement>('[role="menuitem"]')?.focus();
    return () => {
      document.removeEventListener("keydown", onKey);
      document.removeEventListener("mousedown", onDown);
    };
  }, [open]);

  return (
    <div ref={wrap} className="relative -my-1 shrink-0 self-start">
      <button
        ref={trigger}
        type="button"
        aria-label="More actions for this comment"
        aria-haspopup="menu"
        aria-expanded={open}
        disabled={disabled}
        onClick={() => setOpen((v) => !v)}
        className="grid h-8 w-8 cursor-pointer place-items-center rounded-full text-[var(--text-primary)] hover:bg-[var(--line-hairline-10)] disabled:opacity-60 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--accent-primary)]"
      >
        <DotsThree size={24} weight="bold" aria-hidden="true" />
      </button>
      {open ? (
        <div
          role="menu"
          aria-label="Comment actions"
          className="absolute right-0 top-full z-20 mt-1 min-w-[160px] rounded-[12px] bg-[var(--surface-app)] py-1 shadow-[var(--shadow-sheet)]"
        >
          <button
            type="button"
            role="menuitem"
            onClick={() => {
              setOpen(false);
              onDelete();
            }}
            className="flex w-full cursor-pointer items-center gap-2 px-4 py-2.5 text-left text-[13px] text-[var(--accent-danger)] hover:bg-[var(--line-hairline-10)] focus-visible:bg-[var(--line-hairline-10)] focus-visible:outline-none"
          >
            <Trash size={18} aria-hidden="true" />
            Delete
          </button>
        </div>
      ) : null}
    </div>
  );
}

export default CommentThread;
