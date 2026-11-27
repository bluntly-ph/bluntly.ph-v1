"use client";

import { useEffect, useRef, useState } from "react";
import { DotsThree, LinkSimple } from "@phosphor-icons/react";

/**
 * The ⋯ on the question page's orange bar (Figma NavBar Type=Detail, the 28px
 * DotsThree of Screen/Question 7731:15603). No frame draws what it opens; the
 * one action a question has besides those on the page is its link, so it
 * offers Copy link — the same item the review bar's menu leads with
 * (ReviewOverflowMenu), with its dismissal rules: outside tap, Escape, scroll.
 */
export function QuestionOverflowMenu({ questionId }: { questionId: string }) {
  const [open, setOpen] = useState(false);
  const [copied, setCopied] = useState(false);
  const root = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      if (!root.current?.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    const onScroll = () => setOpen(false);
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
      window.removeEventListener("scroll", onScroll);
    };
  }, [open]);

  async function copyLink() {
    try {
      await navigator.clipboard.writeText(new URL(`/questions/${questionId}`, window.location.origin).toString());
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      /* Clipboard denied: the label simply doesn't change. */
    }
    setOpen(false);
  }

  return (
    <div ref={root} className="relative">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-label="More options"
        aria-expanded={open}
        aria-haspopup="menu"
        className="grid h-10 w-10 cursor-pointer place-items-center rounded-full text-[var(--text-on-brand)] hover:bg-white/15"
      >
        <DotsThree size={28} />
      </button>
      {open ? (
        <div role="menu" className="absolute right-0 top-full z-20 mt-1 w-52 overflow-hidden rounded-[var(--radius-sm)] bg-[var(--surface-card)] py-1 shadow-[var(--shadow-card)]">
          <button
            type="button"
            role="menuitem"
            onClick={copyLink}
            className="flex w-full cursor-pointer items-center gap-2 px-4 py-2.5 text-left text-[14px] text-[var(--text-primary)] hover:bg-[var(--surface-app)]"
          >
            <LinkSimple size={18} aria-hidden />
            Copy link
          </button>
        </div>
      ) : null}
      <span aria-live="polite" className="sr-only">
        {copied ? "Link to this question copied" : ""}
      </span>
    </div>
  );
}
