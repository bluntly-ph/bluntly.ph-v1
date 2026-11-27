"use client";

import { useRouter } from "next/navigation";
import { useId, useRef, useState } from "react";
import { ArrowRight, ArrowsDownUp, Check, Equals, QuestionMark, X } from "@phosphor-icons/react/dist/ssr";
import type { Icon } from "@phosphor-icons/react";

import {
  BluntlyTextarea,
  CHIP_SHELL,
  CON_SUGGESTIONS,
  CrowdBand,
  PRO_SUGGESTIONS,
  PhrasePicker,
  ProductPhotoCard,
  RatingStepDecor,
  STAR_ARC,
} from "@/app/reviews/new/WriteReviewForm";
import { ComposerGrid, ComposerHeader } from "@/components/reviews/ComposerHeader";
import {
  COMPOSER_ACTION_BUTTON,
  ComposerActions,
  ComposerLayout,
  ComposerSteps,
  type ComposerStep,
} from "@/components/reviews/ComposerLayout";
import { LatestStats } from "@/components/reviews/LatestStats";
import { DONE_CARDS, TiltedRatingCards } from "@/components/reviews/TiltedRatingCards";
import { MascotPrompt } from "@/components/reviews/MascotPrompt";
import type { PanelUser } from "@/components/site/ProfileNavPanel";
import { ReviewQuoteCard } from "@/components/reviews/ReviewQuoteCard";
import { Button } from "@/components/ui/Button";
import { relativeTime } from "@/lib/relative-time";
import { StarRatingInput } from "@/components/ui/StarRatingInput";

import {
  EMPTY_DRAFT,
  EXPECTATIONS,
  FIT_CHOICES,
  FIT_DEPENDS,
  fitDetailRemaining,
  USAGE,
  VERDICT_CHOICES,
  answerPayload,
  type AnswerDraft,
} from "./answer-flow-model";
import type { QuestionRequirement } from "./ask-question-model";
import {
  ANSWER_STEPS,
  answerStepBlocker,
  firstUnmetStep,
  stepForServerParts,
  stepRequirementNote,
} from "./structured-question-model";

/**
 * Answer a question, built to Figma "Answer Page - Step 1..7" and "All done"
 * (7573:8215 … 7573:9158; meeting 2026-10-02, 1:04-2:20: "very similar to the
 * review flow"). It reuses the review composer's own pieces — the header and
 * progress line, the crowd band, the "Write it bluntly" field, the pros / cons
 * chips, the rating stars and the photo card — and posts once, at the end, to
 * POST /questions/{id}/answers with the structured parts.
 *
 * Structured answers (owner, 2026-10-05; structured-question-model and
 * docs/STRUCTURED_QUESTIONS_FIGMA_SPEC.md): the words and the RATING are
 * always required; each specific the asker requested ("Looking for: …") makes
 * its step required; every other step can be passed by Continue without a
 * choice, and the photo keeps the frame's skip. Posting re-checks every
 * required step and returns to the first one left unmet.
 */

/**
 * How much of the bar each step fills, as Screen/Answer/Step 1…7 draw it
 * (39, 117, 156, 234, 273, 351 and 390 of 390px); Done draws the bare track.
 */
const ANSWER_PROGRESS = [0.1, 0.3, 0.4, 0.6, 0.7, 0.9, 1];

const STEPS = [
  { label: "Your answer", title: "Straight to the point", blurb: null },
  { label: "Experience", title: "Been there, used that", blurb: "Tell them what it’s actually like to own it." },
  { label: "Pros and cons", title: "The good, the bad", blurb: "Tap what applies. It helps them see the full picture." },
  { label: "Verdict", title: "Your verdict", blurb: "Your unfiltered words. Make it count." },
  { label: "Is it for them?", title: "Is it for them?", blurb: "Read their situation. Does this product fit it?" },
  { label: "Rating", title: "Rating time", blurb: "Last one! How would you rate it overall?" },
  { label: "Photo", title: "Show, don’t tell", blurb: "A photo of your own unit backs up your answer. Optional, but buyers trust it more." },
] as const;

const VERDICT_ICON: Record<string, { Icon: Icon; color: string }> = {
  yes: { Icon: Check, color: "var(--accent-success)" },
  on_sale: { Icon: Equals, color: "var(--base-black)" },
  other_variant: { Icon: ArrowsDownUp, color: "var(--base-black)" },
  no: { Icon: X, color: "var(--accent-danger)" },
};
const FIT_ICON: Icon[] = [Check, Equals, X];
const FIT_COLOR = ["var(--accent-success)", "var(--base-black)", "var(--accent-danger)"];

function Choice({ selected, onClick, Icon, color, label }: { selected: boolean; onClick: () => void; Icon: Icon; color: string; label: string }) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={selected}
      className="flex h-[53px] w-full cursor-pointer items-center gap-3 rounded-[16px] bg-[var(--surface-card)] px-4 text-left shadow-[var(--shadow-card)] focus-visible:outline focus-visible:outline-2 focus-visible:outline-[var(--accent-primary)]"
      style={selected ? { boxShadow: `var(--shadow-card), inset 0 0 0 2px var(--accent-primary)` } : undefined}
    >
      <Icon size={20} weight="bold" aria-hidden className="shrink-0" style={{ color }} />
      <span className="text-[14px] leading-none" style={{ color: selected ? "var(--accent-primary)" : "var(--text-primary)" }}>
        {label}
      </span>
    </button>
  );
}

/**
 * Steps 4.1 / 5.1 (7573:8678, 7573:8753): once picked, the list folds to the
 * chosen row — white, a 1px brand border, radius 16, 53 high — with "Change"
 * (14px, 30% ink) at its right to bring the list back.
 */
function ChosenRow({ Icon, color, label, onChange }: { Icon: Icon; color: string; label: string; onChange: () => void }) {
  return (
    <div className="flex h-[53px] w-full items-center gap-3 rounded-[16px] border border-[rgba(239,88,33,0.8)] bg-[var(--surface-card)] px-4">
      <Icon size={20} weight="bold" aria-hidden className="shrink-0" style={{ color }} />
      <span className="min-w-0 flex-1 truncate text-[14px] leading-[20px] text-[var(--text-primary)]">{label}</span>
      <button
        type="button"
        onClick={onChange}
        aria-label={`Change: ${label}`}
        className="shrink-0 cursor-pointer text-[14px] leading-[20px] text-[rgba(32,32,32,0.3)] hover:text-[var(--text-primary)] focus-visible:outline focus-visible:outline-2 focus-visible:outline-[var(--accent-primary)]"
      >
        Change
      </button>
    </div>
  );
}

/**
 * The text card under a folded choice: Step 4.1's "Why? (optional)" and Step
 * 5.1's "Tell them what it depends on..." — 358 × 231 white, radius 16, the
 * card shadow, 14px text. With a minimum (5.1 only), "N characters remaining"
 * sits in 10px Light under its right edge until the text is long enough; the
 * optional Why has no counter (as drawn).
 */
function ReasonField({
  label,
  placeholder,
  value,
  onChange,
  remaining = null,
}: {
  label: string;
  placeholder: string;
  value: string;
  onChange: (next: string) => void;
  remaining?: number | null;
}) {
  const id = useId();
  return (
    <div className="mt-3">
      <label htmlFor={id} className="sr-only">
        {label}
      </label>
      <textarea
        id={id}
        value={value}
        onChange={(e) => onChange(e.target.value.slice(0, 900))}
        placeholder={placeholder}
        className="own-focus field-sizing-content block min-h-[231px] w-full resize-none rounded-[16px] bg-[var(--surface-card)] px-4 py-4 text-[14px] leading-[20px] text-[var(--text-primary)] shadow-[var(--shadow-card)] outline-none [overflow-wrap:anywhere] placeholder:text-[rgba(32,32,32,0.3)] focus-visible:shadow-[var(--shadow-card),inset_0_0_0_1px_var(--accent-primary)]"
      />
      {remaining !== null ? (
        <p aria-live="polite" className="mt-1 h-[14px] text-right text-[10px] font-light leading-[14px] text-[var(--text-primary)]">
          {remaining > 0 ? `${remaining} characters remaining` : ""}
        </p>
      ) : null}
    </div>
  );
}

function Chip({ selected, onClick, children }: { selected: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={selected}
      className={`${CHIP_SHELL} cursor-pointer focus-visible:outline focus-visible:outline-2 focus-visible:outline-[var(--accent-primary)] ${selected ? "text-[var(--accent-primary)] ring-1 ring-inset ring-[var(--accent-primary)]" : "text-[var(--text-primary)]"}`}
    >
      {children}
    </button>
  );
}

/**
 * The folded steps' marks, frame x/y less the 16px gutter and the body's top
 * (232); those on the right half are anchored right so a 320px phone keeps
 * them inside the column.
 */
const FOLDED_MARKS: readonly React.CSSProperties[] = [
  { right: 60, top: -20 },
  { right: 8, top: 79 },
  { left: 73, top: -1 },
  { left: 16, top: 47 },
  { left: 179, top: 110 },
];

function ChoiceCard({ label, prompt, children }: { label: string; prompt: string; children: React.ReactNode }) {
  return (
    <fieldset className="rounded-[12px] bg-[var(--surface-app)] px-5 pb-7 pt-5 shadow-[var(--shadow-card)]">
      <legend className="sr-only">{label}</legend>
      <p aria-hidden className="text-[12px] leading-none text-[var(--chart-honesty-fund)]">{label}</p>
      <p className="mt-[5px] text-[12px] font-light leading-none text-[rgba(32,32,32,0.7)]">{prompt}</p>
      <div className="mt-[14px] flex flex-wrap gap-x-2 gap-y-3">{children}</div>
    </fieldset>
  );
}

export function AnswerFlow({
  user,
  questionId,
  question,
  context,
  requested = [],
  asker = null,
  askedAt = null,
  upvotes = 0,
  replies = 0,
}: {
  user: PanelUser;
  /** Who asked, for the Done card (Screen/Answer/Done 7573:9158 quotes the question). */
  asker?: { name: string; levelName: string | null; stage: number | null; score: string | null; avatarUrl?: string | null } | null;
  askedAt?: string | null;
  upvotes?: number;
  replies?: number;
  questionId: string;
  /** The specifics the asker requested (the question's "Looking for:" line). */
  requested?: readonly QuestionRequirement[];
  /** The question as asked, shown in the mascot's bubble. */
  question: string;
  /** The asker's situation, quoted under the title (the question body past its first line). */
  context: string | null;
}) {
  const router = useRouter();
  const [step, setStep] = useState(0);
  const [d, setD] = useState<AnswerDraft>(EMPTY_DRAFT);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);
  /** "Change" on a folded verdict / fit row brings the list back (4.1, 5.1). */
  const [picking, setPicking] = useState(false);
  const goTo = (i: number) => {
    setPicking(false);
    setStep(i);
  };
  const inFlight = useRef(false);
  const patch = (c: Partial<AnswerDraft>) => {
    setD((prev) => ({ ...prev, ...c }));
    setError(null);
  };
  const isLast = step === STEPS.length - 1;
  const blocker = answerStepBlocker(ANSWER_STEPS[step], d, requested);

  async function submit(override: Partial<AnswerDraft> = {}) {
    if (busy || inFlight.current) return;
    // Every required step, not only this one: Skip on the photo posts too.
    const unmet = firstUnmetStep({ ...d, ...override }, requested);
    if (unmet) {
      goTo(unmet.index);
      setError(unmet.reason);
      return;
    }
    inFlight.current = true;
    setBusy(true);
    setError(null);
    try {
      const res = await fetch(`/api/bff/api/v1/questions/${questionId}/answers`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(answerPayload({ ...d, ...override })),
      });
      if (!res.ok) {
        const p = (await res.json().catch(() => ({}))) as { detail?: unknown; parts?: unknown };
        // A part the server says is missing (answer_rating_required /
        // answer_part_required): back to its step, with the server's words.
        const back = stepForServerParts(p.parts);
        if (back !== null) goTo(back);
        setError(typeof p.detail === "string" ? p.detail : "Couldn't post your answer. Try again.");
        return;
      }
      setDone(true);
    } catch {
      setError("Couldn't reach the server. Try again.");
    } finally {
      setBusy(false);
      inFlight.current = false;
    }
  }

  const back = () => (done ? router.push(`/questions/${questionId}`) : step > 0 ? goTo(step - 1) : router.push(`/questions/${questionId}`));
  const steps: ComposerStep[] = STEPS.map((s, i) => ({
    label: s.label,
    number: i + 1,
    state: done || i < step ? "done" : i === step ? "current" : "todo",
    onSelect: !done && i < step ? () => goTo(i) : undefined,
  }));

  return (
    <>
      <ComposerHeader user={user} title="Answer a question" onBack={back} backLabel="Back" progress={done ? 0 : ANSWER_PROGRESS[step]} />
      <ComposerGrid />
      <ComposerLayout
        aside={
          <ComposerSteps
            flow="Answer a question"
            subjectLabel="Answering"
            subject={question}
            steps={steps}
            note={done ? "The asker was notified." : "Your words and a rating are required, and anything the asker asked for. Every other step can be skipped."}
          />
        }
      >
        {done ? (
          <div className="relative pb-32">
            {/* FIGMA Done (7573:9158): the tilted rating cards from the bottom
                corners, as on the Ask done screen; phones only. */}
            <TiltedRatingCards cards={DONE_CARDS} className="fixed inset-x-0 bottom-0 z-0 hidden h-[340px] max-sm:block" />
            <div className="relative z-10">
              <p className="text-[12px] leading-none">All done!</p>
              <h1 className="mt-2.5 text-[20px] font-medium leading-none text-[var(--accent-primary)]">Answer posted!</h1>
              <p className="mt-[7px] text-[12px] font-light leading-[18px] text-[rgba(32,32,32,0.7)]">
                Thanks for being blunt. The asker gets notified right away.
              </p>
              <p className="ml-[3px] mt-[50px] text-[12px] leading-none text-[var(--chart-honesty-fund)]">You answered this question:</p>
              {/* FIGMA Done: the asker's Author row (their photo, else their
                  initial), the question in quotes, its votes and replies. */}
              <ReviewQuoteCard
                className="mt-[21px]"
                username={asker?.name ?? "Former member"}
                avatarUrl={asker?.avatarUrl ?? null}
                age={askedAt ? relativeTime(askedAt) : ""}
                levelName={asker?.levelName ?? null}
                stage={asker?.stage ?? null}
                score={asker?.score ?? null}
                title={question}
                upvotes={upvotes}
                comments={replies}
              />
              <LatestStats className="mt-[83px] [&>p]:ml-[11px] md:mt-8 md:[&>dl]:justify-start" />
            </div>
            <ComposerActions>
              <Button href={`/questions/${questionId}`} fullWidth className={COMPOSER_ACTION_BUTTON}>
                View the question
                <ArrowRight size={20} aria-hidden="true" />
              </Button>
            </ComposerActions>
          </div>
        ) : (
          <div className="pb-32 md:pb-0">
            <p className="text-[12px] leading-none text-[var(--text-primary)]" data-testid="answer-step-counter">
              Step {step + 1} out of {STEPS.length}
              <span className="text-[var(--text-secondary)]"> · {stepRequirementNote(ANSWER_STEPS[step], requested)}</span>
            </p>
            <h1 className="mt-2.5 text-[20px] font-medium leading-none text-[var(--accent-primary)]">
              {/* 4.1: the title gains its "!" once a verdict is chosen. */}
              {step === 3 && d.verdict ? "Your verdict!" : STEPS[step].title}
            </h1>
            {step === 0 && context ? (
              <p className="mt-[7px] text-[12px] font-light italic leading-[18px] text-[rgba(32,32,32,0.7)]">&ldquo;{context}&rdquo;</p>
            ) : STEPS[step].blurb ? (
              <p className="mt-[7px] text-[12px] font-light leading-[18px] text-[rgba(32,32,32,0.7)]">{STEPS[step].blurb}</p>
            ) : null}

            {/* FIGMA: the step's body starts 16px under the quote (Step 1), 34px
                under the line for the mascot steps (4, 5), 46px for the card
                steps (2, 3, 7); the rating step's stars sit 154px under it
                (6), as in the review flow, whose clouds it shares. */}
            <div className={step === 0 ? "mt-4" : step === 5 ? "" : step === 1 || step === 2 || step === 6 ? "mt-[46px]" : "mt-[34px]"}>
              {step === 0 ? (
                <div className="relative isolate">
                  <CrowdBand />
                  <MascotPrompt variant="simple" className="pt-[62px]">
                    {question}
                  </MascotPrompt>
                  <BluntlyTextarea
                    label="Your answer"
                    value={d.text}
                    onChange={(text) => patch({ text: text.slice(0, 4000) })}
                    satisfied="That's a blunt answer!"
                    autoFocus
                    className="mt-8"
                  />
                </div>
              ) : null}

              {step === 1 ? (
                <div className="flex flex-col gap-4">
                  <ChoiceCard label="Usage" prompt="How long have you used it?">
                    {USAGE.map((u) => (
                      <Chip key={u} selected={d.usage === u} onClick={() => patch({ usage: d.usage === u ? null : u })}>
                        {u}
                      </Chip>
                    ))}
                  </ChoiceCard>
                  <ChoiceCard label="Expectations" prompt="Compared to what you expected?">
                    {EXPECTATIONS.map((e) => (
                      <Chip key={e} selected={d.expectation === e} onClick={() => patch({ expectation: d.expectation === e ? null : e })}>
                        {e}
                      </Chip>
                    ))}
                    <input
                      value={d.note}
                      onChange={(e) => patch({ note: e.target.value.slice(0, 300) })}
                      placeholder="Anything they should know? (optional)"
                      aria-label="Anything they should know? (optional)"
                      className={`${CHIP_SHELL} own-focus w-full text-ellipsis text-[var(--text-primary)] outline-none placeholder:text-[rgba(32,32,32,0.3)] focus-visible:ring-1 focus-visible:ring-inset focus-visible:ring-[var(--accent-primary)]`}
                    />
                  </ChoiceCard>
                </div>
              ) : null}

              {step === 2 ? (
                <div className="grid gap-7 sm:grid-cols-2">
                  <PhrasePicker tone="pro" label="Pros" prompt="What's so great about this product?" suggestions={PRO_SUGGESTIONS} addLabel="Add a pro…" value={d.pros} onChange={(pros) => patch({ pros })} />
                  <PhrasePicker tone="con" label="Cons" prompt="What are the downsides worth mentioning?" suggestions={CON_SUGGESTIONS} addLabel="Add a con…" value={d.cons} onChange={(cons) => patch({ cons })} />
                </div>
              ) : null}

              {step === 3 || step === 4 ? (
                <div className="relative isolate">
                  {(step === 3 ? d.verdict : d.fit) && !picking ? (
                    // 4.1 / 5.1 (7573:8678, 7573:8753): five marks once a choice is folded.
                    FOLDED_MARKS.map((at, i) => (
                      <QuestionMark key={i} size={32} weight="thin" aria-hidden="true" className="pointer-events-none absolute -z-10 text-[var(--line-hairline-10)]" style={at} />
                    ))
                  ) : (
                    <>
                      <QuestionMark size={32} weight="thin" aria-hidden="true" className="pointer-events-none absolute left-[26px] top-[53px] -z-10 text-[var(--line-hairline-10)]" />
                      <QuestionMark size={32} weight="thin" aria-hidden="true" className="pointer-events-none absolute right-[16px] top-[69px] -z-10 text-[var(--line-hairline-10)]" />
                    </>
                  )}
                  <MascotPrompt className="mb-8" variant="simple">
                    {step === 3 ? "Would you recommend this to them?" : "Is this right for them?"}
                  </MascotPrompt>
                  {step === 3 && d.verdict && !picking ? (
                    <>
                      <ChosenRow
                        Icon={VERDICT_ICON[d.verdict].Icon}
                        color={VERDICT_ICON[d.verdict].color}
                        label={VERDICT_CHOICES.find((v) => v.value === d.verdict)?.label ?? ""}
                        onChange={() => setPicking(true)}
                      />
                      <ReasonField
                        label="Why? (optional)"
                        placeholder="Why? (optional)"
                        value={d.verdictReason}
                        onChange={(verdictReason) => patch({ verdictReason })}
                      />
                    </>
                  ) : step === 4 && d.fit && !picking ? (
                    <>
                      <ChosenRow
                        Icon={FIT_ICON[FIT_CHOICES.indexOf(d.fit as (typeof FIT_CHOICES)[number])] ?? Equals}
                        color={FIT_COLOR[FIT_CHOICES.indexOf(d.fit as (typeof FIT_CHOICES)[number])] ?? "var(--base-black)"}
                        label={d.fit}
                        onChange={() => setPicking(true)}
                      />
                      {d.fit === FIT_DEPENDS ? (
                        <ReasonField
                          label="Tell them what it depends on"
                          placeholder="Tell them what it depends on..."
                          value={d.fitDetail}
                          onChange={(fitDetail) => patch({ fitDetail })}
                          remaining={fitDetailRemaining(d.fitDetail)}
                        />
                      ) : null}
                    </>
                  ) : (
                    <div className="flex flex-col gap-3">
                      {step === 3
                        ? VERDICT_CHOICES.map((v) => (
                            <Choice
                              key={v.value}
                              selected={d.verdict === v.value}
                              onClick={() => {
                                patch({ verdict: v.value });
                                setPicking(false);
                              }}
                              Icon={VERDICT_ICON[v.value].Icon}
                              color={VERDICT_ICON[v.value].color}
                              label={v.label}
                            />
                          ))
                        : FIT_CHOICES.map((f, i) => (
                            <Choice
                              key={f}
                              selected={d.fit === f}
                              onClick={() => {
                                patch({ fit: f });
                                setPicking(false);
                              }}
                              Icon={FIT_ICON[i]}
                              color={FIT_COLOR[i]}
                              label={f}
                            />
                          ))}
                    </div>
                  )}
                </div>
              ) : null}

              {step === 5 ? (
                <div className="relative isolate pt-[154px] md:pb-10 md:pt-0">
                  <RatingStepDecor />
                  <StarRatingInput label="Star rating" value={d.rating} onChange={(rating) => patch({ rating })} size={52} gap={8} arc={STAR_ARC} />
                </div>
              ) : null}

              {step === 6 ? (
                <ProductPhotoCard
                  urls={d.photoUrl ? [d.photoUrl] : []}
                  onChange={(urls) => patch({ photoUrl: urls[0] ?? null })}
                  max={1}
                  onSkip={() => {
                    patch({ photoUrl: null });
                    void submit({ photoUrl: null });
                  }}
                  receiptKey={null}
                  skipLabel="Skip – post without a photo"
                />
              ) : null}
            </div>

            <ComposerActions hint={blocker} error={error}>
              <Button
                type="button"
                onClick={isLast ? () => void submit() : () => goTo(step + 1)}
                disabled={Boolean(blocker) || busy}
                fullWidth
                className={COMPOSER_ACTION_BUTTON}
              >
                {busy ? "Posting…" : isLast ? "Post answer" : "Continue"}
                {busy ? null : <ArrowRight size={20} aria-hidden="true" />}
              </Button>
            </ComposerActions>
            <p role="status" className="sr-only">
              {blocker ?? ""}
            </p>
          </div>
        )}
      </ComposerLayout>
    </>
  );
}
