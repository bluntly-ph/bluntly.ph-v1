"use client";

import Image from "next/image";
import { useEffect, useState } from "react";
import { ImageBroken, MagnifyingGlass, Package, Storefront } from "@phosphor-icons/react/dist/ssr";

import { AdminModal } from "@/components/admin/AdminModal";
import { InvestigateAnswerButton } from "@/components/admin/queue/AnswerInvestigation";
import { PersonCell, shortAge } from "@/components/admin/queue/QueueCells";

import { TrustBadge } from "@/components/ui/TrustBadge";
import {
  answerPhotos,
  answerTabLabel,
  qaAuthorStats,
  questionEmptyMessage,
  questionRows,
  selectAnswer,
  type QaAuthor,
  type QaQuestion,
  type QaQuestionDetail,
} from "@/components/admin/qa-answers-model";
import { relativeAge } from "@/components/admin/review-queue-model";
import { trustLevel } from "@/lib/trust";
import { TOP_SEARCH_STATES } from "@/components/ui/search-styles";

/**
 * The console's Answers tab, built to frame 6532:278 — since deleted from the
 * Figma file (checked 2026-09-16), so this stands on its last reading and
 * cannot be re-compared. See AdminShell for the full frame provenance.
 *
 * The frame was a question on the left and, on the right, a "Request by:" card,
 * the question, a row of chips, an "Answered by:" card outlined in the brand
 * orange, the answer, and a three-photo grid.
 *
 * WHAT CHANGED AND WHY. This tab used to be a paragraph saying Q&A moderation
 * was not wired up, on the grounds that no `/admin` Q&A endpoint exists. That
 * is still true — and it turns out not to matter. `GET /api/v1/questions` and
 * `GET /api/v1/questions/{id}` already return the asker, every answer, each
 * responder and their trust, and an administrator reading them needs no new route.
 * So the tab now renders real questions and real answers.
 *
 * TWO DOCUMENTED DEVIATIONS, both because the data does not exist rather than
 * because the work was skipped:
 *
 *  - The frame's chips are labelled "Experience" / "Is this right for me?",
 *    i.e. sections WITHIN one answer. `AnswerCreate` takes a single `body`
 *    field, so an answer has no sections. The chips instead select among the
 *    question's answers, which is the same interaction over the data that
 *    exists — and is what the frame's own multi-answer layout implies.
 *  - The three-photo grid has no source at all. See `answerPhotos`.
 *
 * The detail is fetched through the BFF proxy on selection, the same route
 * `AnswerForm` and `BestAnswerButton` already use, rather than pre-fetching a
 * detail for every question on the server.
 */
export function QaAnswersTab({
  questions,
  now,
}: {
  /**
   * `null` means the Q&A request failed, which is NOT the same as "no
   * questions" and must not read like it. See `questionEmptyMessage`.
   */
  questions: QaQuestion[] | null;
  /** The server's render instant — see ReviewQueueScreen's `now`. */
  now: number;
}) {
  const [query, setQuery] = useState("");
  const [selectedQuestionId, setSelectedQuestionId] = useState<string | null>(null);

  const rows = questionRows(questions ?? [], query);
  const emptyMessage = questionEmptyMessage(questions, rows.length);

  const selected = rows.find((q) => q.id === selectedQuestionId) ?? null;

  // Screen/Admin/Queue/Answers 7956:11661: who asked, how big the thread is,
  // and who wrote the Best Answer, so asker-answerer relationships show at a
  // glance (meeting 2026-10-02, 7:11). A row opens the thread in a modal.
  return (
    <div className="flex flex-col gap-3">
      <label className="relative w-full max-w-[18rem]" hidden={questions === null}>
        <MagnifyingGlass
          size={16}
          className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-[var(--text-muted)]"
        />
        <span className="sr-only">Search questions</span>
        <input
          type="search"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search question, product or asker"
          className={`h-9 w-full rounded-[10px] pl-9 pr-3 text-[12px] caret-[var(--accent-primary)] outline-none placeholder:text-[var(--text-secondary)] ${TOP_SEARCH_STATES}`}
        />
      </label>

      <div className="overflow-x-auto rounded-[16px] border border-[var(--border-subtle)]">
        <table className="w-full min-w-[900px] table-fixed border-collapse text-left text-[14px]">
          <caption className="sr-only">Questions and their answers</caption>
          <colgroup>
            <col style={{ width: "34%" }} />
            <col style={{ width: "22%" }} />
            <col style={{ width: "8%" }} />
            <col style={{ width: "23%" }} />
            <col style={{ width: "13%" }} />
          </colgroup>
          <thead className="bg-[var(--surface-app)] text-[12px] text-[var(--text-secondary)]">
            <tr>
              <th scope="col" className="h-10 px-3 font-normal">Question</th>
              <th scope="col" className="px-3 font-normal">Asked by</th>
              <th scope="col" className="px-3 font-normal">Answers</th>
              <th scope="col" className="px-3 font-normal">Best answer</th>
              <th scope="col" className="px-3 font-normal">Asked</th>
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 ? (
              <tr>
                <td
                  colSpan={5}
                  role={questions === null ? "alert" : undefined}
                  className={`border-t border-[var(--border-subtle)] px-3 py-10 text-center ${
                    questions === null ? "text-[var(--accent-danger)]" : "text-[var(--text-secondary)]"
                  }`}
                >
                  {emptyMessage}
                </td>
              </tr>
            ) : (
              rows.map((q) => (
                <tr
                  key={q.id}
                  onClick={() => setSelectedQuestionId(q.id)}
                  className="cursor-pointer border-t border-[var(--border-subtle)] hover:bg-[var(--surface-app)]/60"
                >
                  <td className="px-3 py-[10px]">
                    <button
                      type="button"
                      onClick={(e) => {
                        e.stopPropagation();
                        setSelectedQuestionId(q.id);
                      }}
                      className="flex w-full items-center gap-[10px] text-left focus-visible:outline focus-visible:outline-2 focus-visible:outline-[var(--accent-primary)]"
                    >
                      <span className="relative grid size-8 shrink-0 place-items-center overflow-hidden rounded-[8px] bg-[var(--surface-app)]">
                        {q.product_image_url && q.product_image_url.startsWith("http") ? (
                          <Image src={q.product_image_url} alt="" fill sizes="32px" className="object-cover" />
                        ) : q.seller_name && !q.product_name ? (
                          <Storefront size={16} className="text-[var(--text-muted)]" aria-hidden />
                        ) : (
                          <Package size={16} className="text-[var(--text-muted)]" aria-hidden />
                        )}
                      </span>
                      <span className="flex min-w-0 flex-col gap-1 leading-none">
                        <span className="truncate">{q.body}</span>
                        <span className="truncate text-[12px] text-[var(--text-secondary)]">
                          {q.product_name ?? q.seller_name ?? "Unlisted product"}
                        </span>
                      </span>
                    </button>
                  </td>
                  <td className="px-3">
                    <PersonCell
                      name={q.asker?.display_name ?? q.asker?.username ?? "Deleted account"}
                      stage={q.asker?.trust_stage}
                      levelName={q.asker?.trust_level_name}
                      href={q.asker ? `/admin/people/${q.asker.id}` : undefined}
                    />
                  </td>
                  <td className="px-3">{q.answer_count}</td>
                  <td className="px-3">
                    {q.best_answer_by ? (
                      <PersonCell
                        name={q.best_answer_by.display_name ?? q.best_answer_by.username ?? "Member"}
                        stage={q.best_answer_by.trust_stage}
                        levelName={q.best_answer_by.trust_level_name}
                        href={`/admin/people/${q.best_answer_by.id}`}
                      />
                    ) : (
                      <span className="text-[var(--text-secondary)]">—</span>
                    )}
                  </td>
                  <td className="px-3 text-[var(--text-secondary)]">{shortAge(q.created_at, now)}</td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
      {rows.length > 0 ? (
        <p className="text-[12px] text-[var(--text-secondary)]">
          Showing {rows.length} of {questions?.length ?? 0}
        </p>
      ) : null}

      {selected ? (
        <AdminModal
          title={selected.body}
          subtitle={`Asked about ${selected.product_name ?? selected.seller_name ?? "an unlisted product"} · ${relativeAge(selected.created_at, now)}`}
          onClose={() => setSelectedQuestionId(null)}
        >
          <QuestionDetailPanel key={selected.id} questionId={selected.id} now={now} />
        </AdminModal>
      ) : null}
    </div>
  );
}

/** The frame's right-hand column. */
function QuestionDetailPanel({
  questionId,
  now,
}: {
  questionId: string;
  now: number;
}) {
  const [detail, setDetail] = useState<QaQuestionDetail | null>(null);
  // Starts loading rather than idle: the component only exists once a question
  // is selected, and the fetch begins on its first effect.
  const [state, setState] = useState<"idle" | "loading" | "error">("loading");
  const [answerId, setAnswerId] = useState<string | null>(null);

  useEffect(() => {
    // An administrator clicking down a list outruns the network; without this the
    // slower earlier response would overwrite the newer one.
    const abort = new AbortController();

    fetch(`/api/bff/api/v1/questions/${questionId}`, { signal: abort.signal })
      .then((res) => (res.ok ? res.json() : Promise.reject(new Error(String(res.status)))))
      .then((data: QaQuestionDetail) => {
        setDetail(data);
        setState("idle");
      })
      .catch((error: unknown) => {
        if ((error as { name?: string })?.name === "AbortError") return;
        setDetail(null);
        setState("error");
      });

    return () => abort.abort();
  }, [questionId]);

  return (
    <aside
      aria-live="polite"
      className="flex min-h-0 flex-col gap-4 overflow-y-auto rounded-[var(--radius-md)] bg-[var(--surface-card)] p-5 shadow-[var(--shadow-card)]"
    >
      {state === "loading" && !detail ? (
        <p className="text-[13px] text-[var(--text-secondary)]">Loading the question…</p>
      ) : null}

      {state === "error" ? (
        <p className="text-[13px] text-[var(--accent-danger)]">
          That question could not be loaded. It may have been removed.
        </p>
      ) : null}

      {detail ? (
        <QuestionDetail detail={detail} answerId={answerId} onPick={setAnswerId} now={now} />
      ) : null}
    </aside>
  );
}

function QuestionDetail({
  detail,
  answerId,
  onPick,
  now,
}: {
  detail: QaQuestionDetail;
  answerId: string | null;
  onPick: (id: string) => void;
  now: number;
}) {
  const answer = selectAnswer(detail, answerId);
  const photos = answer ? answerPhotos() : null;

  return (
    <>
      <p className="text-[10px] font-light italic text-[var(--text-secondary)]">Request by:</p>
      <QaPersonCard author={detail.asker} />

      <div>
        <p className="text-[10px] font-bold text-[var(--text-primary)]">
          {detail.product_name ?? detail.seller_name ?? "Unlisted product"}
        </p>
        <p className="mt-1 whitespace-pre-line text-[12px] leading-relaxed text-[var(--text-primary)]">
          {detail.body}
        </p>
      </div>

      {detail.answers.length > 1 ? (
        <div
          role="group"
          aria-label="Answers to this question"
          className="-mx-1 flex gap-2 overflow-x-auto px-1 pb-1"
        >
          {/* Buttons with aria-pressed rather than a tablist: a real tablist
              owes the reader arrow-key roving focus and an associated
              tabpanel, and claiming the role without them is worse for a
              screen reader than not claiming it. */}
          {detail.answers.map((a, index) => {
            const active = a.id === answer?.id;
            return (
              <button
                key={a.id}
                type="button"
                aria-pressed={active}
                onClick={() => onPick(a.id)}
                className={`shrink-0 rounded-[4px] px-2 py-1 text-[10px] transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-[var(--accent-primary)] ${
                  active
                    ? "bg-[color-mix(in_srgb,var(--accent-primary)_14%,transparent)] text-[var(--accent-primary)]"
                    : "bg-[color-mix(in_srgb,var(--text-primary)_3%,transparent)] text-[var(--text-primary)] hover:bg-[var(--line-hairline-10)]"
                }`}
              >
                {answerTabLabel(a, index)}
              </button>
            );
          })}
        </div>
      ) : null}

      {answer ? (
        <div className="rounded-[var(--radius-md)] border border-[color-mix(in_srgb,var(--accent-primary)_30%,transparent)] p-4">
          <p className="text-[10px] font-light italic text-[var(--text-secondary)]">Answered by:</p>
          <div className="mt-2">
            <QaPersonCard author={answer.responder} />
          </div>

          <p className="mt-3 whitespace-pre-line text-[12px] leading-relaxed text-[var(--text-primary)]">
            {answer.body}
          </p>

          <p className="mt-2 text-[10px] text-[var(--text-muted)]">
            {relativeAge(answer.created_at, now)}
            {answer.is_best_answer ? " · Accepted by the asker" : ""}
            {answer.is_first_responder ? " · First responder" : ""}
          </p>

          <InvestigateAnswerButton answerId={answer.id} />

          {photos && !photos.available ? (
            <div
              title={photos.reason}
              className="mt-3 flex items-center gap-2 rounded-[var(--radius-sm)] bg-[var(--surface-app)] px-3 py-2.5"
            >
              <ImageBroken size={20} className="shrink-0 text-[var(--text-muted)]" aria-hidden="true" />
              <p className="text-[10px] leading-snug text-[var(--text-secondary)]">
                Answers hold text only — no photos are collected.
              </p>
            </div>
          ) : null}
        </div>
      ) : (
        <p className="rounded-[var(--radius-md)] bg-[var(--surface-app)] p-4 text-[12px] text-[var(--text-secondary)]">
          Nobody has answered this question yet.
        </p>
      )}
    </>
  );
}

/** The frame's participant card: avatar, name, level, then four stats. */
function QaPersonCard({ author }: { author: QaAuthor | null }) {
  const stats = qaAuthorStats(author);
  const name = author?.display_name ?? author?.username ?? "Deleted account";

  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center gap-2">
        <span
          aria-hidden="true"
          className="grid size-8 shrink-0 place-items-center rounded-full bg-[var(--accent-primary)] text-[12px] font-bold text-[var(--text-on-brand)]"
        >
          {name.slice(0, 1).toUpperCase()}
        </span>
        <span className="min-w-0">
          <span className="block truncate text-[12px] text-[var(--text-primary)]">{name}</span>
          <span className="block truncate text-[10px] font-light text-[var(--text-secondary)]">
            {trustLevel(author?.trust_level_name, author?.trust_stage)}
          </span>
        </span>
      </div>

      <dl className="grid grid-cols-2 gap-x-4 gap-y-2 sm:grid-cols-4">
        {stats.map((stat) => (
          <div key={stat.label}>
            <dt className="text-[10px] font-light text-[var(--text-secondary)]">{stat.label}</dt>
            <dd className="text-[12px] text-[var(--text-primary)]">
              {stat.available ? (
                stat.label === "Trust Score" ? (
                  <TrustBadge
                    levelName={author?.trust_level_name}
                    stage={author?.trust_stage}
                    score={author?.reputation_score}
                    compact
                    plain
                  />
                ) : (
                  stat.value
                )
              ) : (
                <span title={stat.reason} className="text-[var(--text-muted)]">
                  Not available
                </span>
              )}
            </dd>
          </div>
        ))}
      </dl>
    </div>
  );
}

export default QaAnswersTab;
