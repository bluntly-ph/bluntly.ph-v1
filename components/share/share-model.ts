/**
 * What the app's share sheet shares (QA-024).
 *
 * The sheet only ever shares a page of this site: the link is built from the
 * current origin and a same-site PATH, so a share can never become an open
 * redirect or point somewhere a caller smuggled in. Anything that is not a plain
 * same-site path falls back to the site's home page.
 */

/** A same-site path, or "/" for anything that could leave the site. */
export function safeSharePath(path: string | null | undefined): string {
  if (!path || !path.startsWith("/") || path.startsWith("//") || path.includes("\\")) return "/";
  if ([...path].some((ch) => ch.trim() === "" || ch.charCodeAt(0) < 32)) return "/";
  return path;
}

/** The absolute link the sheet shows and copies. */
export function shareUrl(origin: string, path: string | null | undefined): string {
  return new URL(safeSharePath(path), origin).toString();
}

export type ShareStatus = "idle" | "copied" | "failed";

/** The copy button's words for each outcome. */
export function copyLabel(status: ShareStatus): string {
  if (status === "copied") return "Link copied";
  if (status === "failed") return "Couldn't copy — select the link and copy it";
  return "Copy link";
}

/**
 * The destinations Figma "Share to" (1731:1571, read 2026-09-24) draws in its
 * scrolling row, less the three this sheet cannot honestly offer:
 *
 *  - Instagram and "Add to Story": Instagram has no web share address. On a
 *    phone both are reached through "More" (the system sheet), which lists the
 *    installed Instagram app; a button here could only pretend.
 *  - Bookmark: Recent Reads and Bookmarks are omitted from the product on
 *    purpose (owner decision), so there is nothing for it to save into.
 *
 * `appOnly` marks the two with no web share page at all — Messenger's and
 * Viber's are app links — so they are offered only on a touch device, where
 * the app can answer them.
 */
export type ShareDestinationId = "facebook" | "messenger" | "reddit" | "x" | "viber" | "telegram" | "whatsapp";

export type ShareDestination = { id: ShareDestinationId; label: string; appOnly?: boolean };

export const SHARE_DESTINATIONS: readonly ShareDestination[] = [
  { id: "facebook", label: "Facebook" },
  { id: "messenger", label: "Messenger", appOnly: true },
  { id: "reddit", label: "Reddit" },
  { id: "x", label: "X" },
  { id: "viber", label: "Viber", appOnly: true },
  { id: "telegram", label: "Telegram" },
  { id: "whatsapp", label: "WhatsApp" },
];

/** The destinations to draw: the app-only two only where an app can open them. */
export function shareDestinations(touch: boolean): ShareDestination[] {
  return SHARE_DESTINATIONS.filter((d) => touch || !d.appOnly);
}

/**
 * Where a destination button goes. `url` is always `shareUrl(...)` — a page of
 * this site — and both it and the title are URL-encoded, so neither can break
 * out of the query string or turn the button into something else. The hosts are
 * fixed here; nothing a caller passes chooses them.
 */
export function destinationHref(id: ShareDestinationId, url: string, title: string): string {
  const u = encodeURIComponent(url);
  const t = encodeURIComponent(title);
  const both = encodeURIComponent(title ? `${title} ${url}` : url);
  switch (id) {
    case "facebook":
      return `https://www.facebook.com/sharer/sharer.php?u=${u}`;
    case "messenger":
      return `fb-messenger://share/?link=${u}`;
    case "reddit":
      return `https://www.reddit.com/submit?url=${u}&title=${t}`;
    case "x":
      return `https://x.com/intent/post?url=${u}&text=${t}`;
    case "viber":
      return `viber://forward?text=${both}`;
    case "telegram":
      return `https://t.me/share/url?url=${u}&text=${t}`;
    case "whatsapp":
      return `https://wa.me/?text=${both}`;
  }
}
