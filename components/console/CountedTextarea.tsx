"use client";

import { useRef } from "react";

import { useAutoGrow } from "@/components/ui/useAutoGrow";

import { FIELD_ERROR, FIELD_HINT, FIELD_LABEL, FIELD_TEXTAREA } from "./fields";
import { countProblem, countState } from "./counted-model";

/**
 * A console textarea with its label and "n / max" counter (Figma field states:
 * default, focus, over the limit, disabled). Typing past `max` is allowed and
 * shows the error state; the screen keeps its submit off with
 * `countState(value, max, min).over` / `.short`, and the API enforces the same
 * limits.
 *
 * It starts at `rows` and grows with the text up to `maxHeight`, then scrolls
 * (MQA-010), so a long note or reply can be read whole before it is sent.
 */
export function CountedTextarea({
  id,
  label,
  value,
  onChange,
  max,
  min = 0,
  rows = 4,
  placeholder,
  hint,
  disabled,
  labelHidden = false,
  autoFocus,
  maxHeight = 320,
}: {
  id: string;
  label: React.ReactNode;
  value: string;
  onChange: (value: string) => void;
  max: number;
  /** Minimum non-blank characters; flagged only once something is typed. */
  min?: number;
  rows?: number;
  placeholder?: string;
  /** Left side of the line under the field; replaced by the error while there is one. */
  hint?: React.ReactNode;
  disabled?: boolean;
  labelHidden?: boolean;
  autoFocus?: boolean;
  /** Tallest it grows before scrolling, in px. */
  maxHeight?: number;
}) {
  const box = useRef<HTMLTextAreaElement>(null);
  useAutoGrow(box, value, maxHeight);
  const state = countState(value, max, min);
  const problem = countProblem(state, min);
  const describedBy = `${id}-count`;
  return (
    <div className="flex flex-col gap-2">
      <label htmlFor={id} className={labelHidden ? "sr-only" : FIELD_LABEL}>
        {label}
      </label>
      <textarea
        ref={box}
        id={id}
        value={value}
        rows={rows}
        disabled={disabled}
        autoFocus={autoFocus}
        placeholder={placeholder}
        aria-invalid={problem ? true : undefined}
        aria-describedby={describedBy}
        onChange={(e) => onChange(e.target.value)}
        className={FIELD_TEXTAREA}
      />
      <span id={describedBy} className={`flex gap-3 ${FIELD_HINT}`}>
        <span className={`flex-1 ${problem ? FIELD_ERROR : ""}`} aria-live="polite">
          {problem ?? hint}
        </span>
        <span className={`[font-variant-numeric:tabular-nums] ${state.over ? "font-medium text-[var(--accent-danger)]" : ""}`}>{state.label}</span>
      </span>
    </div>
  );
}
