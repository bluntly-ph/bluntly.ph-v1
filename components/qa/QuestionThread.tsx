"use client";

import Image from "next/image";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import {
  ArrowBendDownRight,
  ArrowFatDown,
  ArrowFatUp,
  ArrowsDownUp,
  ChatCircle,
  Check,
  ClockCounterClockwise,
  DotsThree,
  Equals,
  Flag,
  LinkSimple,
  Medal,
  ShareNetwork,
  Trash,
  X,
} from "@phosphor-icons/react/dist/ssr";

import { BestAnswerButton } from "@/components/qa/BestAnswerButton";
import { ShareSheet, type ShareSheetHandle } from "@/components/share/ShareSheet";
import { answerByline } from "@/components/qa/question-subject-model";
import {
  VERDICT_LABEL,
  experienceLines,
  fitTone,
  pointLines,
  replyTree,
  sortAnswers,
  THREAD_MAX_DEPTH,
  descendantCount,
  focusThread,
  type ReplyNode,
  type Verdict,
} from "@/components/qa/question-thread-model";
import { splitFit } from "@/components/qa/answer-flow-model";
import { AuthorHeader } from "@/components/review/AuthorHeader";
import { ReportDialog } from "@/components/review/ReportDialog";
import { StarRow } from "@/components/sellers/SellerIdentity";
import type { Answer, QAAuthor, Reply } from "@/lib/qa";
import { shortAge } from "@/lib/relative-time";
import { ComposerShell } from "@/components/ui/ComposerShell";

/**
 * The thread on the question page, built to Figma Question Detail v6B
 * (7731:15601): the Best Answer card (7731:15656), "N more answers" with its
 * "Most helpful" chip (7731:15715), each AnswerRow (7731:15742) with its
 * VoteBar / Reply (n) / Share ActionBar and the reply Thread with rails at
 * three levels, and the question's Reactions (7731:15654).
 *
 * Every number is the API's, from the vote and reply rows (migration 0073); a
 * vote or reply goes to its endpoint and the page re-reads. The VoteBar follows
 * its component note: neutral arrows grey, an up-vote green, a down-vote red,
 * so a voter can see their own vote registered.
 */

const VERDICT_ICON: Record<Verdict, { Icon: typeof Check; cls: string }> = {
  yes: { Icon: Check, cls: "text-[var(--accent-success)]" },
  on_sale: { Icon: Equals, cls: "text-[var(--text-primary)]" },
  other_variant: { Icon: ArrowsDownUp, cls: "text-[var(--text-primary)]" },
  no: { Icon: X, cls: "text-[var(--accent-danger)]" },
};
const SECTION = "text-[12px] leading-normal text-[var(--chart-honesty-fund)]";
const LINE = "flex items-center gap-[6px] text-[12px] font-light leading-normal text-[var(--text-primary)]";

type Viewer = { id: string | null; loginHref: string };

async function put(url: string, body: unknown): Promise<Response> {
  return fetch(`/api/bff/api/v1${url}`, {
    method: "PUT",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
  });
}

function problem(res: Response, fallback: string): Promise<string> {
  return res
    .json()
    .then((p: { detail?: unknown }) => (typeof p.detail === "string" ? p.detail : fallback))
    .catch(() => fallback);
}

/* ------------------------------------------------------------------ author */

type AuthorFields = Pick<QAAuthor, "trust_stage"> & {
  trust_level_name?: string | null;
  reputation_score?: string | number | null;
  avatar_url?: string | null;
};

function Author({
  author,
  name,
  when,
  seller = false,
  edited = false,
  menu = null,
}: {
  author: AuthorFields | null;
  name: string;
  when: string;
  seller?: boolean;
  /** The store edited its answer (Figma EditAnswer: buyers see "Edited"). */
  edited?: boolean;
  /** The row's ⋯ (Figma Author "More", 24px DotsThree), at the right. */
  menu?: React.ReactNode;
}) {
  // The shared Figma "Author" (7659:5991): one header for reviews, answers,
  // replies and seller responses (AuthorHeader).
  return (
    <AuthorHeader
      className="w-full"
      name={name}
      avatarUrl={author?.avatar_url ?? null}
      age={<span suppressHydrationWarning>{shortAge(when)}</span>}
      trailing={menu}
      levelName={author?.trust_level_name}
      stage={author?.trust_stage}
      score={author?.reputation_score}
      seller={seller}
      badges={edited ? <span className="shrink-0 font-extralight text-[var(--text-secondary)]">· Edited</span> : null}
    />
  );
}

type MenuItem = { label: string; Icon: typeof Flag; onSelect: () => void; danger?: boolean };

/**
 * The 24px ⋯ at the right of an answer's or a reply's Author row (Figma
 * Screen/Question: every Author carries "More"). No frame draws its menu, so it
 * holds what the item already offers: Copy link, Report (an answer someone else
 * wrote), Remove (a reply, for its author or staff — it was a text button in
 * the action row, which the frame does not draw).
 */
function ItemMenu({ path, items }: { path: string; items: MenuItem[] }) {
  const [open, setOpen] = useState(false);
  const [copied, setCopied] = useState(false);
  const root = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      if (!root.current?.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);
  const all: MenuItem[] = [
    {
      label: copied ? "Copied" : "Copy link",
      Icon: LinkSimple,
      onSelect: async () => {
        try {
          await navigator.clipboard.writeText(new URL(path, window.location.origin).toString());
          setCopied(true);
          setTimeout(() => setCopied(false), 2000);
        } catch {
          /* Clipboard denied: the label simply doesn't change. */
        }
      },
    },
    ...items,
  ];
  return (
    <div ref={root} className="relative self-start">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-label="More options"
        aria-expanded={open}
        aria-haspopup="menu"
        className="grid size-8 cursor-pointer place-items-center rounded-full text-[var(--text-primary)] hover:bg-[var(--line-hairline-10)]"
      >
        <DotsThree size={24} weight="bold" aria-hidden />
      </button>
      {open ? (
        <div role="menu" className="absolute right-0 top-full z-20 mt-1 w-48 overflow-hidden rounded-[var(--radius-sm)] bg-[var(--surface-card)] py-1 shadow-[var(--shadow-card)]">
          {all.map(({ label, Icon, onSelect, danger }) => (
            <button
              key={label}
              type="button"
              role="menuitem"
              onClick={() => {
                onSelect();
                setOpen(false);
              }}
              className={`flex w-full cursor-pointer items-center gap-2 px-4 py-2.5 text-left text-[14px] hover:bg-[var(--surface-app)] ${danger ? "text-[var(--accent-danger)]" : "text-[var(--text-primary)]"}`}
            >
              <Icon size={18} aria-hidden />
              {label}
            </button>
          ))}
        </div>
      ) : null}
      <span aria-live="polite" className="sr-only">
        {copied ? "Link copied" : ""}
      </span>
    </div>
  );
}

/* --------------------------------------------------------------- vote bar */

function VoteBar({
  url,
  up,
  down,
  mine,
  own,
  viewer,
  label,
}: {
  url: string;
  up: number;
  down: number;
  mine: "up" | "down" | null | undefined;
  own: boolean;
  viewer: Viewer;
  label: string;
}) {
  const router = useRouter();
  const [state, setState] = useState({ up, down, mine: mine ?? null });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function cast(direction: "up" | "down") {
    if (busy) return;
    if (!viewer.id) {
      router.push(viewer.loginHref);
      return;
    }
    setBusy(true);
    setError(null);
    const next = state.mine === direction ? null : direction;
    try {
      const res = await put(url, { vote: next });
      if (!res.ok) {
        setError(await problem(res, "Couldn't save your vote."));
        return;
      }
      const t = (await res.json()) as { up: number; down: number; my_vote: "up" | "down" | null };
      setState({ up: t.up, down: t.down, mine: t.my_vote });
    } catch {
      setError("Couldn't reach the server.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <span className="flex items-center gap-3" role="group" aria-label={`Votes on this ${label}`}>
      <button
        type="button"
        onClick={() => cast("up")}
        disabled={busy || own}
        aria-pressed={state.mine === "up"}
        aria-label={`Helpful (${state.up})`}
        title={own ? `You can't vote on your own ${label}` : undefined}
        className="flex cursor-pointer items-center gap-1 disabled:cursor-default"
      >
        <ArrowFatUp size={20} weight="fill" aria-hidden className={state.mine === "up" ? "text-[var(--accent-success)]" : "text-[var(--base-gray-400)]"} />
        <span className="text-[12px] font-light leading-none text-[var(--text-primary)]">{state.up}</span>
      </button>
      <button
        type="button"
        onClick={() => cast("down")}
        disabled={busy || own}
        aria-pressed={state.mine === "down"}
        aria-label={`Not helpful (${state.down})`}
        className="cursor-pointer disabled:cursor-default"
      >
        <ArrowFatDown size={20} weight="fill" aria-hidden className={state.mine === "down" ? "text-[var(--accent-danger)]" : "text-[var(--base-gray-400)]"} />
      </button>
      {error ? (
        <span role="alert" className="text-[11px] text-[var(--accent-danger)]">
          {error}
        </span>
      ) : null}
    </span>
  );
}

/** The question's Reactions (7731:15654): up-votes (a toggle) and the discussion size. */
export function QuestionReactions({
  questionId,
  upvotes,
  mine,
  own,
  comments,
  viewerId,
  loginHref,
}: {
  questionId: string;
  upvotes: number;
  mine: boolean;
  own: boolean;
  comments: number;
  viewerId: string | null;
  loginHref: string;
}) {
  const router = useRouter();
  const [state, setState] = useState({ upvotes, mine });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function toggle() {
    if (busy) return;
    if (!viewerId) {
      router.push(loginHref);
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const res = await put(`/questions/${questionId}/vote`, { up: !state.mine });
      if (!res.ok) {
        setError(await problem(res, "Couldn't save your vote."));
        return;
      }
      const v = (await res.json()) as { upvotes: number; my_upvote: boolean };
      setState({ upvotes: v.upvotes, mine: v.my_upvote });
    } catch {
      setError("Couldn't reach the server.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex items-center gap-4">
      <button
        type="button"
        onClick={toggle}
        disabled={busy || own}
        aria-pressed={state.mine}
        aria-label={`Up-vote this question (${state.upvotes})`}
        title={own ? "You can't vote on your own question" : undefined}
        className="flex cursor-pointer items-center gap-1 disabled:cursor-default"
        data-testid="question-upvote"
      >
        <ArrowFatUp size={16} weight="fill" aria-hidden className={state.mine ? "text-[var(--accent-success)]" : "text-[var(--base-gray-400)]"} />
        <span className="text-[12px] font-light leading-normal">{state.upvotes}</span>
      </button>
      <span className="flex items-center gap-1" aria-label={`${comments} answers and replies`}>
        <ChatCircle size={16} aria-hidden />
        <span className="text-[12px] font-light leading-normal">{comments}</span>
      </span>
      {error ? (
        <span role="alert" className="text-[11px] text-[var(--accent-danger)]">
          {error}
        </span>
      ) : null}
    </div>
  );
}

/* --------------------------------------------------------------- replies */

function ReplyBox({ onSubmit, onCancel, autoFocus = true }: { onSubmit: (body: string) => Promise<string | null>; onCancel: () => void; autoFocus?: boolean }) {
  const [body, setBody] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  return (
    <form
      className="flex w-full flex-col gap-2"
      onSubmit={async (e) => {
        e.preventDefault();
        if (!body.trim() || busy) return;
        setBusy(true);
        setError(await onSubmit(body.trim()));
        setBusy(false);
      }}
    >
      <textarea
        value={body}
        onChange={(e) => setBody(e.target.value.slice(0, 1000))}
        autoFocus={autoFocus}
        rows={2}
        aria-label="Your reply"
        placeholder="Join the discussion…"
        className="w-full resize-none rounded-[16px] bg-[var(--surface-app)] px-4 py-3 text-[14px] leading-[21px] outline-none placeholder:text-[rgba(32,32,32,0.5)] focus-visible:ring-2 focus-visible:ring-[var(--accent-primary)]"
      />
      {error ? (
        <p role="alert" className="text-[12px] text-[var(--accent-danger)]">
          {error}
        </p>
      ) : null}
      <span className="flex justify-end gap-3 text-[12px]">
        <button type="button" onClick={onCancel} className="cursor-pointer text-[var(--text-secondary)]">
          Cancel
        </button>
        <button type="submit" disabled={!body.trim() || busy} data-testid="reply-submit" className="cursor-pointer font-medium text-[var(--accent-primary)] disabled:opacity-50">
          {busy ? "Posting…" : "Reply"}
        </button>
      </span>
    </form>
  );
}

function Rail({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex w-full gap-3">
      <span aria-hidden className="relative w-3 shrink-0">
        <span className="absolute bottom-0 left-[5px] top-0 w-[1.5px] bg-[#d9d9d9]" />
      </span>
      <div className="flex min-w-0 flex-1 flex-col gap-4">{children}</div>
    </div>
  );
}

/** "Continue this thread · N more replies" (Figma Screen/Question), into the thread view. */
function ContinueThread({ questionId, replyId, hidden }: { questionId: string; replyId: string; hidden: number }) {
  return (
    <Link
      href={`/questions/${questionId}?thread=${replyId}#thread`}
      className="flex flex-wrap items-baseline gap-x-1.5 text-[12px] leading-normal text-[var(--text-primary)] hover:text-[var(--accent-primary)]"
    >
      <span className="font-medium">Continue this thread</span>{" "}
      <span className="font-light">
        · {hidden} more {hidden === 1 ? "reply" : "replies"}
      </span>
    </Link>
  );
}

function ReplyItem({
  node,
  questionId,
  answerId,
  viewer,
  canRemove,
  depth = 1,
  replySignal = 0,
}: {
  node: ReplyNode<Reply>;
  questionId: string;
  answerId: string;
  viewer: Viewer;
  canRemove: boolean;
  /** Rails above this reply: 1 under an answer; 0 for the thread view's root. */
  depth?: number;
  /** Bumped by the thread view's composer: open this reply's reply box. */
  replySignal?: number;
}) {
  const router = useRouter();
  const [replying, setReplying] = useState(false);
  // A new signal opens the box, adjusted while rendering rather than in an
  // effect (react.dev, "Adjusting some state when a prop changes").
  const [seenSignal, setSeenSignal] = useState(replySignal);
  if (replySignal !== seenSignal) {
    setSeenSignal(replySignal);
    if (replySignal > 0) setReplying(true);
  }
  const own = Boolean(viewer.id && node.author?.id === viewer.id);
  const name = node.author ? (node.author.display_name ?? node.author.username ?? "Member") : "Former member";
  // Figma Screen/Question/Thread: three levels under a root, then "Continue
  // this thread · N more replies" into the thread view focused on this reply.
  const capped = depth >= THREAD_MAX_DEPTH && node.children.length > 0;
  const hidden = capped ? descendantCount(node) : 0;
  return (
    <div className="flex min-w-0 flex-col gap-4" id={`reply-${node.id}`}>
      <div className="flex min-w-0 flex-col gap-2">
        <Author
          author={node.author ?? null}
          name={name}
          when={node.created_at}
          menu={
            <ItemMenu
              path={`/questions/${questionId}#reply-${node.id}`}
              items={
                own || canRemove
                  ? [
                      {
                        label: "Remove",
                        Icon: Trash,
                        danger: true,
                        onSelect: async () => {
                          const res = await fetch(`/api/bff/api/v1/questions/${questionId}/replies/${node.id}`, { method: "DELETE" });
                          if (res.ok) router.refresh();
                        },
                      },
                    ]
                  : []
              }
            />
          }
        />
        <p className="whitespace-pre-line break-words text-[14px] leading-[1.5] text-[var(--text-primary)] [overflow-wrap:anywhere]">{node.body}</p>
        <div className="flex flex-wrap items-center gap-x-6 gap-y-2">
          <VoteBar
            url={`/questions/${questionId}/replies/${node.id}/vote`}
            up={node.up ?? 0}
            down={node.down ?? 0}
            mine={node.my_vote}
            own={own}
            viewer={viewer}
            label="reply"
          />
          <button
            type="button"
            onClick={() => (viewer.id ? setReplying((v) => !v) : router.push(viewer.loginHref))}
            className="flex cursor-pointer items-center gap-1 text-[12px] font-light leading-none"
          >
            <ArrowBendDownRight size={20} aria-hidden /> Reply
          </button>
        </div>
        {replying ? (
          <ReplyBox
            onCancel={() => setReplying(false)}
            onSubmit={async (body) => {
              const res = await fetch(`/api/bff/api/v1/questions/${questionId}/answers/${answerId}/replies`, {
                method: "POST",
                headers: { "content-type": "application/json" },
                body: JSON.stringify({ body, parent_id: node.id }),
              });
              if (!res.ok) return problem(res, "Couldn't post your reply.");
              setReplying(false);
              router.refresh();
              return null;
            }}
          />
        ) : null}
      </div>
      {capped ? (
        <ContinueThread questionId={questionId} replyId={node.id} hidden={hidden} />
      ) : node.children.length > 0 ? (
        <Rail>
          {/* The server files a reply past the third level beside its parent
              (qa_engagement MAX_DEPTH), so the third level is where a long
              thread piles up. Figma Screen/Question (7731:15714) shows its
              first reply there, then "Continue this thread · N more replies". */}
          {(depth + 1 >= THREAD_MAX_DEPTH ? node.children.slice(0, 1) : node.children).map((c) => (
            <ReplyItem key={c.id} node={c} questionId={questionId} answerId={answerId} viewer={viewer} canRemove={canRemove} depth={depth + 1} />
          ))}
          {depth + 1 >= THREAD_MAX_DEPTH && node.children.length > 1 ? (
            <ContinueThread
              questionId={questionId}
              replyId={node.id}
              hidden={node.children.slice(1).reduce((n, c) => n + 1 + descendantCount(c), 0)}
            />
          ) : null}
        </Rail>
      ) : null}
    </div>
  );
}

/* ---------------------------------------------------------------- answers */

function Details({ a }: { a: Answer }) {
  const p = a.parts;
  if (!p) return null;
  const exp = experienceLines(p.experience);
  const pros = pointLines(p.good);
  const cons = pointLines(p.bad);
  const fit = splitFit(p.right_for_you);
  const tone = fitTone(fit.choice);
  const FitIcon = tone === "yes" ? Check : tone === "no" ? X : Equals;
  const why = p.verdict ? p.verdict_reason?.trim() : null;
  return (
    <div className="flex flex-col gap-[14px]">
      {/* The verdict's "Why?" (Answer Step 4.1). Screen/Question's Details draw
          no slot for it, so it leads the Details as its own short section,
          under Figma's own field label. */}
      {why ? (
        <div className="flex flex-col gap-[6px]">
          <p className={SECTION}>Why?</p>
          <p className="text-[14px] leading-[20px] [overflow-wrap:anywhere]">{why}</p>
        </div>
      ) : null}
      {exp.length ? (
        <div className="flex flex-col gap-[6px]">
          <p className={SECTION}>Experience</p>
          {exp.map((line, i) => (
            <p key={line} className={LINE}>
              {i === 0 ? <ClockCounterClockwise size={16} aria-hidden /> : <Check size={16} aria-hidden />}
              {line}
            </p>
          ))}
        </div>
      ) : null}
      {pros.length || cons.length ? (
        <div className="flex flex-col gap-[6px]">
          <p className={SECTION}>Pros &amp; Cons</p>
          <div className="flex gap-4">
            <ul className="flex min-w-0 flex-1 flex-col gap-[6px]">
              {pros.map((x) => (
                <li key={x} className={LINE}>
                  <Check size={16} aria-hidden className="shrink-0 text-[var(--accent-success)]" />
                  {x}
                </li>
              ))}
            </ul>
            <ul className="flex min-w-0 flex-1 flex-col gap-[6px]">
              {cons.map((x) => (
                <li key={x} className={LINE}>
                  <X size={16} aria-hidden className="shrink-0 text-[var(--accent-danger)]" />
                  {x}
                </li>
              ))}
            </ul>
          </div>
        </div>
      ) : null}
      {fit.choice ? (
        <div className="flex flex-col gap-[6px]">
          <p className={SECTION}>Is it for them?</p>
          <p className={`${LINE} font-medium`}>
            <FitIcon size={16} aria-hidden />
            {fit.choice}
          </p>
          {/* Screen/Question Details: the "It depends" reason under the fit. */}
          {/* 12px Light on its natural line (7731:15700). */}
          {fit.detail ? <p className="text-[12px] font-light leading-normal [overflow-wrap:anywhere]">{fit.detail}</p> : null}
        </div>
      ) : null}
      {p.photo_urls?.length ? (
        <div className="flex gap-2">
          {p.photo_urls.map((url) => (
            <a key={url} href={url} target="_blank" rel="noreferrer" className="block size-16 overflow-hidden rounded-[12px] bg-[#e1e1e1]">
              <Image src={url} alt="The answerer's photo" width={64} height={64} unoptimized className="size-16 object-cover" />
            </a>
          ))}
        </div>
      ) : null}
    </div>
  );
}

function AnswerCard({
  a,
  questionId,
  viewer,
  best,
  pickedByAsker,
  canPickBest,
  canRemove,
}: {
  a: Answer;
  questionId: string;
  viewer: Viewer;
  best: boolean;
  pickedByAsker: boolean;
  canPickBest: boolean;
  canRemove: boolean;
}) {
  const router = useRouter();
  const [open, setOpen] = useState(best);
  const [replying, setReplying] = useState(false);
  const sheet = useRef<ShareSheetHandle>(null);
  const byline = answerByline(a);
  const own = Boolean(viewer.id && a.responder?.id === viewer.id);
  const verdict = a.parts?.verdict as Verdict | null | undefined;
  const v = verdict ? VERDICT_ICON[verdict] : null;
  const rating = a.parts?.rating != null ? Number(a.parts.rating) : null;
  const text = a.parts ? a.parts.text : a.body;
  const hasDetails = Boolean(a.parts && ((a.parts.verdict && a.parts.verdict_reason) || a.parts.experience || a.parts.good || a.parts.bad || a.parts.right_for_you || a.parts.photo_urls?.length));
  const tree = replyTree(a.replies ?? []);


  return (
    <article
      id={`answer-${a.id}`}
      data-testid={best ? "best-answer" : "answer"}
      className={best ? "flex flex-col gap-[14px] rounded-[16px] border border-[#e9e9e9] bg-[#f9f9f9] p-4" : "flex flex-col gap-[14px] py-4"}
    >
      <Author
        author={a.responder}
        name={byline.name}
        when={a.created_at}
        seller={byline.seller}
        edited={Boolean(a.edited_at)}
        menu={
          <ItemMenu
            path={`/questions/${questionId}#answer-${a.id}`}
            items={
              own
                ? []
                : [
                    {
                      label: "Report",
                      Icon: Flag,
                      onSelect: () => document.getElementById(`report-trigger-answer-${a.id}`)?.click(),
                    },
                  ]
            }
          />
        }
      />
      {own ? null : (
        <ReportDialog reviewId="" canReport={Boolean(viewer.id)} answer={{ questionId, answerId: a.id }} hideTrigger />
      )}
      {v || rating !== null ? (
        <div className="flex items-center gap-2">
          {v && verdict ? (
            <p className="flex items-center gap-[6px] text-[14px] font-medium leading-normal">
              <v.Icon size={16} aria-hidden className={v.cls} />
              {VERDICT_LABEL[verdict].line}
            </p>
          ) : null}
          <span className="flex-1" />
          {rating !== null ? <StarRow value={rating} size={16} gap={2} /> : null}
        </div>
      ) : null}
      <p className={`whitespace-pre-line text-[14px] leading-[1.55] text-[var(--text-primary)] ${!open && hasDetails ? "line-clamp-4" : ""}`}>{text}</p>
      {open ? <Details a={a} /> : null}
      {hasDetails ? (
        <button type="button" onClick={() => setOpen((o) => !o)} className="w-fit cursor-pointer text-[12px] leading-normal text-[var(--accent-primary)]">
          {open ? "Show less" : "Show full answer"}
        </button>
      ) : null}
      <div className="flex flex-wrap items-center justify-between gap-y-2">
        <div className="flex items-center gap-6">
          <VoteBar
            url={`/questions/${questionId}/answers/${a.id}/vote`}
            up={a.helpful_votes}
            down={a.unhelpful_votes ?? 0}
            mine={a.my_vote}
            own={own}
            viewer={viewer}
            label="answer"
          />
          <button
            type="button"
            onClick={() => (viewer.id ? setReplying((r) => !r) : router.push(viewer.loginHref))}
            className="flex cursor-pointer items-center gap-1 text-[12px] font-light leading-none"
            data-testid="reply-toggle"
          >
            <ArrowBendDownRight size={20} aria-hidden /> Reply{a.reply_count ? ` (${a.reply_count})` : ""}
          </button>
          {!best ? (
            <>
              {/* QA-024: the same share sheet as reviews and comments, not the
                  system sheet on phones and a silent copy on desktops. */}
              <button
                type="button"
                onClick={() => sheet.current?.open()}
                aria-haspopup="dialog"
                className="flex cursor-pointer items-center gap-1 text-[12px] font-light leading-none"
              >
                <ShareNetwork size={20} aria-hidden /> Share
              </button>
              <ShareSheet
                path={`/questions/${questionId}#answer-${a.id}`}
                title={`${byline.name}'s answer`}
                excerpt={text}
                variant="none"
                handle={sheet}
              />
            </>
          ) : null}
        </div>
        {best ? (
          // Figma BestLabel (7731:15707): a 16px outline Medal and the label,
          // 12px Light. DEVIATION (kept on purpose): the frame says "Best";
          // QA-058 requires the page to say who decided, so an asker's pick
          // reads "Best Answer · picked by the person who asked".
          <span className="flex items-center gap-1 text-[12px] font-light leading-normal">
            <Medal size={16} aria-hidden />
            {pickedByAsker ? "Best Answer · picked by the person who asked" : "Best"}
          </span>
        ) : canPickBest ? (
          <BestAnswerButton questionId={questionId} answerId={a.id} />
        ) : null}
      </div>
      {replying ? (
        <ReplyBox
          onCancel={() => setReplying(false)}
          onSubmit={async (body) => {
            const res = await fetch(`/api/bff/api/v1/questions/${questionId}/answers/${a.id}/replies`, {
              method: "POST",
              headers: { "content-type": "application/json" },
              body: JSON.stringify({ body }),
            });
            if (!res.ok) return problem(res, "Couldn't post your reply.");
            setReplying(false);
            router.refresh();
            return null;
          }}
        />
      ) : null}
      {tree.length > 0 ? (
        <div className="pt-1" data-testid="thread">
          <Rail>
            {tree.map((n) => (
              <ReplyItem key={n.id} node={n} questionId={questionId} answerId={a.id} viewer={viewer} canRemove={canRemove} />
            ))}
          </Rail>
        </div>
      ) : null}
    </article>
  );
}

/**
 * Figma "Screen/Question/Thread" (7735:8020, read 2026-10-05), opened from
 * "Continue this thread": "Thread started from" over the answer the thread
 * belongs to in a white card (16px in, radius 16; the label in 12px trust
 * blue; the answer in 14px on a 1.55 line; "View full discussion" in 12px
 * Medium), then the ThreadSheet — white, top radius 24 — with "Show N earlier
 * replies" and their authors when the focused reply is not the first, and the
 * focused reply with three levels of its replies on rails.
 *
 * Built from the replies the page already has (focusThread): no extra read.
 */
function ThreadView({
  questionId,
  answer,
  thread,
  viewer,
  canRemove,
  viewerInitial,
}: {
  questionId: string;
  answer: Answer;
  thread: { node: ReplyNode<Reply>; ancestors: Reply[] };
  viewer: Viewer;
  canRemove: boolean;
  viewerInitial: string;
}) {
  const router = useRouter();
  const [replySignal, setReplySignal] = useState(0);
  const byline = answerByline(answer);
  const text = answer.parts ? answer.parts.text : answer.body;
  const earlier = thread.ancestors;
  const root = thread.node.author;
  const rootName = root ? (root.username ?? root.display_name ?? "Member") : "Former member";
  const names = [...new Set(earlier.map((r) => r.author?.username ?? r.author?.display_name ?? "Former member"))];
  return (
    <section id="thread" aria-label="Thread" className="mt-4 flex scroll-mt-24 flex-col gap-4">
      <div className="mx-4 flex min-w-0 flex-col gap-2.5 rounded-[16px] bg-[var(--surface-card)] p-4 md:mx-0">
        <p className="text-[12px] leading-normal text-[var(--accent-trust)]">Thread started from</p>
        <Author author={answer.responder} name={byline.name} when={answer.created_at} seller={byline.seller} edited={Boolean(answer.edited_at)} />
        <p className="whitespace-pre-line break-words text-[14px] leading-[1.55] text-[var(--text-primary)] [overflow-wrap:anywhere]">{text}</p>
        <Link href={`/questions/${questionId}#reply-${thread.node.id}`} className="self-start text-[12px] font-medium leading-normal hover:text-[var(--accent-primary)]">
          View full discussion
        </Link>
      </div>
      <div className="flex min-w-0 flex-col rounded-t-[24px] bg-[var(--surface-card)] px-4 pb-10 pt-5 md:rounded-[24px]">
        {earlier.length ? (
          <Link
            href={`/questions/${questionId}?thread=${earlier[0].id}#thread`}
            className="flex min-w-0 flex-wrap items-center gap-x-2 gap-y-1 pb-4 text-[12px] leading-normal hover:text-[var(--accent-primary)]"
          >
            <ChatCircle size={16} aria-hidden className="shrink-0" />
            <span className="font-medium">
              Show {earlier.length} earlier {earlier.length === 1 ? "reply" : "replies"}
            </span>{" "}
            <span className="min-w-0 truncate font-light">{names.join(", ")}</span>
          </Link>
        ) : null}
        <ReplyItem node={thread.node} questionId={questionId} answerId={answer.id} viewer={viewer} canRemove={canRemove} depth={0} replySignal={replySignal} />
      </div>
      {/* The thread's Composer (Screen/Question/Thread): "Reply to <name>…"
          replies to the focused reply, opening its reply box. */}
      <ComposerShell initial={viewerInitial}>
        <button
          type="button"
          onClick={() => {
            if (!viewer.id) return router.push(viewer.loginHref);
            setReplySignal((n) => n + 1);
            document.getElementById(`reply-${thread.node.id}`)?.scrollIntoView({ block: "center" });
          }}
          className="flex h-11 flex-1 cursor-pointer items-center rounded-full bg-[#f2f2f2] px-4 text-left text-[14px] font-light text-[rgba(32,32,32,0.5)]"
        >
          Reply to {rootName}…
        </button>
      </ComposerShell>
    </section>
  );
}

/**
 * The page body of Screen/Question (7731:15604): `lead` (the ProductStrip),
 * then the Question sheet — white, radius 24, 20px top and bottom, 16px in —
 * holding `children` (the question itself) and the Best Answer card, then the
 * OtherAnswers sheet with "N more answers" sorted by the chip. Both sheets run
 * edge to edge on the phone, 16px apart on the grey page. `?thread=` swaps all
 * of it for the thread view, which the frame draws on its own
 * (Screen/Question/Thread).
 */
export function AnswersThread({
  questionId,
  answers,
  viewerId,
  loginHref,
  isAsker,
  isStaff,
  pickedByAsker,
  focus = null,
  lead = null,
  children = null,
  composer = null,
}: {
  questionId: string;
  answers: Answer[];
  viewerId: string | null;
  loginHref: string;
  isAsker: boolean;
  isStaff: boolean;
  pickedByAsker: boolean;
  /** `?thread=<reply id>`: show that reply's thread alone (Screen/Question/Thread). */
  focus?: string | null;
  /** What sits above the Question sheet (the ProductStrip). */
  lead?: React.ReactNode;
  /** The question itself: the top of the Question sheet. */
  children?: React.ReactNode;
  /**
   * The sticky Composer at the foot: "Write your answer…" into the answer
   * flow, or in the thread view "Reply to <name>…". Null where answers come
   * through the page's own form (a question about a store).
   */
  composer?: { href: string; initial: string } | null;
}) {
  const [sort, setSort] = useState<"helpful" | "newest">("helpful");
  const viewer: Viewer = { id: viewerId, loginHref };
  if (focus) {
    for (const a of answers) {
      const t = focusThread(a.replies ?? [], focus);
      if (t) {
        return (
          <ThreadView questionId={questionId} answer={a} thread={t} viewer={viewer} canRemove={isStaff} viewerInitial={composer?.initial ?? "?"} />
        );
      }
    }
  }
  const best = answers.find((a) => a.is_best_answer) ?? null;
  const rest = sortAnswers(
    answers.filter((a) => a !== best),
    sort,
  );
  return (
    <>
      {lead}
      <div className="mt-4 flex flex-col gap-[14px] rounded-[24px] bg-[var(--surface-card)] px-4 py-5">
        {children}
        {best ? (
          <AnswerCard a={best} questionId={questionId} viewer={viewer} best pickedByAsker={pickedByAsker} canPickBest={false} canRemove={isStaff} />
        ) : null}
      </div>
      <section aria-label="Answers" className="mt-4 rounded-[24px] bg-[var(--surface-card)] px-4 pb-4 pt-5">
        <div className="flex items-center justify-between pb-1">
          <h2 className="text-[16px] font-medium leading-normal">
            {rest.length === 0
              ? best
                ? "No other answers yet"
                : "No answers yet"
              : `${rest.length} ${best ? "more " : ""}${rest.length === 1 ? "answer" : "answers"}`}
          </h2>
          {rest.length > 1 ? (
            <button
              type="button"
              onClick={() => setSort((s) => (s === "helpful" ? "newest" : "helpful"))}
              className="flex h-8 cursor-pointer items-center gap-1 rounded-[16px] border border-[var(--text-primary)] px-3 text-[12px] leading-none"
            >
              <ArrowsDownUp size={16} aria-hidden />
              {sort === "helpful" ? "Most helpful" : "Newest"}
            </button>
          ) : null}
        </div>
        <div className="divide-y divide-[var(--line-hairline-10)]">
          {rest.map((a) => (
            <AnswerCard
              key={a.id}
              a={a}
              questionId={questionId}
              viewer={viewer}
              best={false}
              pickedByAsker={pickedByAsker}
              canPickBest={isAsker}
              canRemove={isStaff}
            />
          ))}
        </div>
      </section>
      {composer ? <AnswerComposerBar href={composer.href} initial={composer.initial} /> : null}
    </>
  );
}

/** The sticky Composer (7731:15782): "Write your answer…" opens the answer flow. */
export function AnswerComposerBar({ href, initial }: { href: string; initial: string }) {
  return (
    <ComposerShell initial={initial}>
      <Link
        href={href}
        className="flex h-11 flex-1 items-center rounded-full bg-[#f2f2f2] px-4 text-[14px] font-light text-[rgba(32,32,32,0.5)] no-underline"
      >
        Write your answer…
      </Link>
    </ComposerShell>
  );
}
