import Link from "next/link";
import { DotOutline, SealCheck } from "@phosphor-icons/react/dist/ssr";

import { Avatar } from "@/components/ui/Avatar";
import { HonestyScore } from "@/components/ui/HonestyScore";
import { trustLevel } from "@/lib/trust";

/**
 * Figma "Author" (7659:5991, read 2026-10-05): "Author header for reviews,
 * answers, replies and seller responses." A 36px avatar, 10px to the name in
 * 12px Medium (capped at 170px) beside the age in 12px ExtraLight; under them
 * the trust stage — the 12px bluntly mark and the level name in 12px
 * ExtraLight — a 12px DotOutline, and the Honesty Score (the shield, 0-100).
 * Stage and score are different things and both are drawn; either is left out
 * when it is unknown rather than shown as a made-up value.
 *
 * One component for every place the frames place Author: the published review
 * (Screen/Product 7660:5901) and ReviewQuoteCard (the composer's, the
 * question's and the seller review's previews).
 */
export function AuthorHeader({
  name,
  href,
  avatarUrl,
  age,
  levelName,
  stage,
  score,
  trailing,
  badges,
  seller = false,
  className = "",
}: {
  name: string;
  href?: string | null;
  avatarUrl: string | null;
  age?: React.ReactNode;
  levelName?: string | null;
  stage?: number | null;
  score?: string | number | null;
  /** The overflow menu (or the frame's DotsThree), at the right. */
  trailing?: React.ReactNode;
  /** Small chips after the age ("New account"). */
  badges?: React.ReactNode;
  /**
   * Author Type=Seller: "Seller • ✓ Claimed" in place of the trust stage and
   * Honesty Score, which belong to reviewers.
   */
  seller?: boolean;
  className?: string;
}) {
  const hasStage = !seller && (Boolean(levelName) || (stage !== null && stage !== undefined));
  const stageName = hasStage ? trustLevel(levelName, stage) : null;
  const hasScore = !seller && score !== null && score !== undefined && score !== "";

  return (
    <div className={`flex min-w-0 items-center gap-2.5 text-[var(--text-primary)] ${className}`}>
      <Avatar name={name} url={avatarUrl} size={36} />
      <span className="flex min-w-0 flex-1 flex-col gap-1">
        <span className="flex min-w-0 items-center gap-1.5 text-[12px] leading-[normal]">
          {href ? (
            <Link href={href} className="max-w-[170px] truncate font-medium hover:text-[var(--accent-primary)]">
              {name}
            </Link>
          ) : (
            <span className="max-w-[170px] truncate font-medium">{name}</span>
          )}
          {age ? <span className="shrink-0 font-extralight">{age}</span> : null}
          {badges}
        </span>
        {seller ? (
          <span className="flex items-center gap-1 text-[12px] font-extralight leading-[normal]">
            Seller
            <DotOutline size={12} aria-hidden="true" className="shrink-0 text-[var(--base-gray-400)]" />
            <SealCheck size={16} weight="fill" aria-hidden="true" className="shrink-0 text-[var(--accent-trust)]" />
            Claimed
          </span>
        ) : stageName || hasScore ? (
          <span className="flex min-w-0 flex-wrap items-center gap-1 text-[12px] font-extralight leading-[normal]">
            {stageName ? (
              <>
                <BluntlyMark />
                <span className="min-w-0 truncate">{stageName}</span>
              </>
            ) : null}
            {stageName && hasScore ? (
              <DotOutline size={12} aria-hidden="true" className="shrink-0 text-[var(--base-gray-400)]" />
            ) : null}
            <HonestyScore score={score} levelName={levelName} stage={stage} />
          </span>
        ) : null}
      </span>
      {trailing ? <span className="shrink-0 self-start">{trailing}</span> : null}
    </div>
  );
}

/** The 12px bluntly mark the trust stage carries (Figma "FAVICON1-SOLID", turned 180°). */
export function BluntlyMark() {
  return (
    <svg width="12" height="12" viewBox="-1 -3 12.1243 12.1582" aria-hidden="true" className="shrink-0 rotate-180">
      <path
        fillRule="evenodd"
        clipRule="evenodd"
        fill="var(--accent-primary)"
        d="M2.3005 6.15752C1.39549 6.13598 0.620349 5.58595 0.272133 4.80448C0.0305524 4.26232 -0.00129297 3.84309 3.87681e-05 3.50332C0.00299009 2.75059 3.87681e-05 0.000202974 3.87681e-05 0.000202974H1.90157C1.90157 0.000202974 1.90298 2.90744 1.90157 3.58667C1.90118 3.77153 2.02555 3.98196 2.2166 4.06339C2.38472 4.13504 2.64882 4.08907 2.77866 3.96048C3.4634 3.28234 6.11667 0.654381 6.61714 0.312414C6.94593 0.0877549 7.28077 0 7.82173 0C8.72876 0 9.50544 0.571011 9.85394 1.3539C10.1019 1.91089 10.123 2.19014 10.1237 2.58567C10.125 3.37846 10.1237 6.15818 10.1237 6.15818H8.22216C8.22216 6.15818 8.22216 3.16292 8.22216 2.475C8.22216 2.31581 8.13083 2.10259 7.8826 2.03555C7.68545 1.98231 7.48472 2.05636 7.34506 2.19601C6.65683 2.88425 4.0003 5.50796 3.50017 5.85011C3.17409 6.07318 2.72206 6.16755 2.3005 6.15752Z"
      />
    </svg>
  );
}

export default AuthorHeader;
