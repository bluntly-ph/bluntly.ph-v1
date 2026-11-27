import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { CheckCircle, PencilSimple, Users } from "@phosphor-icons/react/dist/ssr";

import { BestAnswerButton } from "@/components/requests/BestAnswerButton";
import { RequestUpvote } from "@/components/requests/RequestUpvote";
import { BrowseLayout, RAIL_ACTION, RailGroup, TakePartGroup } from "@/components/site/BrowseRails";
import { SiteFooter } from "@/components/site/SiteFooter";
import { SiteHeader, type HeaderUser } from "@/components/site/SiteHeader";
import { CtaLink } from "@/components/ui/CtaLink";
import { getUser } from "@/lib/dal";
import { getRequest, getRequestAnswers } from "@/lib/requests";
import { getSessionToken } from "@/lib/session";

export const metadata: Metadata = {
  title: "Request — bluntly",
};

const STATUS_WORDS: Record<string, string> = {
  open: "Open: waiting for the Best Answer",
  fulfilled: "Answered: Best Answer picked",
  expired: "Expired",
  cancelled: "Cancelled by the asker",
};

const VERDICT_WORDS: Record<string, string> = {
  yes_absolutely: "Yes, absolutely",
  it_depends: "It depends",
  hard_pass: "Hard pass",
};

/**
 * A request's own page: where it lives for good (dev/QA sync 2026-09-29).
 *
 * The team's final Bounty Board model: a request names a product and belongs
 * to it; the board only surfaces open, most-wanted requests for the people who
 * can answer; every later review of the product is an answer; the ASKER picks
 * the Best Answer, and the request leaves the board without being deleted or
 * archived. This page is what stays: the question, every answer, the pick.
 * Every request notice links here ("Someone answered your request" used to
 * open the review alone, or a board the request had already left).
 */
export default async function RequestPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const token = await getSessionToken();
  const [me, req, answers] = await Promise.all([
    getUser().catch(() => null),
    getRequest(id, token),
    getRequestAnswers(id),
  ]);
  if (!req) notFound();
  const user: HeaderUser = me ? { username: me.username, avatarUrl: me.avatar_url, role: me.role } : null;
  const isAsker = me !== null && req.requester_id === me.id;
  const canPick = isAsker && (req.status === "open" || req.status === "expired");
  const open = req.status === "open";

  return (
    <div className="flex min-h-dvh flex-col bg-[var(--surface-app)]">
      <SiteHeader user={user} />
      <main className="flex flex-1 flex-col">
        <BrowseLayout
          current="requests"
          outerClassName="mx-auto w-full max-w-[52rem] flex-1 px-6 py-8 lg:max-w-[76rem] lg:px-10 lg:py-10"
          aside={
            <>
              <RailGroup title="How answers work">
                <p className="mt-3 text-[13px] leading-[20px] text-[var(--text-secondary)]">
                  Every review of this product written after the request answers it. The person who asked picks
                  the Best Answer; the request then leaves the board and stays here.
                </p>
                <ul className="mt-3 flex flex-col gap-2 text-[13px]">
                  <li>
                    <Link href="/requests" className={RAIL_ACTION}>
                      Back to the board
                    </Link>
                  </li>
                  {req.product_name ? (
                    <li>
                      <Link href={`/search?q=${encodeURIComponent(req.product_name)}`} className={RAIL_ACTION}>
                        Everything about this product
                      </Link>
                    </li>
                  ) : null}
                </ul>
              </RailGroup>
              <TakePartGroup className="mt-8" />
            </>
          }
        >
          <article id={`request-${req.id}`} data-testid="request-page" data-status={req.status}>
            <div className="flex gap-4">
              <RequestUpvote
                requestId={req.id}
                count={req.upvote_count}
                canVote={me !== null && !isAsker && open}
                myUpvote={req.my_upvote}
              />
              <div className="min-w-0 flex-1">
                <p className="text-[12px] text-[var(--text-secondary)]">
                  {req.product_name ? (
                    <>
                      About{" "}
                      <Link
                        href={`/search?q=${encodeURIComponent(req.product_name)}`}
                        className="font-medium text-[var(--text-primary)] underline"
                      >
                        {req.product_name}
                      </Link>
                    </>
                  ) : (
                    "Review request"
                  )}
                </p>
                <h1 className="mt-1 text-[22px] font-bold text-[var(--text-primary)]">{req.title}</h1>
                <p className="mt-2 whitespace-pre-line break-words text-[14px] text-[var(--text-secondary)]">
                  {req.details}
                </p>
                <p className="mt-3 flex flex-wrap items-center gap-2 text-[12px]">
                  <span
                    data-testid="request-status"
                    className={`inline-flex items-center gap-1 rounded-[var(--radius-pill)] px-2.5 py-1 ${
                      req.status === "fulfilled"
                        ? "bg-[color-mix(in_srgb,var(--accent-success)_14%,transparent)] text-[var(--accent-success)]"
                        : "bg-[var(--line-hairline-10)] text-[var(--text-secondary)]"
                    }`}
                  >
                    {req.status === "fulfilled" ? <CheckCircle size={14} weight="fill" /> : null}
                    {STATUS_WORDS[req.status] ?? req.status}
                  </span>
                  {req.upvote_count > 0 ? (
                    <span className="inline-flex items-center gap-1 text-[var(--text-secondary)]">
                      <Users size={13} weight="fill" /> {req.upvote_count} waiting
                    </span>
                  ) : null}
                </p>
                {open && !isAsker && req.product_id ? (
                  <div className="mt-4">
                    <CtaLink
                      href={`/reviews/new?product=${encodeURIComponent(req.product_id)}`}
                      size="sm"
                      icon={<PencilSimple size={16} weight="fill" />}
                    >
                      Answer with a review
                    </CtaLink>
                  </div>
                ) : null}
              </div>
            </div>

            <h2 className="mt-8 text-[16px] font-semibold text-[var(--text-primary)]">
              {answers && answers.length > 0
                ? `${answers.length} ${answers.length === 1 ? "answer" : "answers"}`
                : "Answers"}
            </h2>
            {canPick && answers && answers.length > 0 ? (
              <p className="mt-1 text-[13px] text-[var(--text-secondary)]">
                You asked this. Pick the review that answered it best; the request then leaves the board.
              </p>
            ) : null}
            {answers === null ? (
              <p className="mt-3 text-[14px] text-[var(--text-secondary)]">The answers could not be loaded.</p>
            ) : answers.length === 0 ? (
              <p className="mt-3 rounded-[var(--radius-sm)] bg-[var(--surface-card)] p-6 text-[14px] text-[var(--text-secondary)] shadow-[var(--shadow-hairline-inset)]">
                No answers yet. A review of this product written from now on answers it.
              </p>
            ) : (
              <ul className="mt-3 flex flex-col gap-3" data-testid="request-answers">
                {answers.map((a) => (
                  <li
                    key={a.review_id}
                    data-best={a.is_best ? "true" : undefined}
                    className={`rounded-[var(--radius-sm)] bg-[var(--surface-card)] p-4 shadow-[var(--shadow-card)] ${
                      a.is_best ? "ring-2 ring-[var(--accent-success)]" : ""
                    }`}
                  >
                    {a.is_best ? (
                      <p className="mb-1 inline-flex items-center gap-1 text-[12px] font-semibold text-[var(--accent-success)]">
                        <CheckCircle size={14} weight="fill" /> Best Answer · picked by the person who asked
                      </p>
                    ) : null}
                    <Link
                      href={`/reviews/${a.review_id}`}
                      className="block text-[15px] font-semibold text-[var(--text-primary)] hover:underline"
                    >
                      {a.title ?? "Untitled review"}
                    </Link>
                    <p className="mt-0.5 text-[12px] text-[var(--text-secondary)]">
                      {[
                        a.author_username ? `@${a.author_username}` : a.author_display_name,
                        `${a.star_rating}★`,
                        VERDICT_WORDS[a.verdict] ?? a.verdict,
                      ]
                        .filter(Boolean)
                        .join(" · ")}
                    </p>
                    <p className="mt-2 line-clamp-4 break-words text-[13px] text-[var(--text-primary)]">{a.excerpt}</p>
                    {canPick ? <BestAnswerButton requestId={req.id} reviewId={a.review_id} /> : null}
                  </li>
                ))}
              </ul>
            )}
          </article>
        </BrowseLayout>
      </main>
      <SiteFooter />
    </div>
  );
}
