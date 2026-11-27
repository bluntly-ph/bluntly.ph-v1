import { SealCheck, Star, StarHalf } from "@phosphor-icons/react/dist/ssr";

import { STAR_EMPTY, formatRating, starColor, starFill } from "@/components/ui/star-ladder";

import { sellerInitials } from "./seller-model";

/**
 * The small pieces every seller surface shares: the store's mark, whether it
 * has been claimed, and a row of stars.
 *
 * No hooks, so server pages and the client composer both use them.
 */

const FACE = "font-[family-name:var(--font-system)]";

/**
 * A store has no logo in this product. The owner's frames draw the unclaimed
 * store ("JAS") as its initials on a plain disc, so every store is drawn that
 * way rather than with a borrowed or invented logo.
 */
export function SellerAvatar({
  name,
  size = 80,
  shape = "circle",
}: {
  name: string;
  size?: number;
  shape?: "circle" | "tile";
}) {
  return (
    <span
      aria-hidden="true"
      className={`grid shrink-0 place-items-center bg-[var(--surface-card)] ${FACE} text-[var(--text-muted)] ${
        shape === "circle" ? "rounded-full" : "rounded-[var(--radius-md)]"
      }`}
      style={{ width: size, height: size, fontSize: Math.round(size * 0.28) }}
    >
      {sellerInitials(name)}
    </span>
  );
}

/**
 * A reviewer with no photo, as a plain 36px disc with their initial. Members
 * carry no avatar in the seller API, so no face is invented for them.
 */
export function ReviewerInitial({ name, size = 36 }: { name: string; size?: number }) {
  return (
    <span
      aria-hidden="true"
      className={`grid shrink-0 place-items-center rounded-full bg-[var(--base-gray-200)] ${FACE} font-semibold text-[var(--text-secondary)]`}
      style={{ width: size, height: size, fontSize: Math.round(size * 0.4) }}
    >
      {(name.trim()[0] ?? "?").toUpperCase()}
    </span>
  );
}

/**
 * "Claimed Profile" only after an administrator approved a claim; everything else,
 * including a store with a claim still waiting, is unclaimed.
 *
 * Figma "ClaimedBadge" (7159:4840): a 16px SealCheck and 12px Poppins Regular,
 * 4px apart. The row is drawn at 70% and its parts at 70% again, so the whole
 * badge reads at 49% ink - kept for "Unclaimed Profile"; "Claimed Profile" is
 * trust blue with a filled seal (MQA-034).
 */
export function ClaimStatusLine({ status }: { status: string }) {
  const claimed = status === "claimed";
  // MQA-034: a claimed profile is the one a shopper should notice, so it
  // leaves the frame's 49% ink for the trust blue and a filled seal; an
  // unclaimed one keeps the muted grey. (The frame drew both alike, and the
  // claim step then told a shopper scanning the list nothing.)
  return claimed ? (
    <span data-claim="claimed" className="flex items-center gap-1 text-[12px] font-medium leading-none text-[var(--accent-trust)]">
      <SealCheck size={16} weight="fill" aria-hidden="true" />
      Claimed Profile
    </span>
  ) : (
    <span data-claim="unclaimed" className="flex items-center gap-1 text-[12px] leading-none text-[var(--text-primary)] opacity-[0.49]">
      Unclaimed Profile
    </span>
  );
}

/**
 * Display only. A store with no rating draws grey stars and says so.
 *
 * Figma "Icon/Star" (6805:431): Filled takes the rating ladder's colour — coral
 * for 1–2, yellow for 3, the rating green for 4–5 — Half is that colour over
 * the grey, and Empty is a solid #8c8c8c silhouette (--base-gray-400). Ratings
 * run 0 to 5 in half steps (owner requirement, 2026-09-16).
 */
export function StarRow({
  value,
  size = 20,
  gap = 2,
  className = "",
}: {
  value: number | null;
  size?: number;
  /** Pixels between stars. The search row's frame spaces them wider. */
  gap?: number;
  className?: string;
}) {
  return (
    <span
      role="img"
      aria-label={value === null ? "Not rated yet" : `Rated ${formatRating(value)} out of 5`}
      className={`inline-flex ${className}`}
      style={{ gap }}
    >
      {[1, 2, 3, 4, 5].map((n) => {
        const fill = starFill(n, value);
        // A half is the grey star with the coloured half drawn over it, so the
        // split is the glyph's own rather than a clipped rectangle.
        return (
          <span key={n} className="relative inline-block" style={{ width: size, height: size }}>
            <Star
              size={size}
              weight="fill"
              aria-hidden="true"
              className="absolute inset-0"
              style={{ color: fill === "full" ? starColor(value) : STAR_EMPTY }}
            />
            {fill === "half" ? (
              <StarHalf
                size={size}
                weight="fill"
                aria-hidden="true"
                className="absolute inset-0"
                style={{ color: starColor(value) }}
              />
            ) : null}
          </span>
        );
      })}
    </span>
  );
}
