import type { Metadata } from "next";
import Image from "next/image";
import Link from "next/link";
import { notFound } from "next/navigation";
import { ArrowLeft, ArrowRight, ArrowsDownUp, ChartLine, Check, Equals, X } from "@phosphor-icons/react/dist/ssr";

import { AnswerForm } from "@/components/qa/AnswerForm";
import { AnswersThread, QuestionReactions } from "@/components/qa/QuestionThread";
import { splitQuestionBody } from "@/components/qa/ask-question-model";
import { NotifyMeButton } from "@/components/qa/NotifyMeButton";
import { QuestionOverflowMenu } from "@/components/qa/QuestionOverflowMenu";
import { PriceHistorySheet } from "@/components/product/PriceHistorySheet";
import { questionSubject } from "@/components/qa/question-subject-model";
import { VERDICT_LABEL, VERDICT_ORDER, verdictSummary } from "@/components/qa/question-thread-model";
import { LookingFor } from "@/components/qa/LookingFor";
import { COMPOSER_HEADING, COMPOSER_HINT } from "@/components/reviews/composer-styles";
import { SiteFooter } from "@/components/site/SiteFooter";
import { SiteHeader, type HeaderUser } from "@/components/site/SiteHeader";
import { DetailNavBar } from "@/components/site/DetailNavBar";
import { QuickActions } from "@/components/site/QuickActions";
import { getUser } from "@/lib/dal";
import { usablePhoto } from "@/lib/image";
import { getQuestionDetail } from "@/lib/qa";
import { relativeTime } from "@/lib/relative-time";
import { getSessionToken } from "@/lib/session";

export const metadata: Metadata = {
  title: "Question — bluntly",
};

const STAFF = new Set(["administrator", "super_admin"]);

/** The Verdict Summary's StatStack glyphs (7743:7956): 16px, after the count. */
const SUMMARY_ICON = {
  yes: { Icon: Check, cls: "text-[var(--accent-success)]" },
  on_sale: { Icon: Equals, cls: "text-[var(--text-primary)]" },
  other_variant: { Icon: ArrowsDownUp, cls: "text-[var(--text-primary)]" },
  no: { Icon: X, cls: "text-[var(--accent-danger)]" },
} as const;

/**
 * One question as a thread, built to Figma "Question Detail v6B - Light panel"
 * (7731:15601):
 *
 *   ProductStrip (7731:15605)   the product, and the Verdict Summary: how many
 *                               answers said get it / on sale / other variant /
 *                               skip it, counted from the answers' own verdicts
 *   Question (7731:15647)       the asker and when, the question, the asker's
 *                               situation, Reactions (up-vote toggle, answers +
 *                               replies), then the Best Answer card in full
 *   OtherAnswers (7731:15714)   "N more answers" with the Most helpful chip,
 *                               each answer with its votes, Reply (n), Share
 *                               and its reply thread
 *   Composer (7731:15782)       "Write your answer…" opens the answer flow
 *
 * Votes and replies are real rows (migration 0073). Kept from before, because
 * flows depend on them: "About a product/store" and "Notify me!" (QA-045), the
 * asker's "Pick as Best Answer" (QA-058), and the one-line answer form, which
 * is how a store answers a question about itself.
 *
 * Not drawn, for want of data: "3D Model" (no product has one), "Price
 * History" (no single-product price page exists), the "⋯" menus.
 */
export default async function QuestionPage({
  params,
  searchParams,
}: {
  params: Promise<{ id: string }>;
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const { id } = await params;
  // Figma Screen/Question/Thread: "Continue this thread" opens ?thread=<reply>.
  const threadParam = (await searchParams).thread;
  const focus = typeof threadParam === "string" ? threadParam : null;
  // The viewer's token makes this read uncached (QA-044) and brings their own
  // votes and "Notify me" state.
  const token = await getSessionToken();
  const [question, me] = await Promise.all([getQuestionDetail(id, token), getUser().catch(() => null)]);
  if (!question) notFound();
  const subject = questionSubject(question);
  const { text, requirements } = splitQuestionBody(question.body);
  const [title, ...situation] = text.trim().split("\n");
  const context = situation.join("\n").trim();

  const user: HeaderUser = me ? { username: me.username, avatarUrl: me.avatar_url, role: me.role } : null;
  const isAsker = Boolean(me && me.id === question.asker?.id);
  const loginHref = `/login?next=${encodeURIComponent(`/questions/${question.id}`)}`;
  const summary = verdictSummary(question.answers);
  const image = usablePhoto(question.product_image_url ?? null);
  const asker = question.asker ? (question.asker.display_name ?? question.asker.username ?? "Member") : "Former member";

  const strip = (
    // ProductStrip (7731:15605): white, radius 16, 12px in, 16px from the
    // phone's edges on the grey page; the product, its quiet links, then the
    // Verdict Summary.
    <section key="strip" aria-label="What this question is about" className="mx-4 mt-4 flex flex-col gap-6 rounded-[16px] bg-[var(--surface-card)] p-3 md:mx-0">
      <div className="flex items-center gap-3">
        {image ? (
          <Image src={image} alt="" width={48} height={48} unoptimized className="size-12 shrink-0 rounded-[12px] object-cover" />
        ) : (
          <span aria-hidden className="size-12 shrink-0 rounded-[12px] bg-[var(--surface-app)]" />
        )}
        <span className="flex min-w-0 flex-1 flex-col gap-[2px]">
          {subject.href ? (
            <Link href={subject.href} className="text-[14px] font-medium leading-normal text-[var(--text-primary)] no-underline [overflow-wrap:anywhere] hover:text-[var(--accent-primary)]">
              {subject.label}
            </Link>
          ) : (
            <span className="text-[14px] font-medium leading-normal [overflow-wrap:anywhere]">{subject.label}</span>
          )}
          <span className="flex flex-wrap items-center gap-3">
            {/* Kept (QA-045): what the question is about, beside the tools. */}
            <span className="text-[10px] font-light leading-normal">{question.seller_id ? "About a store" : "About a product"}</span>
            {subject.kind === "product" && question.product_id ? (
              // Tools (7731:15610): "Price History" with its 16px ChartLine, 10px
              // Light. NOT DRAWN: "3D Model" — no product carries a model.
              <PriceHistorySheet
                productId={question.product_id}
                productName={question.product_name}
                triggerClassName="flex cursor-pointer items-center gap-1 rounded-full text-[10px] font-light leading-normal text-[var(--text-primary)] hover:text-[var(--accent-primary)]"
                triggerContent={
                  <>
                    <ChartLine size={16} aria-hidden /> Price History
                  </>
                }
              />
            ) : null}
          </span>
        </span>
      </div>
      {subject.kind === "product" ? (
        <div className="flex flex-col gap-3" data-testid="verdict-summary">
          <p className="flex items-center justify-between text-[12px] leading-normal">
            <span className="text-[var(--chart-honesty-fund)]">Verdict Summary</span>
            <span className="font-light">
              from {summary.total} {summary.total === 1 ? "answer" : "answers"}
            </span>
          </p>
          <dl className="grid grid-cols-4 gap-3">
            {VERDICT_ORDER.map((v) => {
              const { Icon, cls } = SUMMARY_ICON[v];
              return (
                <div key={v} className="flex flex-col gap-[2px]">
                  <dd className="flex items-center gap-1 text-[16px] font-medium leading-normal">
                    {summary.counts[v]}
                    <Icon size={16} aria-hidden className={cls} />
                  </dd>
                  <dt className="order-last text-[10px] font-light leading-normal">{VERDICT_LABEL[v].summary}</dt>
                </div>
              );
            })}
          </dl>
        </div>
      ) : null}
    </section>
  );

  return (
    // The phone draws Screen/Question on the grey app surface: the white
    // ProductStrip, Question and OtherAnswers sheets sit on it.
    <div className="flex min-h-dvh flex-col bg-[var(--surface-app)]">
      <DetailNavBar label="Question" backFallback="/questions" user={user} loginHref={loginHref}>
        <QuestionOverflowMenu questionId={question.id} />
      </DetailNavBar>
      <div className="hidden md:block">
        <SiteHeader user={user} />
      </div>
      <main className="mx-auto w-full max-w-[42rem] flex-1 pb-16 md:px-6 md:pt-4 lg:grid lg:max-w-[72rem] lg:grid-cols-[minmax(0,44rem)_18rem] lg:items-start lg:justify-center lg:gap-12 lg:px-10 lg:pt-10">
        <div className="min-w-0">
          {/* The phone's bar carries Back; from md the site header has none. */}
          <Link
            href="/questions"
            className="hidden items-center gap-1 text-[12px] font-light leading-none text-[var(--text-primary)] no-underline hover:text-[var(--accent-primary)] md:inline-flex"
          >
            <ArrowLeft size={16} aria-hidden="true" /> All questions
          </Link>

          <AnswersThread
            questionId={question.id}
            answers={question.answers}
            viewerId={me?.id ?? null}
            loginHref={loginHref}
            isAsker={isAsker}
            isStaff={Boolean(me && STAFF.has(me.role))}
            pickedByAsker={Boolean(question.best_answer_picked_by_asker)}
            focus={focus}
            lead={strip}
            composer={
              subject.kind === "product"
                ? { href: me ? `/questions/${question.id}/answer` : loginHref, initial: (me?.username?.[0] ?? "?").toUpperCase() }
                : null
            }
          >
            {/* Question (7731:15647): the asker and when, the question, the
                asker's situation, then the Reactions footer. Kept from before,
                because flows depend on them: the "Looking for" chips the answer
                flow enforces, and "Notify me!" (QA-045). */}
            <article key="question" className="flex flex-col gap-[14px]">
              <p className="flex items-center gap-[6px] text-[12px] leading-normal">
                <span aria-hidden className="grid size-5 place-items-center rounded-full bg-[var(--surface-app)] text-[10px] font-medium">
                  {asker[0]?.toUpperCase() ?? "?"}
                </span>
                <span>{asker}</span>
                <span className="font-light">asked {relativeTime(question.created_at)}</span>
              </p>
              <h1 className="text-[20px] font-semibold leading-[1.35] text-[var(--text-primary)] [overflow-wrap:anywhere]">{title}</h1>
              {context ? <p className="whitespace-pre-line text-[14px] font-light leading-[1.5] [overflow-wrap:anywhere]">{context}</p> : null}
              <LookingFor requested={requirements} />
              <div className="flex flex-wrap items-center justify-between gap-3">
                <QuestionReactions
                  questionId={question.id}
                  upvotes={question.upvotes ?? 0}
                  mine={Boolean(question.my_upvote)}
                  own={isAsker}
                  comments={question.answers.length + (question.reply_count ?? 0)}
                  viewerId={me?.id ?? null}
                  loginHref={loginHref}
                />
                <NotifyMeButton questionId={question.id} initiallySubscribed={Boolean(question.is_subscribed)} signedIn={Boolean(me)} />
              </div>
            </article>
          </AnswersThread>

          {/* The one-line form, for a question about a store only. A member's
              answer about a product needs a rating and whatever the asker
              requested (structured Q&A, owner 2026-10-05; the API refuses it
              otherwise), so it goes through the Answer flow below. */}
          {subject.kind !== "product" ? (
            <section className="mx-4 mt-9 md:mx-0">
              <h2 className={COMPOSER_HEADING}>Your answer</h2>
              <p className={COMPOSER_HINT}>Share what you know from actually buying from this store</p>
              <div className="mt-[18px]">
                <AnswerForm questionId={question.id} canAnswer={Boolean(me)} />
              </div>
            </section>
          ) : null}

        </div>

        <aside aria-label="About this question" className="hidden lg:sticky lg:top-[96px] lg:block">
          <div className="rounded-[16px] bg-[var(--surface-card)] p-6 shadow-[var(--shadow-card)]">
            <p className="text-[10px] font-light leading-none text-[rgba(32,32,32,0.7)]">Questions about</p>
            <p className="mt-1.5 text-[14px] font-medium leading-[1.35] [overflow-wrap:anywhere]">{subject.label}</p>
            <dl className="mt-5 grid grid-cols-2 gap-3 border-t border-[var(--line-hairline-10)] pt-4">
              <div>
                <dt className="text-[10px] font-light leading-none text-[rgba(32,32,32,0.7)]">Answers</dt>
                <dd className="mt-1.5 text-[20px] font-semibold leading-none text-[var(--accent-primary)]">{question.answers.length}</dd>
              </div>
              <div>
                <dt className="text-[10px] font-light leading-none text-[rgba(32,32,32,0.7)]">Up-votes</dt>
                <dd className="mt-1.5 text-[20px] font-semibold leading-none text-[var(--accent-primary)]">{question.upvotes ?? 0}</dd>
              </div>
            </dl>
            <Link
              href="/questions/new"
              className="mt-5 flex h-11 items-center justify-center gap-1 rounded-[var(--radius-pill)] bg-[var(--accent-primary)] text-[14px] font-medium leading-none text-[var(--text-on-brand)] no-underline hover:bg-[var(--accent-primary-strong)]"
            >
              Ask your own question <ArrowRight size={16} aria-hidden="true" />
            </Link>
            <Link
              href="/questions"
              className="mt-3 flex h-11 items-center justify-center rounded-[var(--radius-pill)] text-[14px] leading-none text-[var(--text-primary)] no-underline shadow-[inset_0_0_0_1px_var(--line-hairline-30)] hover:text-[var(--accent-primary)]"
            >
              Browse all questions
            </Link>
          </div>
        </aside>
      </main>
      {/* QuickActions/Button (8511:40945); it lifts over the composer while that is docked. */}
      <QuickActions />
      <SiteFooter />
    </div>
  );
}
