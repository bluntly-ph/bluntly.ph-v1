import Link from "next/link";

import type { SavedComment } from "@/lib/comments";
import { splitHeadline } from "@/lib/reviews";

/**
 * One saved comment on the member's own profile (QA-069). The Comments tab's
 * row (ProfileCommentRow) with who wrote it, linking to the comment itself on
 * its review — `#comment-<id>` — rather than the top of the review.
 */
export function SavedCommentRow({ comment }: { comment: SavedComment }) {
  const headline = splitHeadline(comment.review.title, comment.review.product_name);
  const who = comment.author?.username ?? comment.author?.display_name ?? "someone";

  return (
    <li className="border-b border-[var(--line-hairline-10)] px-4 py-4 md:rounded-[16px] md:border-b-0 md:bg-[var(--surface-card)] md:p-4 md:shadow-[var(--shadow-card)]">
      <article className="mx-auto w-full max-w-[358px] md:max-w-none">
        <Link
          href={`/reviews/${comment.review.id}#comment-${comment.id}`}
          className="block text-[var(--text-primary)] no-underline"
        >
          <h2 className="text-[14px] leading-[21px]">
            {headline.product ? (
              <>
                <span className="font-bold">{headline.product} - </span>
                {headline.rest}
              </>
            ) : (
              <span className="font-bold">{comment.review.title}</span>
            )}
          </h2>
          <p className="mt-1 text-[12px] font-light leading-[18px] [overflow-wrap:anywhere]">{comment.body}</p>
          <p className="mt-2 text-[12px] font-light leading-none text-[var(--text-secondary)]">by {who}</p>
        </Link>
      </article>
    </li>
  );
}

export default SavedCommentRow;
