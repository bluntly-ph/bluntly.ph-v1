"use client";

import {
  useEffect,
  useId,
  useImperativeHandle,
  useRef,
  useState,
  type ComponentType,
  type Ref,
} from "react";
import {
  ChatCircleDots,
  Check,
  DotsThree,
  FacebookLogo,
  LinkSimple,
  MessengerLogo,
  RedditLogo,
  ShareFat,
  Share,
  ShareNetwork,
  TelegramLogo,
  WhatsappLogo,
  X,
  XLogo,
  type IconProps,
} from "@phosphor-icons/react";

import {
  copyLabel,
  destinationHref,
  shareDestinations,
  shareUrl,
  type ShareDestinationId,
  type ShareStatus,
} from "./share-model";
import { FALLBACK_SHARE_IMAGE } from "@/lib/share-image";

const FOCUS =
  "focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--accent-primary)]";

/** What a caller can do with a sheet drawn with `variant="none"`. */
export type ShareSheetHandle = { open: () => void };

/** Brand marks. Phosphor has no Viber logo, so its tile carries a chat glyph in Viber's purple. */
const MARK: Record<ShareDestinationId, { Icon: ComponentType<IconProps>; colour: string }> = {
  facebook: { Icon: FacebookLogo, colour: "#1877F2" },
  messenger: { Icon: MessengerLogo, colour: "#0084FF" },
  reddit: { Icon: RedditLogo, colour: "#FF4500" },
  x: { Icon: XLogo, colour: "var(--text-primary)" },
  viber: { Icon: ChatCircleDots, colour: "#7360F2" },
  telegram: { Icon: TelegramLogo, colour: "#26A5E4" },
  whatsapp: { Icon: WhatsappLogo, colour: "#25D366" },
};

/** A 48px outlined tile with its 10px label 4px under it — the frame's destination unit. */
const TILE =
  "grid h-12 w-12 place-items-center rounded-[12px] border border-[var(--line-hairline-30)] bg-[var(--surface-app)] group-hover:bg-[var(--line-hairline-10)]";
const TILE_LABEL = "mt-1 text-center text-[10px] font-light leading-[10px] text-[var(--text-primary)]";

/**
 * The app's own share sheet (QA-024), built to Figma "Share to" (1731:1571),
 * read 2026-09-24.
 *
 * Top to bottom as drawn: a 28px ShareFat, "Share to…" in 16px Bold and the
 * close X; a preview card of what is being shared (30% ink outline, radius
 * 16); a 342px rule; the caption, where one applies; a scrolling row of 48px
 * destination tiles on a 65px pitch with 10px labels; then Copy link and More.
 *
 * Destinations, and why three of the frame's are not drawn, are in
 * share-model. Every one opens this site's link for the item in a new tab, at
 * a host fixed in code; nothing a caller passes can change where it goes.
 *
 * The caption — "Share your post on other platforms to get more views and
 * boost your commission." — is the author's own prompt, so callers pass it only
 * to the author, and only mention commission when the post can earn one.
 *
 * The link itself stays in a read-only field for assistive technology and is
 * shown when copying is refused, selected, so a manual copy is one keystroke.
 * A native <dialog>: Escape and the backdrop close it, focus is trapped while
 * it is open and returns to the trigger afterwards.
 *
 * Variants: `icon` is the review page's 32px round Share; `label` is a pill
 * with the word; `inline` is the small text action in a comment's row.
 */
export function ShareSheet({
  path,
  title,
  excerpt,
  image = null,
  caption,
  variant = "label",
  onShared,
  handle,
}: {
  /** A same-site path; anything else shares the home page (share-model). */
  path: string;
  title: string;
  /** A few lines of what is shared, for the preview card. */
  excerpt?: string | null;
  /** QA-070: the picture the link travels with, shown in the preview card. */
  image?: string | null;
  /** The frame's author prompt under the rule; omitted for everyone else. */
  caption?: string | null;
  /** `none` draws no trigger: a caller opens the sheet through `handle`. */
  variant?: "icon" | "label" | "inline" | "none";
  /** Called once per completed share or copy, e.g. for reading telemetry. */
  onShared?: () => void;
  /** Opens the sheet from elsewhere, e.g. a "⋯" menu item (the profile's). */
  handle?: Ref<ShareSheetHandle>;
}) {
  const dialogRef = useRef<HTMLDialogElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const titleId = useId();
  const [status, setStatus] = useState<ShareStatus>("idle");
  const [url, setUrl] = useState("");
  // Read when the sheet opens, not while rendering: `navigator.share` and the
  // pointer type exist only in the browser, and reading them during SSR would
  // hydrate wrongly.
  const [systemShare, setSystemShare] = useState(false);
  const [touch, setTouch] = useState(false);
  // The sheet's body exists only while it is open. Every comment carries a
  // Share, and a closed <dialog> still holds its content: without this, each
  // comment's words sat in the page twice (once in the thread, once in its
  // hidden preview card) and every page carried every sheet's markup.
  const [isOpen, setIsOpen] = useState(false);

  useEffect(() => {
    const el = dialogRef.current;
    if (!el) return;
    const onClose = () => {
      setStatus("idle");
      setIsOpen(false);
    };
    el.addEventListener("close", onClose);
    return () => el.removeEventListener("close", onClose);
  }, []);

  // Shown once its body has rendered, so the dialog focuses a real control.
  useEffect(() => {
    const el = dialogRef.current;
    if (isOpen && el && !el.open) el.showModal();
  }, [isOpen]);

  function open(event: React.MouseEvent) {
    // Inside a card that is itself a link, a Share must not also navigate.
    event.preventDefault();
    event.stopPropagation();
    openSheet();
  }

  function openSheet() {
    setUrl(shareUrl(window.location.origin, path));
    setSystemShare(typeof navigator.share === "function");
    setTouch(window.matchMedia?.("(pointer: coarse)").matches ?? false);
    setIsOpen(true);
  }
  useImperativeHandle(handle, () => ({ open: openSheet }));


  async function copy() {
    try {
      await navigator.clipboard.writeText(url);
      setStatus("copied");
      onShared?.();
    } catch {
      // Clipboard refused (permissions, insecure context): show the link
      // selected so a manual copy is one keystroke away.
      setStatus("failed");
      requestAnimationFrame(() => inputRef.current?.select());
    }
  }

  async function more() {
    try {
      await navigator.share({ title, url });
      onShared?.();
      dialogRef.current?.close();
    } catch (error) {
      // Dismissing the system sheet is the reader declining, not a failure.
      if ((error as Error)?.name !== "AbortError") setStatus("failed");
    }
  }

  const trigger =
    variant === "none" ? null : variant === "icon" ? (
      <button
        type="button"
        onClick={open}
        aria-label="Share"
        aria-haspopup="dialog"
        title="Share"
        className={`grid h-8 w-8 shrink-0 cursor-pointer place-items-center rounded-full border border-[var(--line-hairline-30)] text-[var(--base-gray-400)] hover:bg-[var(--line-hairline-10)] ${FOCUS}`}
      >
        <Share size={20} aria-hidden="true" />
      </button>
    ) : variant === "inline" ? (
      <button
        type="button"
        onClick={open}
        aria-haspopup="dialog"
        className={`inline-flex min-h-8 cursor-pointer items-center gap-1 rounded-[16px] px-2 text-[12px] font-light leading-none text-[var(--text-secondary)] hover:bg-[var(--line-hairline-10)] hover:text-[var(--text-primary)] ${FOCUS}`}
      >
        <Share size={16} aria-hidden="true" />
        Share
      </button>
    ) : (
      <button
        type="button"
        onClick={open}
        aria-haspopup="dialog"
        className={`inline-flex cursor-pointer items-center gap-2 rounded-[var(--radius-pill)] px-4 py-2.5 text-[13px] font-medium text-[var(--text-secondary)] hover:bg-[var(--line-hairline-10)] ${FOCUS}`}
      >
        <ShareNetwork size={16} aria-hidden="true" />
        Share
      </button>
    );

  return (
    <>
      {trigger}
      <dialog
        ref={dialogRef}
        aria-labelledby={titleId}
        // A click on the backdrop lands on the dialog element itself.
        onClick={(e) => {
          if (e.target === dialogRef.current) dialogRef.current?.close();
        }}
        className="m-auto max-h-[90dvh] w-[min(390px,calc(100vw-2rem))] overflow-y-auto rounded-[20px] bg-[var(--surface-app)] p-0 text-[var(--text-primary)] shadow-[var(--shadow-sheet)] backdrop:bg-[var(--overlay-scrim-25)]"
      >
        {isOpen ? (
          <>
            <div className="mt-6 flex h-7 items-center justify-between px-6">
              <ShareFat size={28} weight="fill" aria-hidden="true" className="shrink-0" />
              <h2 id={titleId} className="text-[16px] font-bold leading-none">
                Share to…
              </h2>
              <button
                type="button"
                onClick={() => dialogRef.current?.close()}
                aria-label="Close"
                className={`-my-2 -mr-2 grid h-11 w-11 shrink-0 cursor-pointer place-items-center rounded-full hover:bg-[var(--line-hairline-10)] ${FOCUS}`}
              >
                <X size={28} aria-hidden="true" />
              </button>
            </div>

            <div className="px-6 pb-8 pt-[22px]">
              <div className="rounded-[16px] border border-[var(--line-hairline-30)] p-4">
                <p className="line-clamp-3 text-[14px] font-bold leading-[21px]">{title}</p>
                {excerpt || image ? (
                  <>
                    <hr className="my-3 border-0 border-t border-[var(--line-hairline-30)]" />
                    {/* QA-070, Figma "Share to" (1731:1571): the picture sits
                        as a square to the left of the excerpt — the review's
                        photo, else the product's, else the site card. A plain
                        img: the site card is a local file the image loader
                        does not serve. */}
                    <div className="flex items-start gap-3">
                      {image ? (
                        // eslint-disable-next-line @next/next/no-img-element
                        <img
                          src={image}
                          alt=""
                          data-share-preview-image
                          loading="lazy"
                          className={`h-[100px] w-[100px] shrink-0 rounded-[12px] ${
                            image === FALLBACK_SHARE_IMAGE
                              ? "bg-[var(--accent-primary)] object-contain"
                              : "bg-[var(--surface-card)] object-cover"
                          }`}
                        />
                      ) : null}
                      {excerpt ? (
                        <p className="line-clamp-5 min-w-0 flex-1 whitespace-pre-line text-[12px] font-light leading-[18px] [overflow-wrap:anywhere]">
                          {excerpt}
                        </p>
                      ) : null}
                    </div>
                  </>
                ) : null}
              </div>

              <hr className="mt-3 border-0 border-t border-[var(--line-hairline-30)]" />
              {caption ? (
                <p className="mt-3 text-[10px] font-light leading-[10px] text-[var(--text-primary)]">{caption}</p>
              ) : null}

              <ul aria-label="Share to" className="-mx-6 mt-[22px] flex gap-4 overflow-x-auto px-6 pb-1 [scrollbar-width:none]">
                {shareDestinations(touch).map((d) => {
                  const { Icon, colour } = MARK[d.id];
                  return (
                    <li key={d.id} className="shrink-0">
                      <a
                        href={url ? destinationHref(d.id, url, title) : undefined}
                        target="_blank"
                        rel="noopener noreferrer"
                        onClick={() => onShared?.()}
                        className={`group flex w-12 flex-col items-center no-underline ${FOCUS}`}
                      >
                        <span className={TILE}>
                          <Icon size={32} weight="fill" aria-hidden="true" style={{ color: colour }} />
                        </span>
                        <span className={TILE_LABEL}>{d.label}</span>
                      </a>
                    </li>
                  );
                })}
              </ul>

              <div className="mt-6 flex gap-4">
                <button type="button" onClick={copy} className={`group flex w-12 cursor-pointer flex-col items-center ${FOCUS}`}>
                  <span className={TILE}>
                    {status === "copied" ? (
                      <Check size={28} weight="bold" aria-hidden="true" className="text-[var(--accent-success)]" />
                    ) : (
                      <LinkSimple size={28} aria-hidden="true" />
                    )}
                  </span>
                  <span className={`${TILE_LABEL} whitespace-nowrap`}>{status === "failed" ? "Copy link" : copyLabel(status)}</span>
                </button>
                {systemShare ? (
                  <button type="button" onClick={more} className={`group flex w-12 cursor-pointer flex-col items-center ${FOCUS}`}>
                    <span className={TILE}>
                      <DotsThree size={28} weight="bold" aria-hidden="true" />
                    </span>
                    <span className={TILE_LABEL}>More</span>
                  </button>
                ) : null}
              </div>

              <label className="sr-only" htmlFor={`${titleId}-url`}>
                Link to share
              </label>
              <input
                id={`${titleId}-url`}
                ref={inputRef}
                readOnly
                value={url}
                onFocus={(e) => e.currentTarget.select()}
                className={
                  status === "failed"
                    ? "mt-4 h-11 w-full rounded-[var(--radius-sm)] bg-[var(--surface-card)] px-3 text-[16px] text-[var(--text-secondary)] shadow-[var(--shadow-hairline-inset)] outline-none focus-visible:shadow-[0_0_0_2px_var(--accent-primary)] sm:text-[14px]"
                    : "sr-only"
                }
              />

              <p aria-live="polite" className="mt-3 min-h-[18px] text-[12px] leading-[18px]">
                {status === "copied" ? (
                  <span className="text-[var(--accent-success)]">Link copied to your clipboard.</span>
                ) : status === "failed" ? (
                  <span className="text-[var(--accent-danger)]">{copyLabel("failed")}.</span>
                ) : null}
              </p>
            </div>
          </>
        ) : null}
      </dialog>
    </>
  );
}

export default ShareSheet;
