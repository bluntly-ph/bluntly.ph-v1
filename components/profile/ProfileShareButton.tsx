"use client";

import { useRef } from "react";
import { Export } from "@phosphor-icons/react/dist/ssr";

import { ShareSheet, type ShareSheetHandle } from "@/components/share/ShareSheet";

/**
 * The profile panel's 20px Export control (Figma 5446:5891). Shares the
 * public profile address — `/u/{id}`, not the owner's private `/profile`.
 *
 * QA-024: it opens the app's own share sheet, like every other Share on the
 * site (the system sheet is "More options…" inside it). It used to hand
 * straight to the system sheet on a phone and copy silently on a desktop, so
 * the same button behaved differently from one device to the next.
 */
export function ProfileShareButton({ name, path }: { name: string; path: string }) {
  const sheet = useRef<ShareSheetHandle>(null);

  return (
    <>
      <button
        type="button"
        onClick={() => sheet.current?.open()}
        aria-label="Share this profile"
        aria-haspopup="dialog"
        className="grid h-11 w-11 cursor-pointer place-items-center rounded-full text-[var(--text-primary)] hover:bg-[var(--line-hairline-10)] focus-visible:outline focus-visible:outline-2 focus-visible:outline-[var(--accent-primary)]"
      >
        <Export size={20} aria-hidden="true" />
      </button>
      <ShareSheet path={path} title={`${name} on bluntly`} variant="none" handle={sheet} />
    </>
  );
}

export default ProfileShareButton;
