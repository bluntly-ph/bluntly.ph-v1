"use client";

import { useRouter } from "next/navigation";
import { useId, useState } from "react";
import { ArrowRight, Plus } from "@phosphor-icons/react/dist/ssr";

import { COMPOSER_FOCUS_RING, COMPOSER_HEADING, COMPOSER_HINT } from "@/components/reviews/composer-styles";
import { ComposerGrid, ComposerHeader } from "@/components/reviews/ComposerHeader";
import {
  COMPOSER_ACTION_BUTTON,
  ComposerActions,
  ComposerLayout,
  ComposerSteps,
  type ComposerStep,
} from "@/components/reviews/ComposerLayout";
import { CurrentlyReviewingCard } from "@/components/reviews/CurrentlyReviewingCard";
import { LatestStats } from "@/components/reviews/LatestStats";
import { ProductPicker, type PickedProduct } from "@/components/reviews/ProductPicker";
import { ReviewQuoteCard } from "@/components/reviews/ReviewQuoteCard";
import {
  DONE_CARDS,
  STAR_CORAL,
  STAR_GREEN,
  STAR_YELLOW,
  TiltedRatingCards,
  fadedStar,
  starRow,
  type TiltedCard,
} from "@/components/reviews/TiltedRatingCards";
import type { PanelUser } from "@/components/site/ProfileNavPanel";
import { Button } from "@/components/ui/Button";

import {
  MAX_QUESTION_TEXT,
  MIN_QUESTION_CHARS,
  composeQuestionBody,
  type QuestionRequirement,
} from "./ask-question-model";
import { ASKABLE_REQUIREMENTS } from "./structured-question-model";

/**
 * Ask a question (FR-5), built to the "Question Page" frames, read from Figma
 * 2026-09-15:
 *
 *   product   Step 1 (4705:14719, idle) and with results (4709:14832)
 *   question  Step 2 (4695:14599) and Step 2.3 (4742:15580, filled)
 *   done      Step 3 (4742:15979)
 *
 * The progress line is the frames' own: grey on step 1, 312 of 390px orange on
 * step 2, all green on step 3.
 *
 * INTENTIONAL PRODUCT DIFFERENCES:
 *  - "Would you like to share a photo?" is not drawn: a question has no photo
 *    in the API, so an upload here would be accepted and then dropped.
 *  - The specifics ("Experience", "Pros & Cons", …) have no field of their own
 *    either. They travel as a last "Looking for:" line of the question, which
 *    answerers read as written and the question pages show as the frame's
 *    "Requirements:" tags (ask-question-model). Future work: a column.
 *  - Step 2's pill posts the question, so it says "Submit" as the other
 *    composers' last steps do; the frame's "Continue" promises another step.
 *  - NO AUDIENCE PICKER (owner decision 2026-09-28). The frame "Question Page -
 *    Buyer or Seller" (4682:14203) asked whether the question was for other
 *    buyers or for the seller. Both may answer under the Q&A rules, so the
 *    choice decided nothing and is gone; the question's SUBJECT (this product,
 *    or a store from its page) is unchanged.
 *  - The stats are the member's real dashboard figures (see LatestStats).
 */

type Stage = "product" | "question" | "done";

// Screen/Ask: Step 1 the bare track, Step 2 312 of 390px, Step 3 (done) the bare track.
const PROGRESS: Record<Stage, number> = { product: 0, question: 312 / 390, done: 0 };

/** Step 1's cards, "Question Page - Step 1" (4705:14719), measured below the bar. */
const PRODUCT_CARDS: TiltedCard[] = [
  { x: -123, top: 325, tilt: 5, faded: true, stars: starRow(5, STAR_GREEN) },
  { x: -106, top: 271, tilt: 5, faded: true, stars: starRow(4, STAR_GREEN) },
  { x: -90, top: 216, tilt: 5, faded: true, stars: starRow(2, fadedStar(STAR_CORAL)) },
  { x: 363, bottom: -8, tilt: -5, faded: true, anchorRight: true, starsStart: true, stars: starRow(5, STAR_GREEN) },
  { x: 347, bottom: 46, tilt: -5, faded: true, anchorRight: true, starsStart: true, stars: starRow(4, STAR_GREEN) },
  { x: 330, bottom: 101, tilt: -5, faded: true, anchorRight: true, starsStart: true, stars: starRow(3, fadedStar(STAR_YELLOW)) },
];

/** Step 2's cards behind the product card (4695:14599), from the bar down. */
const QUESTION_CARDS: TiltedCard[] = [
  { x: -134, top: 73, tilt: 5, faded: true, stars: starRow(5, STAR_GREEN) },
  { x: -117, top: 19, tilt: 5, faded: true, stars: starRow(4, STAR_GREEN) },
  { x: -100, top: -36, tilt: 5, faded: true, stars: starRow(2, fadedStar(STAR_CORAL)) },
  { x: 358, top: 154, tilt: -5, faded: true, anchorRight: true, starsStart: true, stars: starRow(5, STAR_GREEN) },
  { x: 342, top: 100, tilt: -5, faded: true, anchorRight: true, starsStart: true, stars: starRow(4, STAR_GREEN) },
  { x: 325, top: 45, tilt: -5, faded: true, anchorRight: true, starsStart: true, stars: starRow(3, fadedStar(STAR_YELLOW)) },
];

export function AskQuestionForm({ user }: { user: PanelUser }) {
  const router = useRouter();
  const [stage, setStage] = useState<Stage>("product");
  const [product, setProduct] = useState<PickedProduct | null>(null);
  const [text, setText] = useState("");
  const [requirements, setRequirements] = useState<QuestionRequirement[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [postedId, setPostedId] = useState<string | null>(null);

  function go(next: Stage) {
    setError(null);
    setStage(next);
    window.scrollTo({ top: 0 });
  }

  function toggle(r: QuestionRequirement) {
    setRequirements((list) => (list.includes(r) ? list.filter((x) => x !== r) : [...list, r]));
  }

  const short = MIN_QUESTION_CHARS - text.trim().length;
  const blocker = stage === "question" && short > 0 ? `Write at least ${MIN_QUESTION_CHARS} characters.` : null;

  async function submit() {
    if (!product || blocker || busy) return;
    setBusy(true);
    setError(null);
    try {
      const res = await fetch("/api/bff/api/v1/questions", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          product_id: product.id,
          body: composeQuestionBody(text, requirements),
        }),
      });
      if (!res.ok) {
        const p = (await res.json().catch(() => ({}))) as { detail?: string };
        setError(p.detail ?? "Couldn't post your question.");
        return;
      }
      const created = (await res.json()) as { id: string };
      setPostedId(created.id);
      go("done");
    } catch {
      setError("Couldn't reach the server. Try again.");
    } finally {
      setBusy(false);
    }
  }

  const back =
    stage === "product"
      ? () => router.back()
      : stage === "question"
        ? () => go("product")
        : () => router.push(postedId ? `/questions/${postedId}` : "/questions");

  const panelSteps: ComposerStep[] = [
    {
      label: "Choose the product",
      number: 1,
      state: stage === "product" ? "current" : "done",
      onSelect: stage === "question" ? () => go("product") : undefined,
    },
    { label: "Write your question", number: 2, state: stage === "question" ? "current" : stage === "done" ? "done" : "todo" },
  ];

  return (
    <>
      <ComposerHeader
        user={user}
        title="Ask a question"
        onBack={back}
        backLabel={stage === "question" ? "Choose another product" : stage === "done" ? "Go to your question" : "Leave"}
        progress={PROGRESS[stage]}
      />
      <ComposerGrid />
      <ComposerLayout
        aside={
          <ComposerSteps
            flow="Ask a question"
            subjectLabel="Product in question"
            subject={stage === "product" ? null : (product?.canonical_name ?? null)}
            steps={panelSteps}
            note={stage === "product" ? null : "Anyone who has used it can answer, sellers included."}
          />
        }
      >
        {stage === "product" ? (
          <ProductPicker
            title="Mirror, mirror on the wall"
            blurb="Find the product. Ask a question. Let people answer."
            placeholder="e.g Anker Zolo Powerbank"
            searchLabel="Search for the product your question is about"
            fieldClassName="mt-[19px]"
            decorCards={PRODUCT_CARDS}
            emptyHint={false}
            onPick={(p) => {
              setProduct(p);
              go("question");
            }}
          />
        ) : null}
        {stage === "question" && product ? (
          <QuestionStep
            product={product}
            text={text}
            setText={setText}
            requirements={requirements}
            toggle={toggle}
            onChangeProduct={() => go("product")}
          />
        ) : null}
        {stage === "done" && product && postedId ? (
          <DoneStep user={user} text={text} questionId={postedId} />
        ) : null}

        {/* Pinned to the viewport on the phone, inline on the website. */}
        {stage === "question" ? (
          <ComposerActions hint={blocker} error={error}>
            <Button
              type="button"
              onClick={submit}
              disabled={Boolean(blocker) || busy}
              fullWidth
              className={COMPOSER_ACTION_BUTTON}
            >
              {busy ? "Posting…" : "Submit"}
              {busy ? null : <ArrowRight size={20} aria-hidden="true" />}
            </Button>
          </ComposerActions>
        ) : null}
      </ComposerLayout>

      <p role="status" className="sr-only">
        {blocker ?? ""}
      </p>
    </>
  );
}

/* --------------------------------------------------------------- question */

/**
 * "Question Page - Step 2" (4695:14599) / 2.3 (4742:15580): the product card;
 * 56px lower the white sheet at radius 32, 36px in from its top and 28px from
 * its sides. "What's your main question?" over a 156px white field at radius 16
 * with the card shadow, the counter 4px under it in 10px Light — "Good
 * question!" in brand orange once it is long enough, when the field takes an
 * orange line. 36px lower the specifics: 52px chips at radius 12, white at 30%
 * with a 0 4px 4px shadow at 10%, 12px apart, a 20px Plus 8px before 14px
 * Regular; a chosen chip takes the orange line and a green plus.
 */
function QuestionStep({
  product,
  text,
  setText,
  requirements,
  toggle,
  onChangeProduct,
}: {
  product: PickedProduct;
  text: string;
  setText: (text: string) => void;
  requirements: QuestionRequirement[];
  toggle: (r: QuestionRequirement) => void;
  onChangeProduct: () => void;
}) {
  const bodyId = useId();
  const bodyHint = useId();
  const specificsHint = useId();
  const short = MIN_QUESTION_CHARS - text.trim().length;

  return (
    <div className="relative">
      <TiltedRatingCards
        cards={QUESTION_CARDS}
        className="absolute -left-4 -right-4 -top-4 -z-10 hidden h-[260px] max-sm:block"
      />

      <CurrentlyReviewingCard
        label="Product in question:"
        labelInset={false}
        name={product.canonical_name ?? "Unnamed product"}
        onChange={onChangeProduct}
      />

      <section className="-mx-4 -mb-[120px] mt-14 rounded-t-[32px] bg-[var(--surface-card)] px-7 pb-[120px] pt-9 sm:-mx-6 sm:px-8 md:mx-0 md:mb-0 md:rounded-[32px] md:px-10 md:pb-10">
        <label htmlFor={bodyId} className={`block ${COMPOSER_HEADING}`}>
          What&rsquo;s your main question?
        </label>
        <p id={bodyHint} className={COMPOSER_HINT}>
          Ask your main question
        </p>
        <div className="relative mt-[18px]">
          <textarea
            id={bodyId}
            aria-describedby={bodyHint}
            value={text}
            onChange={(e) => setText(e.target.value.slice(0, MAX_QUESTION_TEXT))}
            className={`field-sizing-content block min-h-[156px] w-full resize-none rounded-[16px] border bg-[var(--surface-card)] px-[15px] py-4 text-[14px] leading-[21px] text-[var(--text-primary)] shadow-[var(--shadow-card)] outline-none focus-visible:border-[var(--accent-primary)] ${
              short > 0 ? "border-transparent" : "border-[rgba(239,88,33,0.8)]"
            }`}
          />
          {text.length === 0 ? (
            <span
              aria-hidden="true"
              className="pointer-events-none absolute left-4 top-4 text-[14px] leading-[21px] text-[rgba(32,32,32,0.3)]"
            >
              Write it <em>bluntly</em> here..
            </span>
          ) : null}
        </div>
        <p
          aria-live="polite"
          className={`mt-1 text-right text-[10px] font-light leading-none ${
            short > 0 ? "text-[var(--text-primary)]" : "text-[var(--accent-primary)]"
          }`}
        >
          {short > 0 ? `${short} characters remaining` : "Good question!"}
        </p>

        <fieldset aria-describedby={specificsHint} className="mt-9 min-w-0">
          <legend className={COMPOSER_HEADING}>Are there any specifics you&rsquo;d like to know?</legend>
          <p id={specificsHint} className={COMPOSER_HINT}>
            Help other buyers answer your question
          </p>
          <div className="mt-[18px] flex flex-wrap gap-3">
            {/* Figma Screen/Ask/Step 2 (7573:10506): four chips. Rating is not
                one — every answer must give a rating anyway (owner rule). */}
            {ASKABLE_REQUIREMENTS.map((r) => {
              const on = requirements.includes(r);
              return (
                <button
                  key={r}
                  type="button"
                  aria-pressed={on}
                  onClick={() => toggle(r)}
                  className={`flex h-[52px] cursor-pointer items-center gap-2 rounded-[12px] border bg-[rgba(255,255,255,0.3)] px-[15px] text-[14px] leading-none text-[var(--text-primary)] shadow-[0_4px_4px_0_var(--shadow-color-10)] ${COMPOSER_FOCUS_RING} ${
                    on ? "border-[rgba(239,88,33,0.8)]" : "border-transparent"
                  }`}
                >
                  <Plus
                    size={20}
                    weight="light"
                    aria-hidden="true"
                    className={`shrink-0 ${on ? "text-[var(--accent-success)]" : "text-[var(--base-gray-400)]"}`}
                  />
                  {r}
                </button>
              );
            })}
          </div>
        </fieldset>
      </section>
    </div>
  );
}

/* ------------------------------------------------------------------- done */

/**
 * "Question Page - Step 3" (4742:15979): "All done!", "Now, we wait.." and the
 * patience line in the composer heading stack; "View your question here:" 35px
 * lower and 14px in, over the ReviewQuoteCard (Photos=No) 33px under it (Screen/Ask/Step 3
 * 7573:11005); "Your latest stats:" 83px under the card and 11px in (32px on the website); the six tilted cards from the bottom corners; "View my
 * question" pinned 32px from the bottom.
 */
function DoneStep({
  user,
  text,
  questionId,
}: {
  user: PanelUser;
  text: string;
  questionId: string;
}) {
  return (
    <div className="relative">
      <TiltedRatingCards cards={DONE_CARDS} className="fixed inset-x-0 bottom-0 z-0 hidden h-[340px] max-sm:block" />
      <div className="relative z-10">
        <p className="text-[12px] leading-none text-[var(--text-primary)]">All done!</p>
        <h1 className="mt-2.5 text-[20px] font-medium leading-none text-[var(--accent-primary)]">Now, we wait..</h1>
        <p className="mt-[7px] text-[12px] font-light leading-[18px] text-[rgba(32,32,32,0.7)]">
          A little patience goes a long way. Give other buyers time to answer your question!
        </p>

        <p className="ml-[14px] mt-[35px] text-[12px] leading-none text-[var(--accent-trust)]">
          View your question here:
        </p>
        {/* Figma "Screen/Ask/Step 3" (7573:11005, re-read 2026-10-05):
            ReviewQuoteCard with Photos=No — the question in quotes, the
            asker's own stage and Honesty Score, real zero counts. A question
            carries no photo, so the product's image is not drawn as one. */}
        <ReviewQuoteCard
          username={user?.username ?? null}
          avatarUrl={user?.avatarUrl ?? null}
          levelName={user?.trustLevelName}
          stage={user?.trustStage}
          score={user?.reputationScore}
          title={text}
          className="mt-[21px] md:max-w-[26rem]"
        />

        <LatestStats className="mt-[83px] [&>p]:ml-[11px] md:mt-8 md:[&>dl]:justify-start" />
      </div>

      <ComposerActions>
        <Button href={`/questions/${questionId}`} fullWidth className={COMPOSER_ACTION_BUTTON}>
          View my question
          <ArrowRight size={20} aria-hidden="true" />
        </Button>
      </ComposerActions>
    </div>
  );
}

export default AskQuestionForm;
