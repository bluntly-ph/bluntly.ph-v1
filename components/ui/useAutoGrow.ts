"use client";

import { useLayoutEffect, type RefObject } from "react";

/**
 * A textarea that grows with what is typed, up to `maxHeight`, then scrolls
 * (MQA-010: a long reply to a seller was squeezed into one line and could not
 * be read back before sending).
 *
 * CSS `field-sizing: content` does this in Chromium only; Safari and Firefox
 * leave the box at its first height. This measures instead, so every browser
 * behaves the same. Never wider: the box keeps its width and the text wraps.
 * Line breaks are the user's own; nothing here touches the value.
 */
export function useAutoGrow(
  ref: RefObject<HTMLTextAreaElement | null>,
  value: string,
  maxHeight = 320,
): void {
  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;
    const fit = () => {
      el.style.height = "auto";
      const cs = getComputedStyle(el);
      const border = (parseFloat(cs.borderTopWidth) || 0) + (parseFloat(cs.borderBottomWidth) || 0);
      const full = el.scrollHeight + border;
      el.style.height = `${Math.min(full, maxHeight)}px`;
      el.style.overflowY = full > maxHeight ? "auto" : "hidden";
    };
    fit();
    // A narrower window wraps the same text onto more lines.
    window.addEventListener("resize", fit);
    return () => window.removeEventListener("resize", fit);
  }, [ref, value, maxHeight]);
}
