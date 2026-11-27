import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { AnswerFlow } from "@/components/qa/AnswerFlow";
import { splitQuestionBody } from "@/components/qa/ask-question-model";
import { requireOnboardedUser } from "@/lib/dal";
import { getSessionToken } from "@/lib/session";
import { getQuestionDetail } from "@/lib/qa";

export const metadata: Metadata = { title: "Answer a question — bluntly" };

/**
 * The answer flow (Figma "Answer Page - Step 1..7", 7573:8215…), reached from
 * a question's "Answer" button. Signed-in members only; the API decides who
 * may answer (the Q&A rules) and says why when it refuses.
 */
export default async function AnswerQuestionPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const me = await requireOnboardedUser();
  const question = await getQuestionDetail(id, await getSessionToken());
  if (!question) notFound();
  const { text, requirements } = splitQuestionBody(question.body);
  const [first, ...rest] = text.trim().split("\n");
  const context = rest.join(" ").trim() || null;
  return (
    <div className="min-h-dvh bg-[var(--surface-app)]">
      <AnswerFlow
        user={{ username: me.username, avatarUrl: me.avatar_url, role: me.role }}
        questionId={question.id}
        question={first}
        context={context}
        requested={requirements}
        asker={
          question.asker
            ? {
                name: question.asker.display_name ?? question.asker.username ?? "Member",
                levelName: question.asker.trust_level_name,
                stage: question.asker.trust_stage,
                score: question.asker.reputation_score,
                avatarUrl: question.asker.avatar_url ?? null,
              }
            : null
        }
        askedAt={question.created_at}
        upvotes={question.upvotes ?? 0}
        replies={question.reply_count ?? 0}
      />
    </div>
  );
}
