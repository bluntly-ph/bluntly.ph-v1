"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { CaretDown, ChatCircleText, WarningCircle } from "@phosphor-icons/react";

import { AdminModal } from "@/components/admin/AdminModal";
import { ConfirmDialog } from "@/components/admin/ConfirmDialog";
import { Chip } from "@/components/console/Chip";
import { countState } from "@/components/console/counted-model";
import { CountedTextarea } from "@/components/console/CountedTextarea";
import { MENU, usePopover } from "@/components/console/popover";

import { AuthorPanel, OriginalityPanel } from "./InvestigationTabs";
import { Timeline, VotersPanel } from "./ReviewInvestigation";

const NOTE_MAX = 500;

/**
 * Overlay/Answer/Investigate (Figma Summary 8129:18013, Votes 8129:18282 /
 * 8237:26795, Voters 8129:18588, Originality 8129:19014, Author 8129:19219;
 * Menu/Answer/Moderate 8123:18065, Menu/Answer/Reward 8123:18086), opened from
 * the Answers queue. Read from GET /admin/answers/{id}/investigation.
 *
 * What answers do not have is said, not drawn: no place per vote, no network
 * fingerprint (the only flag is the voting circle), no gate and no reward.
 * In Moderate, "Unmark best answer" works (audited, with a note); "Take down
 * answer" and "Remove flagged votes" need decisions the owner has not made,
 * and the Reward decision has nothing to decide, so those are shown inert
 * with the reason.
 */

type Data = import("@/lib/api-types").components["schemas"]["AnswerInvestigationOut"];
type Tab = "summary" | "votes" | "voters" | "originality" | "author";

function useAnswer(id: string, version: number) {
  const [state, setState] = useState<{ key: string; data: Data | null; failed: boolean }>({ key: "", data: null, failed: false });
  const key = `${id}:${version}`;
  useEffect(() => {
    let live = true;
    fetch(`/api/bff/api/v1/admin/answers/${id}/investigation`, { cache: "no-store" })
      .then((r) => (r.ok ? (r.json() as Promise<Data>) : Promise.reject(new Error(String(r.status)))))
      .then((data) => live && setState({ key, data, failed: false }))
      .catch(() => live && setState({ key, data: null, failed: true }));
    return () => {
      live = false;
    };
  }, [id, key]);
  return state.key === key ? state : { data: null, failed: false };
}

export function InvestigateAnswerButton({ answerId }: { answerId: string }) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button type="button" onClick={() => setOpen(true)} className="mt-3 h-8 rounded-full border border-[var(--text-primary)] px-3 text-[12px]">
        Investigate this answer
      </button>
      {open ? <AnswerInvestigationModal answerId={answerId} onClose={() => setOpen(false)} /> : null}
    </>
  );
}

export function AnswerInvestigationModal({ answerId, onClose }: { answerId: string; onClose: () => void }) {
  const router = useRouter();
  const [tab, setTab] = useState<Tab>("summary");
  const [version, setVersion] = useState(0);
  const { data, failed } = useAnswer(answerId, version);
  const [unmark, setUnmark] = useState(false);
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const moderate = usePopover();
  const reward = usePopover();
  const { open: moderateOpen, setOpen: setModerateOpen, ref: moderateRef } = moderate;
  const { open: rewardOpen, setOpen: setRewardOpen, ref: rewardRef } = reward;

  async function confirmUnmark() {
    setBusy(true);
    setError(null);
    try {
      const res = await fetch(`/api/bff/api/v1/admin/answers/${answerId}/unmark-best`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ note: note.trim() }),
      });
      if (!res.ok) {
        const p = (await res.json().catch(() => ({}))) as { detail?: unknown };
        setError(typeof p.detail === "string" ? p.detail : "It wasn’t unmarked. Try again.");
        return;
      }
      setUnmark(false);
      setNote("");
      setVersion((v) => v + 1);
      router.refresh();
    } catch {
      setError("Couldn’t reach the server.");
    } finally {
      setBusy(false);
    }
  }

  const title = data?.question ?? "Answer";
  const subtitle = data
    ? `Answer by ${data.responder}${data.about ? ` · on ${data.about}` : ""} · ${new Date(data.posted_at).toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric", timeZone: "Asia/Manila" })} · ID ${data.answer_id.slice(0, 8)}`
    : undefined;
  const signals = data ? [data.flagged > 0, data.first_10_min > Math.max(3, (data.typical_first_10_min ?? 0) * 3)].filter(Boolean).length : 0;
  const ITEM = "flex w-full items-center rounded-[10px] px-3 py-[9px] text-left text-[14px] hover:bg-[var(--surface-app)] disabled:cursor-not-allowed disabled:text-[var(--text-muted)] disabled:hover:bg-transparent";

  return (
    <AdminModal title={title} subtitle={subtitle} width={1040} onClose={onClose}>
      <div className="flex flex-wrap items-center gap-3 border-b border-[var(--border-subtle)] px-6 py-3">
        <div role="tablist" aria-label="Investigate" className="flex flex-wrap gap-[2px] rounded-[10px] bg-[var(--surface-app)] p-[3px]">
          {(
            [
              ["summary", "Summary", null],
              ["votes", "Votes", data ? String(data.votes_total) : null],
              ["voters", "Voters", data ? `${data.flagged} flagged` : null],
              ["originality", "Originality", null],
              ["author", "Author", null],
            ] as const
          ).map(([key, label, count]) => (
            <button
              key={key}
              type="button"
              role="tab"
              aria-selected={tab === key}
              onClick={() => setTab(key)}
              className={`flex items-center gap-[6px] rounded-[8px] px-3 py-[5px] leading-none ${tab === key ? "bg-[var(--surface-card)] shadow-[var(--shadow-segment)]" : "text-[var(--text-secondary)]"}`}
            >
              <span className="text-[14px] font-medium">{label}</span>
              {count !== null ? <span className="text-[12px] text-[var(--text-secondary)]">{count}</span> : null}
            </button>
          ))}
        </div>
        {data?.is_best ? <Chip tone="success">Best answer</Chip> : null}
        <span className="flex-1" />
        {signals > 0 ? (
          <span className="inline-flex items-center gap-1 rounded-full bg-[var(--status-high-bg)] px-3 py-1 text-[12px] font-medium text-[var(--accent-danger)]">
            <WarningCircle size={14} weight="fill" aria-hidden /> {signals} {signals === 1 ? "signal needs" : "signals need"} a look
          </span>
        ) : null}
      </div>

      <div className="min-h-[360px]" data-testid="answer-investigation">
        {!data ? (
          <p role={failed ? "alert" : "status"} className="p-6 text-[14px] text-[var(--text-secondary)]">
            {failed ? "The answer could not be loaded." : "Loading the answer…"}
          </p>
        ) : tab === "summary" ? (
          <Summary d={data} />
        ) : tab === "votes" ? (
          <AnswerVotes d={data} />
        ) : tab === "voters" ? (
          <VotersPanel data={data} failed={false} author={data.responder} noun="answers" />
        ) : tab === "originality" ? (
          <OriginalityPanel kind="answers" id={answerId} />
        ) : data.responder_id ? (
          <AuthorPanel kind="answers" id={answerId} />
        ) : (
          <p className="p-6 text-[14px] text-[var(--text-secondary)]">The author&apos;s account no longer exists.</p>
        )}
      </div>

      <div className="flex flex-wrap items-center gap-3 border-t border-[var(--border-subtle)] px-6 py-4">
        {data ? (
          <Link href={`/questions/${data.question_id}`} target="_blank" className="text-[12px] text-[var(--accent-primary)] hover:underline">
            Open on site
          </Link>
        ) : null}
        <div ref={moderateRef} className="relative">
          <button type="button" aria-haspopup="menu" aria-expanded={moderateOpen} onClick={() => setModerateOpen(!moderateOpen)} className="flex h-9 items-center gap-2 rounded-full border border-[var(--text-primary)] px-4 text-[12px]">
            Moderate <CaretDown size={12} aria-hidden />
          </button>
          {moderateOpen ? (
            <div role="menu" aria-label="Moderate" className={`${MENU} bottom-[calc(100%+6px)] left-0 right-auto top-auto w-[260px] p-[6px]`}>
              <button type="button" role="menuitem" disabled title="Removing votes is an owner decision; signals never act on their own." className={ITEM}>
                Remove flagged votes ({data?.flagged ?? 0})
              </button>
              <button
                type="button"
                role="menuitem"
                disabled={!data?.is_best}
                title={data?.is_best ? undefined : "This answer isn’t the best answer."}
                onClick={() => {
                  setModerateOpen(false);
                  setUnmark(true);
                }}
                className={ITEM}
              >
                Unmark best answer
              </button>
              <button type="button" role="menuitem" disabled title="Answers can’t be taken down yet: it needs an owner decision." className={ITEM}>
                Take down answer
              </button>
              <p className="px-3 pb-1 pt-2 text-[11px] text-[var(--text-secondary)]">Removing votes and taking an answer down need an owner decision before they exist.</p>
            </div>
          ) : null}
        </div>
        <div ref={rewardRef} className="relative">
          <button type="button" aria-haspopup="menu" aria-expanded={rewardOpen} onClick={() => setRewardOpen(!rewardOpen)} className="flex h-9 items-center gap-2 rounded-full bg-[var(--accent-primary)] px-4 text-[12px] text-white">
            Reward decision <CaretDown size={12} aria-hidden />
          </button>
          {rewardOpen ? (
            <div role="menu" aria-label="Reward decision" className={`${MENU} bottom-[calc(100%+6px)] left-0 right-auto top-auto w-[260px] p-[6px]`}>
              <button type="button" role="menuitem" disabled className={ITEM}>
                Approve reward
              </button>
              <button type="button" role="menuitem" disabled className={ITEM}>
                Reject reward
              </button>
              <p className="px-3 pb-1 pt-2 text-[11px] text-[var(--text-secondary)]">Answers earn no reward on Bluntly yet, so there is nothing to decide.</p>
            </div>
          ) : null}
        </div>
      </div>

      <ConfirmDialog
        open={unmark}
        title="Unmark the best answer?"
        confirmLabel="Unmark"
        busyLabel="Unmarking…"
        busy={busy}
        disabled={note.trim().length < 3 || countState(note, NOTE_MAX).over}
        error={error}
        onConfirm={() => void confirmUnmark()}
        onClose={() => setUnmark(false)}
      >
        <p>The question goes back to having no best answer, and the asker can pick again. Recorded in the Activity log with your note.</p>
        <CountedTextarea id="unmark-note" label="Why (the team sees this)" value={note} onChange={setNote} max={NOTE_MAX} min={3} rows={2} />
      </ConfirmDialog>
    </AdminModal>
  );
}

function Summary({ d }: { d: Data }) {
  const delta = d.score_without_flagged - d.score_all;
  return (
    <div className="grid gap-4 p-6 md:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
      <section className="flex flex-col gap-3 rounded-[16px] border border-[var(--border-subtle)] p-4">
        <p className="text-[12px] text-[var(--text-secondary)]">Question{d.asker ? ` by ${d.asker}` : ""}</p>
        <p className="text-[14px] font-medium">{d.question}</p>
        <div className="rounded-[12px] bg-[var(--surface-app)] p-3">
          <p className="flex items-center gap-2 text-[12px] text-[var(--text-secondary)]">
            <ChatCircleText size={14} aria-hidden /> {d.responder} · {d.responder_level ?? `Stage ${d.responder_stage}`}
            {d.is_seller_answer ? " · the store" : ""}
          </p>
          <p className="mt-2 whitespace-pre-line text-[14px]">{d.body}</p>
        </div>
        <dl className="grid grid-cols-2 gap-3 text-[13px]">
          <div>
            <dt className="text-[12px] text-[var(--text-secondary)]">Posted</dt>
            <dd suppressHydrationWarning>{new Date(d.posted_at).toLocaleString("en-GB", { day: "numeric", month: "short", hour: "numeric", minute: "2-digit", timeZone: "Asia/Manila" })}</dd>
          </div>
          <div>
            <dt className="text-[12px] text-[var(--text-secondary)]">Best answer</dt>
            <dd>{d.is_best ? (d.picked_by_asker ? "Picked by the asker" : "Marked, picker not recorded") : "No"}</dd>
          </div>
        </dl>
      </section>
      <section className="flex flex-col gap-3 rounded-[16px] border border-[var(--border-subtle)] p-4">
        <h3 className="text-[14px] font-medium">What we found</h3>
        <Finding bad={d.flagged > 0} title={d.flagged > 0 ? `${d.flagged} ${d.flagged === 1 ? "vote" : "votes"} from the voting circle` : "No voting circle"}>
          {d.flagged > 0 ? "Voters who up-voted at least 80% of this person’s answers." : "No voter up-voted most of this person’s answers."}
        </Finding>
        <Finding bad={d.first_10_min > Math.max(3, (d.typical_first_10_min ?? 0) * 3)} title={`${d.first_10_min} ${d.first_10_min === 1 ? "vote" : "votes"} in the first 10 minutes`}>
          {d.typical_first_10_min != null ? `Typical for answers is ${Math.round(d.typical_first_10_min)}.` : "No typical figure yet."}
        </Finding>
        <Finding bad={d.flagged > 0 && delta < 0} title="Helpful score">
          {d.score_all.toFixed(2)} with every vote{d.flagged > 0 ? `, ${d.score_without_flagged.toFixed(2)} without the ${d.flagged} flagged` : ""}. Answers are ordered by it; there is no gate.
        </Finding>
      </section>
    </div>
  );
}

function Finding({ bad, title, children }: { bad: boolean; title: string; children: React.ReactNode }) {
  return (
    <div className="flex items-start gap-2 border-t border-[var(--border-subtle)] pt-3 first-of-type:border-t-0 first-of-type:pt-0">
      <span className={`mt-[5px] size-2 shrink-0 rounded-full ${bad ? "bg-[var(--accent-danger)]" : "bg-[var(--accent-success)]"}`} aria-hidden />
      <span className="flex flex-col gap-1">
        <span className="text-[14px] font-medium">{title}</span>
        <span className="text-[12px] text-[var(--text-secondary)]">{children}</span>
      </span>
    </div>
  );
}

function AnswerVotes({ d }: { d: Data }) {
  const delta = d.score_without_flagged - d.score_all;
  return (
    <div className="flex flex-col gap-4 p-6" data-testid="answer-votes">
      <section className="rounded-[16px] border border-[var(--border-subtle)] p-4">
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <h3 className="text-[14px] font-medium">Vote timeline</h3>
          <p className="text-[12px] text-[var(--text-secondary)]">
            {d.votes_total} {d.votes_total === 1 ? "vote" : "votes"} · {d.first_10_min} in the first 10 minutes
            {d.typical_first_10_min != null ? ` · typical is ${Math.round(d.typical_first_10_min)}` : ""}
          </p>
        </div>
        {d.votes_total === 0 ? <p className="py-6 text-[13px] text-[var(--text-secondary)]">No votes yet.</p> : <Timeline voters={d.voters} />}
      </section>
      <div className="grid gap-4 md:grid-cols-2">
        <section className="rounded-[16px] border border-[var(--border-subtle)] p-4">
          <h3 className="text-[14px] font-medium">Flagged votes</h3>
          <p className={`mt-2 text-[28px] font-semibold ${d.flagged ? "text-[var(--accent-danger)]" : ""}`}>{d.flagged}</p>
          <p className="text-[12px] text-[var(--text-secondary)]">Voting circle only: answer votes keep no network fingerprint.</p>
          <div className="mt-4 flex gap-6 border-t border-[var(--border-subtle)] pt-3">
            <div>
              <p className="text-[12px] text-[var(--text-secondary)]">Helpful score</p>
              <p className="text-[20px] font-semibold text-[var(--text-secondary)]">{d.score_all.toFixed(2)}</p>
            </div>
            <div>
              <p className="text-[12px] text-[var(--text-secondary)]">Without flagged</p>
              <p className="text-[20px] font-semibold">
                {d.score_without_flagged.toFixed(2)}
                {d.flagged > 0 && delta !== 0 ? (
                  <span className="ml-2 rounded-full bg-[var(--status-high-bg)] px-2 py-[2px] text-[11px] font-medium text-[var(--accent-danger)]">
                    {delta > 0 ? "+" : "−"}
                    {Math.abs(delta).toFixed(2)}
                  </span>
                ) : null}
              </p>
            </div>
          </div>
        </section>
        <section className="rounded-[16px] border border-[var(--border-subtle)] p-4">
          <h3 className="text-[14px] font-medium">Where votes came from</h3>
          <p className="mt-2 text-[13px] text-[var(--text-secondary)]">Not recorded for answers: only reviews keep a count of first votes by place.</p>
        </section>
      </div>
    </div>
  );
}
