"use client";

import {
  Coins,
  HandHeart,
  Prohibit,
  Signpost,
  Star,
  WarningCircle,
} from "@phosphor-icons/react/dist/ssr";

import { TIER_LABELS, type PriorityTier } from "@/components/admin/review-queue-model";
import { Avatar } from "@/components/ui/Avatar";
import { trustLevelName } from "@/lib/trust";

/**
 * The cells of the redesigned queue table (Row 7943:11533), each from a served
 * field: nothing here decides a policy, it only draws one.
 */

export type EarningPath = "commission" | "honesty_fund" | "super_admin" | "taken_down";

/**
 * Where approving this review's earnings would send them. Mirrors
 * `earning_track.track_for` (verdict first; for "It depends", the stars:
 * 3+ commission, 2 or less the Honesty Fund, exactly 2.5 a Super Admin) and the
 * stored states that already settled it. A review an administrator took down
 * earns nothing until it is restored.
 */
export function earningPath(review: {
  verdict?: string;
  star_rating: number;
  published_at?: string | null;
  earn_eligible_status?: string;
}): EarningPath {
  if (review.published_at === null) return "taken_down";
  if (review.earn_eligible_status === "pending_superadmin_routing") return "super_admin";
  if (review.earn_eligible_status === "honesty_fund") return "honesty_fund";
  if (review.earn_eligible_status === "monetized") return "commission";
  if (review.verdict === "yes_absolutely") return "commission";
  if (review.verdict === "hard_pass") return "honesty_fund";
  if (review.star_rating >= 3) return "commission";
  if (review.star_rating <= 2) return "honesty_fund";
  return "super_admin";
}

const PATH: Record<EarningPath, { label: string; icon: React.ReactNode }> = {
  commission: { label: "Commission", icon: <Coins size={14} className="text-[var(--accent-primary)]" /> },
  honesty_fund: { label: "Honesty Fund", icon: <HandHeart size={14} className="text-[var(--accent-trust)]" /> },
  super_admin: { label: "Super Admin", icon: <Signpost size={14} className="text-[var(--text-secondary)]" /> },
  taken_down: { label: "Taken down", icon: <Prohibit size={14} className="text-[var(--text-secondary)]" /> },
};

export function EarningCell({ path }: { path: EarningPath }) {
  const p = PATH[path];
  return (
    <span className="inline-flex items-center gap-[6px] whitespace-nowrap">
      {p.icon}
      <span className={path === "taken_down" ? "text-[var(--text-secondary)]" : ""}>{p.label}</span>
    </span>
  );
}

/**
 * The star's colour ladder, with the tokens the console frames bind (Queue/
 * AllReviews 8060:15564): green 4+ (success-500), yellow 3 (star), coral 2–2.5
 * (brand-coral), red below (danger). The same grades as components/ui/star-ladder.
 */
export function starTone(rating: number): string {
  if (rating >= 4) return "text-[var(--semantic-success-500)]";
  if (rating >= 3) return "text-[var(--accent-star)]";
  if (rating >= 2) return "text-[var(--brand-coral)]";
  return "text-[var(--semantic-danger)]";
}

export function RatingCell({ rating, muted = false }: { rating: number; muted?: boolean }) {
  return (
    <span className="inline-flex items-center gap-1">
      <Star size={16} weight="fill" className={muted ? "text-[var(--text-muted)]" : starTone(rating)} />
      {Number.isInteger(rating) ? rating : rating.toFixed(1)}
    </span>
  );
}

/** "Trusted Reviewer" reads "Trusted" in a 150px column, as the frame writes it. */
export function levelLabel(stage: number | null | undefined): string {
  const name = trustLevelName(stage ?? null);
  return name ? name.replace(/ Reviewer$/, "") : "—";
}

/** Three signal bars, `filled` of them dark (or orange for High). */
function Bars({ filled, tone }: { filled: number; tone: string }) {
  return (
    <svg width="14" height="14" viewBox="0 0 14 14" aria-hidden className="shrink-0">
      {[0, 1, 2].map((i) => (
        <rect
          key={i}
          x={1 + i * 4.5}
          y={10 - i * 3}
          width="3"
          height={3 + i * 3}
          rx="0.75"
          className={i < filled ? tone : "fill-[var(--base-gray-200)]"}
        />
      ))}
    </svg>
  );
}

/** The admin priority tier (Tier 7949:10663): colour on the icon, the label dark. */
export function TierCell({ tier }: { tier: PriorityTier | null | undefined }) {
  if (!tier) return <span className="text-[var(--text-secondary)]">—</span>;
  const icon =
    tier === "highest" ? (
      <WarningCircle size={14} weight="fill" className="shrink-0 text-[var(--accent-danger)]" />
    ) : tier === "high" ? (
      <Bars filled={3} tone="fill-[var(--accent-primary)]" />
    ) : tier === "neutral" ? (
      <Bars filled={2} tone="fill-[var(--text-primary)]" />
    ) : tier === "low" ? (
      <Bars filled={1} tone="fill-[var(--text-primary)]" />
    ) : (
      <Bars filled={0} tone="" />
    );
  return (
    <span className={`inline-flex items-center gap-[6px] ${tier === "lowest" ? "text-[var(--text-secondary)]" : ""}`}>
      {icon}
      {TIER_LABELS[tier]}
    </span>
  );
}

/** The brand's trust mark beside a level name (the frames' small orange swoosh). */
/** The bluntly mark before a trust level, as the frames draw it (Admin/People 7998:11693). */
export function TrustMark() {
  return (
    <svg width="12" height="7" viewBox="0 0 20.25 12.32" aria-hidden className="shrink-0 rotate-180" fill="var(--accent-primary)">
      <path
        fillRule="evenodd"
        clipRule="evenodd"
        d="M4.60101 12.315C2.79098 12.272 1.2407 11.1719 0.544266 9.60896C0.0611048 8.52464 -0.00258593 7.68618 7.75363e-05 7.00665C0.00598018 5.50118 7.75363e-05 0.000405948 7.75363e-05 0.000405948H3.80314C3.80314 0.000405948 3.80597 5.81489 3.80314 7.17334C3.80236 7.54307 4.05111 7.96393 4.4332 8.12677C4.76944 8.27007 5.29764 8.17814 5.55733 7.92095C6.9268 6.56468 12.2333 1.30876 13.2343 0.624828C13.8919 0.17551 14.5615 0 15.6435 0C17.4575 0 19.0109 1.14202 19.7079 2.7078C20.2037 3.82177 20.2461 4.38028 20.2474 5.17135C20.25 6.75691 20.2474 12.3164 20.2474 12.3164H16.4443C16.4443 12.3164 16.4443 6.32585 16.4443 4.95C16.4443 4.63161 16.2617 4.20518 15.7652 4.07111C15.3709 3.96462 14.9694 4.11271 14.6901 4.39202C13.3137 5.7685 8.00061 11.0159 7.00033 11.7002C6.34819 12.1464 5.44412 12.3351 4.60101 12.315Z"
      />
    </svg>
  );
}

/** A person in a table: initial avatar, name, trust level (Asked by / From columns). */
export function PersonCell({
  name,
  stage,
  levelName,
  href,
  avatarUrl = null,
}: {
  name: string;
  stage?: number | null;
  levelName?: string | null;
  href?: string;
  /** The member's own photo (avatar_url); initials when null or broken. */
  avatarUrl?: string | null;
}) {
  const level = levelName ? levelName.replace(/ Reviewer$/, "") : levelLabel(stage);
  const label = (
    <span className="flex min-w-0 flex-col gap-1 leading-4 [&>:first-child]:leading-5">
      <span className="truncate">{name}</span>
      {stage !== undefined || levelName ? (
        <span className="flex items-center gap-1 truncate text-[12px] text-[var(--text-secondary)]">
          <TrustMark />
          {level}
        </span>
      ) : null}
    </span>
  );
  return (
    <span className="flex items-center gap-2">
      <Avatar name={name} url={avatarUrl} size={28} />
      {href ? (
        <a href={href} onClick={(e) => e.stopPropagation()} className="min-w-0 hover:text-[var(--accent-primary)]">
          {label}
        </a>
      ) : (
        label
      )}
    </span>
  );
}

/** "25m", "2h", "3d": the tables' short ages, from the server's render instant. */
export function shortAge(iso: string, now: number): string {
  const s = Math.max(0, Math.round((now - new Date(iso).getTime()) / 1000));
  if (s < 3600) return `${Math.max(1, Math.round(s / 60))}m`;
  if (s < 86400) return `${Math.round(s / 3600)}h`;
  return `${Math.round(s / 86400)}d`;
}
