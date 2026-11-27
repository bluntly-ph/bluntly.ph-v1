import Image from "next/image";
import Link from "next/link";
import type { ReactNode } from "react";
import { ArrowFatUp, ChatCircle, DotsThree } from "@phosphor-icons/react/dist/ssr";

import { AuthorHeader } from "@/components/review/AuthorHeader";

/**
 * Figma "ReviewQuoteCard" (component set 7702:7587, read 2026-10-05):
 * "author, quote title, up to 4 photo thumbnails (+N), reactions. Photos=No for
 * text-only reviews." As placed (7804:9249 / 7804:9287) in
 * "Screen/WriteReview/Step 7" (4452:748), "Step 7.1" (4512:4973) and
 * "Screen/WriteReview/Done" (4550:8882) it replaced the tilted ReviewCard.
 *
 *   card     white, radius 16, 16px padding, 12px gaps; no shadow; the frames
 *            place it 9px into the left gutter and 8px into the right
 *   author   a 36px avatar, 10px to the name in 12px Medium (capped 170px,
 *            ellipsis) and the age in 12px ExtraLight; under it the trust stage
 *            — the 12px bluntly mark and the level name in 12px ExtraLight —
 *            a 12px DotOutline, and the Honesty Score; a 24px DotsThree right
 *   quote    the title in 16px Italic on a 1.4 line, in curly quotes
 *   photos   Photos=Yes: up to four 72px thumbnails at radius 12, 6px apart;
 *            past four, the fourth is darkened at 45% under "+N" in 12px Medium
 *   metrics  a 16px ArrowFatUp in success green and a 16px ChatCircle, counts
 *            in 12px Light, 16px between the pairs
 *
 * NO PHOTO = NO DEFAULT PHOTO: `photos` is the reviewer's own uploads and
 * nothing else; with none the card is the frame's Photos=No variant.
 *
 * INTENTIONAL PRODUCT DIFFERENCE: the frames float "Earned ₱45.50 today" and a
 * reader's question over the card and fill it with sample engagement ("20d",
 * "14.8k", "3.2k"). A review being written, or posted seconds ago, has none of
 * those: the age says "now", the counts are their real zero, the pills are not
 * drawn. Stage and score are the signed-in reviewer's own (/auth/me); either is
 * left out when it cannot be read rather than shown as a made-up value.
 */
export function ReviewQuoteCard({
  username,
  avatarUrl,
  age = "now",
  levelName,
  stage,
  score,
  title,
  placeholder = "Your interesting title here...",
  photos = [],
  upvotes = 0,
  comments = 0,
  href,
  subject = null,
  footer,
  bleed = true,
  titleAs = "p",
  className = "",
}: {
  username: string | null;
  avatarUrl: string | null;
  age?: string;
  levelName?: string | null;
  stage?: number | null;
  score?: string | number | null;
  title: string;
  placeholder?: string;
  photos?: string[];
  upvotes?: number | string;
  comments?: number | string;
  /** On a results list the card opens its review: author, quote and photos are one link. */
  href?: string;
  /** What the review is about, when the list spans products (12px Light under the quote). */
  subject?: string | null;
  /** Live controls in place of the drawn counts (search: QA-027/028 votes, comment, share). */
  footer?: ReactNode;
  /** The composer frames bleed the card into the gutters; lists do not. */
  bleed?: boolean;
  /** "h2" on a results list, so each review title is a heading under the page h1. */
  titleAs?: "p" | "h2";
  className?: string;
}) {
  const quote = title.trim();
  const shown = photos.slice(0, 4);
  const more = photos.length - shown.length;

  const Title = titleAs;
  const body = (
    <>
      <AuthorHeader
        name={username ?? "you"}
        avatarUrl={avatarUrl}
        age={age}
        levelName={levelName}
        stage={stage}
        score={score}
        // Drawn, not wired: there is nothing yet for a menu to act on.
        trailing={<DotsThree size={24} aria-hidden="true" />}
      />

      <Title
        className={`break-words text-[16px] font-normal italic leading-[1.4] [overflow-wrap:anywhere] ${
          quote ? "" : "text-[rgba(32,32,32,0.5)]"
        }`}
      >
        &ldquo;{quote || placeholder}&rdquo;
      </Title>
      {subject ? <p className="-mt-2 truncate text-[12px] font-light leading-normal text-[#5c5c5c]">{subject}</p> : null}

      {shown.length ? (
        <ul className="grid grid-cols-[repeat(4,minmax(0,72px))] gap-1.5" aria-label={`${photos.length} ${photos.length === 1 ? "photo" : "photos"}`}>
          {shown.map((src, i) => (
            <li key={src} className="relative aspect-square overflow-hidden rounded-[12px] bg-[#e1e1e1]">
              <Image src={src} alt="" fill sizes="72px" className="object-cover" />
              {more > 0 && i === shown.length - 1 ? (
                <span className="absolute inset-0 grid place-items-center bg-[rgba(0,0,0,0.45)] text-[12px] font-medium text-white">
                  +{more}
                </span>
              ) : null}
            </li>
          ))}
        </ul>
      ) : null}
    </>
  );

  return (
    <article
      className={`${bleed ? "-ml-[9px] -mr-[8px]" : ""} flex flex-col gap-3 overflow-hidden rounded-[16px] bg-white p-4 text-[var(--text-primary)] ${className}`}
    >
      {href ? (
        <Link href={href} className="-m-1 flex flex-col gap-3 rounded-[12px] p-1 text-[var(--text-primary)] no-underline focus-visible:outline focus-visible:outline-2 focus-visible:outline-[var(--accent-primary)]">
          {body}
        </Link>
      ) : (
        body
      )}

      {footer ?? (
        <p className="flex items-center gap-4 text-[12px] font-light leading-[normal]">
          <span className="flex items-center gap-1">
            <ArrowFatUp size={16} weight="fill" aria-hidden="true" className="text-[var(--accent-success)]" />
            {upvotes}
            <span className="sr-only">{upvotes === 1 ? "upvote" : "upvotes"}</span>
          </span>
          <span className="flex items-center gap-1">
            <ChatCircle size={16} aria-hidden="true" />
            {comments}
            <span className="sr-only">{comments === 1 ? "comment" : "comments"}</span>
          </span>
        </p>
      )}
    </article>
  );
}

export default ReviewQuoteCard;
