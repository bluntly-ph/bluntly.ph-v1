"use client";

import { ShareSheet } from "@/components/share/ShareSheet";
import { markInteraction } from "@/lib/reading-telemetry-events";

/**
 * Share a review (BUG-015, QA-024).
 *
 * Opens the app's share sheet rather than handing straight to the operating
 * system's: the retest expected the app's own interface, and on desktop the old
 * path was a silent clipboard write. The system sheet is still one tap away,
 * as "More options…" inside ours, where the browser has one.
 *
 * It shares the review's own address — not `window.location`, which can carry
 * a query, a fragment or a returning `?next=` that has no business in a link
 * someone else will open.
 *
 * `variant="icon"` is the Review page frame's round Share (4218:1196).
 */
export function ShareButton({
  title,
  reviewId,
  excerpt,
  image,
  caption,
  variant = "label",
}: {
  title: string;
  reviewId: string;
  /** The review's opening lines, for the sheet's preview card. */
  excerpt?: string | null;
  /** QA-070: the preview picture — `shareImageFor(review photo, product image)`. */
  image?: string | null;
  /** The author's own prompt (Figma "Share to"); pass it only to the author. */
  caption?: string | null;
  variant?: "label" | "icon" | "inline";
}) {
  return (
    <ShareSheet
      path={`/reviews/${reviewId}`}
      title={title}
      excerpt={excerpt}
      image={image}
      caption={caption}
      variant={variant}
      onShared={() => markInteraction(reviewId, "share")}
    />
  );
}

export default ShareButton;
