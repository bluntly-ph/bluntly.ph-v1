import type { QuestionRequirement } from "./ask-question-model";
import { shownRequests } from "./structured-question-model";

/**
 * "Looking for:" and a chip per specific the asker requested (12px Light
 * label, 10px chips on #d9d9d9, radius 4). Rating is never shown (it is
 * required of every answer); a question that requested nothing renders
 * nothing.
 *
 * No Figma frame draws a requested-specifics row (PIM checked Page 1 live,
 * 2026-10-05: Screen/Question 7731:15647 has title, situation and Reactions
 * only), so the question page and the list cards share this one treatment,
 * the smallest that fits the design system. Spec §6, §11 q3.
 */
export function LookingFor({ requested, className = "" }: { requested: readonly QuestionRequirement[]; className?: string }) {
  const shown = shownRequests(requested);
  if (shown.length === 0) return null;
  return (
    <div className={`flex min-w-0 flex-wrap items-center gap-2 ${className}`} data-testid="looking-for">
      <span className="text-[12px] font-light leading-none">Looking for:</span>
      {shown.map((r) => (
        <span key={r} className="rounded-[4px] bg-[#d9d9d9] px-2 py-1 text-[10px] leading-none">
          {r}
        </span>
      ))}
    </div>
  );
}
