import Link from "next/link";
import { ChatCircle, Medal } from "@phosphor-icons/react/dist/ssr";

import { splitQuestionBody } from "@/components/qa/ask-question-model";
import { LookingFor } from "@/components/qa/LookingFor";
import { questionSubject } from "@/components/qa/question-subject-model";
import { Avatar } from "@/components/ui/Avatar";
import type { Question } from "@/lib/qa";
import { relativeTime } from "@/lib/relative-time";

/**
 * A question in a list (the Questions tab of /search and /questions): Figma
 * "ThreadCard" (component 7761:7892, "Discussion card for product question
 * lists", as placed in Screen/Product/Questions/All 7753:7873; read live
 * 2026-10-05). It replaced "QuestionPreviewCard" (7158:4877), which is no
 * longer in the file.
 *
 *   card    white, radius 16, 16px in, 12px between its rows; cards 12px apart
 *   asker   a 20px avatar, 6px to the name in 12px Regular and the age in
 *           12px ExtraLight
 *   title   the question in 16px Medium
 *   footer  16px glyphs with 12px Light counts, 16px apart
 *
 * Drawn from real data only. Not drawn, for want of it in the list API:
 * "2 here now" (the card's Show live toggle), the reply teaser (Show reply:
 * the top answer's excerpt), the up-vote count and the participant faces —
 * each needs a field on QuestionOut (CLAUDE_PIM_STATUS.md, FOR RESEARCH).
 * The asker carries no avatar URL in the API, so Avatar draws their initial.
 *
 * INTENTIONAL PRODUCT DIFFERENCE: the frame sits on one product's page; a
 * search list can span products and stores, so the subject (product or store)
 * is named in 12px Light under the title. The requested specifics show as the
 * shared "Looking for:" row (no Figma slot; spec §6).
 */
export function QuestionResultRow({ question }: { question: Question }) {
  const answers = question.answer_count;
  const { text, requirements } = splitQuestionBody(question.body);
  const asker = question.asker?.display_name ?? question.asker?.username ?? "Former member";

  return (
    <li>
      {/* QA-023: the whole card is the one link, with hover and pressed states. */}
      <Link
        href={`/questions/${question.id}`}
        className="group flex flex-col gap-3 rounded-[16px] bg-[var(--surface-card)] p-4 text-[var(--text-primary)] no-underline transition-colors duration-[var(--duration-fast)] hover:bg-[#f9f9f9] active:bg-[#f9f9f9] focus-visible:outline focus-visible:outline-2 focus-visible:outline-[var(--accent-primary)]"
      >
        <span className="flex min-w-0 items-center gap-[6px] text-[12px] leading-normal">
          <Avatar name={asker} url={null} size={20} />
          <span className="min-w-0 truncate">{asker}</span>
          <span className="shrink-0 font-extralight" suppressHydrationWarning>
            {relativeTime(question.created_at)}
          </span>
        </span>

        <span className="flex flex-col gap-1">
          {/* An h2 under the page's h1: the list's headings stay navigable (QA-023). */}
          <h2 className="line-clamp-3 text-[16px] font-medium leading-normal [overflow-wrap:anywhere] group-hover:text-[var(--accent-primary)]">
            {text}
          </h2>
          <span className="truncate text-[12px] font-light leading-normal text-[#5c5c5c]">{questionSubject(question).label}</span>
        </span>

        <LookingFor requested={requirements} />

        <span className="flex items-center gap-4 text-[12px] font-light leading-normal">
          <span className="inline-flex items-center gap-1">
            <ChatCircle size={16} aria-hidden="true" />
            {answers === 0 ? "Unanswered" : `${answers} ${answers === 1 ? "answer" : "answers"}`}
          </span>
          {question.best_answer_id ? (
            <span className="inline-flex items-center gap-1">
              <Medal size={16} aria-hidden="true" /> Best answer
            </span>
          ) : null}
        </span>
      </Link>
    </li>
  );
}

export default QuestionResultRow;
