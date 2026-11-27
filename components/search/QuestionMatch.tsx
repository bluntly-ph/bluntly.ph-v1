import Link from "next/link";
import { ArrowFatUp, ChatCircle, Medal, NotePencil } from "@phosphor-icons/react/dist/ssr";
import type { ReactNode } from "react";

import { splitQuestionBody } from "@/components/qa/ask-question-model";
import { LookingFor } from "@/components/qa/LookingFor";
import { AuthorHeader } from "@/components/review/AuthorHeader";
import { Avatar } from "@/components/ui/Avatar";
import type { Answer, Question, QuestionDetail } from "@/lib/qa";
import { relativeTime } from "@/lib/relative-time";

// Figma Screen/Search/Questions (7718:12930, read live 2026-10-05): white
// cards at radius 16, 16px in, no shadow; 12px blue section eyebrows.
const CARD = "mx-4 rounded-[16px] bg-[var(--surface-card)] p-4 md:mx-0";
const EYEBROW = "text-[12px] text-[var(--chart-honesty-fund)]";

/** The search's question words, marked where the question uses them (Figma: orange). */
export function Highlight({ text, terms }: { text: string; terms: string }): ReactNode {
  const words = terms
    .toLowerCase()
    .split(/\s+/)
    .filter((w) => w.length >= 3)
    .map((w) => w.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"));
  if (!words.length) return text;
  const re = new RegExp(`(${words.join("|")})`, "gi");
  return text.split(re).map((part, i) =>
    i % 2 === 1 ? (
      <mark key={i} className="bg-transparent text-[var(--accent-primary)]">
        {part}
      </mark>
    ) : (
      part
    ),
  );
}

const body = (q: Question) => splitQuestionBody(q.body).text;
const requested = (q: Question) => splitQuestionBody(q.body).requirements;

/** A row's Meta (7722:7517): 16px glyphs, 12px Light counts, 12px apart. */
function Meta({ q }: { q: Question }) {
  return (
    <span className="flex items-center gap-3 text-[12px] font-light leading-normal">
      {q.best_answer_id ? (
        <span className="flex items-center gap-1">
          <Medal size={16} aria-hidden /> Best answer
        </span>
      ) : null}
      <span className="flex items-center gap-1">
        <ChatCircle size={16} aria-hidden /> {q.answer_count} answer{q.answer_count === 1 ? "" : "s"}
      </span>
    </span>
  );
}

function QuestionList({ title, items, terms, seeAll }: { title: string; items: Question[]; terms: string; seeAll: { href: string; label: string } | null }) {
  if (!items.length && !seeAll) return null;
  return (
    <section aria-label={title} className={`${CARD} pb-1`}>
      <p className={EYEBROW}>{title}</p>
      <ul className="flex flex-col">
        {items.map((q) => (
          <li key={q.id} className="border-b border-[#d9d9d9] py-4 first:pt-3">
            <Link href={`/questions/${q.id}`} className="flex flex-col gap-2 hover:underline">
              <span className="text-[14px] leading-[1.4] [overflow-wrap:anywhere]">
                <Highlight text={body(q)} terms={terms} />
              </span>
              <LookingFor requested={requested(q)} />
              <Meta q={q} />
            </Link>
          </li>
        ))}
      </ul>
      {seeAll ? (
        <Link href={seeAll.href} className="block pb-3 pt-4 text-center text-[14px] font-medium">
          {seeAll.label}
        </Link>
      ) : null}
    </section>
  );
}

function topAnswer(d: QuestionDetail | null): Answer | null {
  if (!d?.answers.length) return null;
  return d.answers.find((a) => a.is_best_answer) ?? [...d.answers].sort((a, b) => b.helpful_votes - a.helpful_votes)[0];
}

/**
 * The Questions tab once the search names a product (Figma Mobile Search v6
 * "Match" 7718:12930 and "No match" 7724:7520): the best-matching question
 * with its top answer, the similar ones, and asking the product's community
 * when nothing fits. Without question words it lists the product's questions.
 */
export function QuestionMatch({
  productName,
  terms,
  matches,
  best,
  related,
  total,
  activeNow,
  seeAllHref,
  now,
}: {
  productName: string;
  /** The question words: the search minus the words that named the product. */
  terms: string;
  matches: Question[];
  best: QuestionDetail | null;
  related: Question[];
  total: number;
  activeNow: number;
  seeAllHref: string;
  now: number;
}) {
  const others = Math.max(0, total - (matches.length ? 1 : 0));
  // "See all 39 other questions" counts the ones not already the best match.
  const listed = matches.length ? others : total;
  const seeAll = listed > 0 ? { href: seeAllHref, label: `See all ${listed.toLocaleString("en-PH")} ${matches.length ? "other " : ""}question${listed === 1 ? "" : "s"}` } : null;
  const active = (
    <span className="flex items-center gap-[6px] text-[12px] font-light leading-normal">
      <span className="size-2 rounded-full bg-[var(--accent-success)]" aria-hidden /> {activeNow} active on this {matches.length ? "discussion" : "thread"}
    </span>
  );

  if (!matches.length) {
    return (
      <div className="mt-4 flex flex-col gap-4" data-testid="question-no-match">
        <section aria-label="No match" className={`${CARD} flex items-center gap-3`}>
          <div className="flex min-w-0 flex-1 flex-col gap-1">
            <p className="text-[12px] text-[var(--accent-danger)]">No match for your search</p>
            <p className="text-[16px] font-semibold">No one asked this yet</p>
            {active}
          </div>
          <Link href="/questions/new" className="flex h-9 shrink-0 items-center gap-1 rounded-full border border-[var(--text-primary)] px-3 text-[13px]">
            Ask question <NotePencil size={14} aria-hidden />
          </Link>
        </section>
        <QuestionList title="Related questions" items={related} terms="" seeAll={seeAll} />
      </div>
    );
  }

  const [first, ...rest] = matches;
  // Figma "Similar questions" (7718:12974) lists three: the other matches
  // first, then the product's other questions, never one already shown.
  const shown = new Set(matches.map((m) => m.id));
  const similar = [...rest, ...related.filter((r) => !shown.has(r.id))].slice(0, 3);
  const answer = topAnswer(best);
  const name = answer?.responder?.display_name ?? answer?.responder?.username ?? "Member";
  // OthersSaid (7718:12968): up to three of the other answerers, overlapping.
  const others3 = (best?.answers ?? []).filter((a) => a.id !== answer?.id).slice(0, 3);
  const othersCount = Math.max(0, first.answer_count - (answer ? 1 : 0));
  return (
    <div className="mt-4 flex flex-col gap-4" data-testid="question-match">
      <section aria-label="Best match for your search" className={`${CARD} flex flex-col gap-4`}>
        <p className={EYEBROW}>Best match for your search</p>
        <Link href={`/questions/${first.id}`} className="block text-[18px] font-semibold leading-[1.35] [overflow-wrap:anywhere] hover:underline">
          <Highlight text={body(first)} terms={terms} />
        </Link>
        <LookingFor requested={requested(first)} />
        {answer ? (
          <div className="flex flex-col gap-[14px] rounded-[12px] border border-[#e9e9e9] bg-[#f9f9f9] p-[18px]">
            <AuthorHeader
              name={name}
              avatarUrl={null}
              age={<span suppressHydrationWarning>{relativeTime(answer.created_at, now)}</span>}
              levelName={answer.responder?.trust_level_name ?? null}
              stage={answer.responder?.trust_stage ?? null}
              score={answer.responder?.reputation_score ?? null}
              seller={answer.is_seller_answer}
            />
            <p className="line-clamp-5 text-[14px] leading-[1.5] [overflow-wrap:anywhere]">{answer.parts?.text ?? answer.body}</p>
            <p className="flex items-center gap-4 text-[12px] font-light leading-normal">
              <span className="flex items-center gap-1">
                <ArrowFatUp size={16} weight="fill" className="text-[var(--accent-success)]" aria-label="Helpful" /> {answer.helpful_votes}
              </span>
              {answer.is_best_answer ? (
                <span className="flex items-center gap-1">
                  <Medal size={16} aria-hidden /> Best
                </span>
              ) : null}
            </p>
          </div>
        ) : (
          <p className="text-[12px] font-light">No answer yet. Be the first.</p>
        )}
        {othersCount > 0 ? (
          <Link href={`/questions/${first.id}`} className="flex items-center gap-2 text-[12px] font-light leading-normal hover:underline">
            {others3.length ? (
              <span className="flex" aria-hidden="true">
                {others3.map((o, i) => (
                  <Avatar
                    key={o.id}
                    name={o.seller_name ?? o.responder?.display_name ?? o.responder?.username ?? "M"}
                    url={null}
                    size={20}
                    ring
                    className={i ? "-ml-[6px]" : ""}
                  />
                ))}
              </span>
            ) : null}
            Read what {othersCount} other{othersCount === 1 ? "" : "s"} said
          </Link>
        ) : null}
      </section>
      <QuestionList title="Similar questions" items={similar} terms={terms} seeAll={others > 0 ? seeAll : null} />
      <section aria-label="Ask the community" className={`${CARD} flex items-center gap-3`}>
        <div className="flex min-w-0 flex-1 flex-col gap-1">
          <p className={EYEBROW}>Can&rsquo;t find your question?</p>
          <p className="text-[14px] font-medium [overflow-wrap:anywhere]">Ask the {productName} community</p>
          {active}
        </div>
        <Link href="/questions/new" className="flex h-8 shrink-0 items-center rounded-[20px] bg-[var(--surface-app)] px-3 text-[12px] font-light leading-4">
          Ask
        </Link>
      </section>
    </div>
  );
}
