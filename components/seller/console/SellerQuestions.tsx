"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { Bell } from "@phosphor-icons/react/dist/ssr";

import { AdminModal } from "@/components/admin/AdminModal";
import { ConfirmDialog } from "@/components/admin/ConfirmDialog";
import { PersonCell } from "@/components/admin/queue/QueueCells";
import { Callout } from "@/components/console/Callout";
import { countState } from "@/components/console/counted-model";
import { CountedTextarea } from "@/components/console/CountedTextarea";
import { ListControls } from "@/components/console/ListControls";
import { Pagination } from "@/components/console/Pagination";

import { agoShort } from "./overview-model";
import { oldestUnanswered } from "./quick-actions-model";
import {
  QUESTION_DEFAULT_SORT,
  QUESTION_SORTS,
  QUESTION_TABS,
  applyQuestions,
  askerOf,
  inQuestionTab,
  questionFilters,
  questionSummary,
  type QuestionTab,
  type StoreQuestion,
} from "./questions-model";

/**
 * Screen/Seller/Questions (Figma 8196:21469, Answered 8201:22543, All
 * 8201:22842), Overlay/Store/Answer 8197:21523 and Confirm/Store/PostAnswer
 * 8202:22661, on GET /sellers/{id}/questions (owner only). Answer posts the
 * store's answer through the existing POST /questions/{id}/answers, which
 * labels it "From the store" (no Best Answer, no earning).
 *
 * Not drawn yet, for want of data: the frame's "About" (no store-product link
 * exists, so every question is about the store) and "Following" columns, and
 * editing an answer (no endpoint).
 */

const MAX = 1000;

export function SellerQuestions({
  questions,
  now,
  answerTo = null,
  storeId,
  initialTab = "unanswered",
  query = {},
}: {
  questions: StoreQuestion[];
  now: number;
  storeId: string;
  initialTab?: QuestionTab;
  /** Sort / Filter / Search from the URL (Figma Menu/Seller/Questions/*). */
  query?: Record<string, string>;
  /** ?answer= on arrival: "oldest" (Quick actions) or a question's id. Opens Answer on it. */
  answerTo?: string | null;
}) {
  const router = useRouter();
  const [tab, setTab] = useState<QuestionTab>(initialTab);
  const [page, setPage] = useState({ page: 1, size: 10 });
  const [answering, setAnswering] = useState<StoreQuestion | null>(() =>
    answerTo === "oldest" ? oldestUnanswered(questions) : (questions.find((q) => q.id === answerTo) ?? null),
  );
  const counts = { unanswered: 0, answered: 0, all: questions.length };
  for (const q of questions) counts[q.store_answer ? "answered" : "unanswered"] += 1;
  const inTab = questions.filter((q) => inQuestionTab(q, tab));
  const shown = applyQuestions(inTab, query);
  const filtering = Boolean(query.community || query.q);
  // Figma: Unanswered / All draw Asked · Answers · Following; Answered draws Your answer · Answered.
  const answeredView = tab === "answered";
  const headers = answeredView ? ["Question", "Your answer", "Answered", "Action"] : ["Question", "Asked", "Answers", "Following", "Action"];
  const rows = shown.slice((page.page - 1) * page.size, page.page * page.size);
  const s = questionSummary(questions);

  return (
    <div className="flex flex-col gap-4">
      <h1 className="text-[24px] font-semibold leading-none">Questions</h1>
      <div className="flex flex-wrap items-center gap-2">
      <nav aria-label="Question views" className="flex w-fit flex-wrap gap-[2px] rounded-[10px] bg-[var(--surface-app)] p-[3px]">
        {QUESTION_TABS.map((t) => (
          <button
            key={t.key}
            type="button"
            aria-current={tab === t.key ? "page" : undefined}
            onClick={() => {
              setTab(t.key);
              setPage((p) => ({ ...p, page: 1 }));
            }}
            className={`flex items-center gap-[6px] rounded-[8px] px-3 py-[5px] leading-none ${
              tab === t.key ? "bg-[var(--surface-card)] shadow-[var(--shadow-segment)]" : "text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
            }`}
          >
            <span className="text-[14px] font-medium">{t.label}</span>
            <span className="text-[12px] text-[var(--text-secondary)]">{counts[t.key]}</span>
          </button>
        ))}
      </nav>
        <span className="flex-1" />
        <ListControls
          basePath={`/seller/${storeId}/questions`}
          params={{ ...query, ...(tab === "unanswered" ? {} : { tab }) }}
          sorts={QUESTION_SORTS}
          defaultSort={QUESTION_DEFAULT_SORT}
          filters={questionFilters(inTab)}
          search={{ placeholder: "Question or who asked", label: "Search questions" }}
        />
      </div>

      <section aria-label="Answers at a glance" className="grid gap-3 sm:grid-cols-3">
        <Card
          label="Unanswered"
          value={String(s.unanswered)}
          note={s.oldest ? `Oldest has waited ${agoShort(new Date(s.oldest).toISOString(), now).replace(" ago", "")}` : "Nothing waiting"}
        />
        <Card label="Answer rate" value={s.rate == null ? "—" : `${Math.round(s.rate * 100)}%`} note={`${s.answered} of ${s.total} questions`} />
        <Card
          label="Median time to answer"
          value={s.medianHours == null ? "—" : s.medianHours < 1 ? `${Math.max(1, Math.round(s.medianHours * 60))} min` : s.medianHours < 48 ? `${Math.round(s.medianHours)} h` : `${Math.round(s.medianHours / 24)} days`}
          note="Your answers, all time"
        />
      </section>

      <div className="overflow-x-auto rounded-[16px] border border-[var(--border-subtle)]">
        <table className="w-full min-w-[860px] border-collapse text-left text-[14px]">
          <caption className="sr-only">Questions about your store</caption>
          <thead className="bg-[var(--surface-app)] text-[12px] text-[var(--text-secondary)]">
            <tr>
              {headers.map((h) => (
                <th key={h} scope="col" className="h-10 px-3 font-normal">
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 ? (
              <tr>
                <td colSpan={headers.length} className="border-t border-[var(--border-subtle)] px-3 py-10 text-center text-[var(--text-secondary)]">
                  {questions.length === 0
                    ? "No one has asked your store a question yet."
                    : filtering
                      ? "No question matches these filters."
                      : tab === "unanswered"
                        ? "Every question has your answer."
                        : "Nothing here yet."}
                </td>
              </tr>
            ) : (
              rows.map((q) => (
                <tr key={q.id} data-testid="seller-question-row" className="border-t border-[var(--border-subtle)] align-top hover:bg-[var(--surface-app)]">
                  <td className="max-w-[380px] px-3 py-[10px]">
                    <span className="flex flex-col gap-1">
                      <span className="line-clamp-2">{q.body}</span>
                      <span className="text-[12px] text-[var(--text-secondary)]">asked by {askerOf(q)}</span>
                    </span>
                  </td>
                  {answeredView ? (
                    <>
                      <td className="max-w-[320px] px-3 py-[10px] text-[var(--text-secondary)]">
                        <span className="line-clamp-2">{q.store_answer?.body ?? "—"}</span>
                      </td>
                      <td className="whitespace-nowrap px-3 py-[10px] text-[var(--text-secondary)]" suppressHydrationWarning>
                        {q.store_answer ? agoShort(q.store_answer.created_at, now) : "—"}
                      </td>
                    </>
                  ) : (
                    <>
                      <td className="whitespace-nowrap px-3 py-[10px] text-[var(--text-secondary)]" suppressHydrationWarning>
                        {agoShort(q.created_at, now)}
                      </td>
                      <td className="px-3 py-[10px] [font-variant-numeric:tabular-nums]">{q.community_answers ?? q.answer_count}</td>
                      <td className="px-3 py-[10px] [font-variant-numeric:tabular-nums]">{q.followers ?? 0}</td>
                    </>
                  )}
                  <td className="px-3 py-[6px]">
                    {q.store_answer ? (
                      <button
                        type="button"
                        onClick={() => setAnswering(q)}
                        className="h-8 rounded-full border border-[var(--border-subtle)] bg-[var(--surface-card)] px-3 text-[12px] hover:border-[var(--text-secondary)]"
                      >
                        Edit
                      </button>
                    ) : (
                      <button
                        type="button"
                        onClick={() => setAnswering(q)}
                        className="h-8 rounded-full border border-[var(--border-subtle)] bg-[var(--surface-card)] px-3 text-[12px] hover:border-[var(--text-secondary)]"
                      >
                        Answer
                      </button>
                    )}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
      <Pagination page={page.page} size={page.size} total={shown.length} onChange={setPage} label="Question pages" />
      {answering ? (
        <AnswerModal
          key={answering.id}
          question={answering}
          onClose={() => {
            setAnswering(null);
            // Drop ?answer= so a refresh doesn't open it again.
            if (answerTo) router.replace(window.location.pathname, { scroll: false });
          }}
          now={now}
        />
      ) : null}
    </div>
  );
}

function Card({ label, value, note }: { label: string; value: string; note: string }) {
  return (
    <div className="flex flex-col gap-2 rounded-[16px] border border-[var(--border-subtle)] p-5">
      <span className="text-[12px] text-[var(--text-secondary)]">{label}</span>
      <span className="text-[24px] font-semibold leading-none [font-variant-numeric:tabular-nums]">{value}</span>
      <span className="text-[12px] text-[var(--text-secondary)]">{note}</span>
    </div>
  );
}

/**
 * Overlay/Store/Answer (8197:21523), and Overlay/Store/EditAnswer (8202:22530)
 * when the store has answered: the answer prefilled, "Save changes", buyers see
 * "Edited" (PATCH /questions/{id}/answers/{answer_id}, owner only).
 */
function AnswerModal({ question, onClose, now }: { question: StoreQuestion; onClose: () => void; now: number }) {
  const router = useRouter();
  const existing = question.store_answer ?? null;
  const [body, setBody] = useState(existing?.body ?? "");
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const asker = askerOf(question);

  const unchanged = existing !== null && body.trim() === existing.body.trim();

  async function post() {
    setBusy(true);
    setError(null);
    try {
      const res = await fetch(
        existing ? `/api/bff/api/v1/questions/${question.id}/answers/${existing.id}` : `/api/bff/api/v1/questions/${question.id}/answers`,
        {
          method: existing ? "PATCH" : "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({ body: body.trim() }),
        },
      );
      if (!res.ok) {
        const p = (await res.json().catch(() => ({}))) as { detail?: string };
        setError(typeof p.detail === "string" ? p.detail : existing ? "Your changes couldn't be saved." : "Your answer couldn't be posted.");
        setConfirming(false);
        return;
      }
      setConfirming(false);
      onClose();
      router.refresh();
    } catch {
      setError("Couldn't reach the server.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <AdminModal title={existing ? "Edit your answer" : "Answer a question"} width={560} onClose={onClose}>
        <div className="flex flex-col gap-4 overflow-y-auto px-6 pb-5 pt-4">
          {existing ? (
            <div className="flex flex-col gap-2 rounded-[16px] border border-[var(--border-subtle)] p-4">
              <span className="text-[12px] text-[var(--text-secondary)]" suppressHydrationWarning>
                asked by {asker} · {agoShort(question.created_at, now)} · about your store
              </span>
              <p className="text-[16px] font-medium">{question.body}</p>
              <span className="flex items-center gap-1.5 text-[12px] text-[var(--text-secondary)]" suppressHydrationWarning>
                <Bell size={14} aria-hidden /> You answered {agoShort(existing.created_at, now)}
                {existing.edited_at ? ` · edited ${agoShort(existing.edited_at, now)}` : ""}
              </span>
            </div>
          ) : (
          <div className="flex flex-col gap-2">
            <span className="text-[12px] text-[var(--text-secondary)]" suppressHydrationWarning>
              asked by {asker} · {agoShort(question.created_at, now)}
            </span>
            <p className="text-[16px] font-medium">{question.body}</p>
            <PersonCell name={asker} stage={question.asker?.trust_stage ?? null} />
            <span className="text-[12px] text-[var(--text-secondary)]">
              {question.answer_count ? `${question.answer_count} community answer${question.answer_count === 1 ? "" : "s"} so far` : "No answers yet"}
            </span>
          </div>
          )}
          <CountedTextarea
            id="store-answer"
            label="Your answer"
            value={body}
            onChange={setBody}
            max={MAX}
            rows={5}
            placeholder="Answer as the store. No links or contact details."
            hint="Labelled “From the store”"
          />
          {existing ? (
            <Callout>Buyers see &ldquo;Edited&rdquo; next to your answer.</Callout>
          ) : (
            <p className="text-[12px] text-[var(--text-secondary)]">Store answers can&rsquo;t be picked as Best Answer and don&rsquo;t earn.</p>
          )}
          {error ? (
            <p role="alert" className="text-[12px] text-[var(--accent-danger)]">
              {error}
            </p>
          ) : null}
        </div>
        <div className={`flex items-center gap-3 border-t border-[var(--border-subtle)] px-6 py-4 ${existing ? "" : "justify-end"}`}>
          <button type="button" onClick={onClose} className="h-9 rounded-full border border-[var(--text-primary)] px-4 text-[12px]">
            Cancel
          </button>
          <button
            type="button"
            disabled={!body.trim() || countState(body, MAX).over || unchanged || busy}
            onClick={() => setConfirming(true)}
            className="h-9 rounded-full bg-[var(--accent-primary)] px-4 text-[12px] text-white disabled:opacity-50"
          >
            {existing ? "Save changes" : "Post answer"}
          </button>
        </div>
      </AdminModal>
      {/* Figma Confirm/Store/PostAnswer 8202:22661 and SaveAnswer 8202:22737. */}
      <ConfirmDialog
        open={confirming}
        title={existing ? "Save your edit?" : "Post your answer?"}
        confirmLabel={existing ? "Save changes" : "Post answer"}
        busyLabel={existing ? "Saving…" : "Posting…"}
        busy={busy}
        error={error}
        onConfirm={() => void post()}
        onClose={() => setConfirming(false)}
      >
        {existing ? (
          <>
            <p>Your new answer replaces the old one.</p>
            <p>Buyers see &ldquo;Edited&rdquo; next to it.</p>
          </>
        ) : (
          <>
            <p>It shows on the question as &ldquo;From the store&rdquo;.</p>
            <p>
              {asker.split(" ")[0]}
              {question.followers ? ` and ${question.followers} follower${question.followers === 1 ? "" : "s"} are` : " is"} notified.
            </p>
            <p>You can edit it later.</p>
          </>
        )}
      </ConfirmDialog>
    </>
  );
}
