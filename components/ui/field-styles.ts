/**
 * Public form fields — one set of classes for every bordered field outside the
 * consoles (which use components/console/fields.ts, Figma Admin/Input).
 *
 * Figma "TextField" (6808:456) and "FormField", re-read 2026-10-05:
 *   field     48px (--control-input-h), radius 12, 16px in, white, 1px border;
 *             value 16px Regular at 0.8px tracking, placeholder at 40% ink
 *   Default   border at 30% ink            (--border-input)
 *   Hover     border at 50% ink            (--border-input-hover)
 *   Focus     border #EF5821 at 80%        (--brand-500-soft)
 *   Error     border #D80027               (--accent-danger), from aria-invalid
 *   Success   border #1FAF38               (--accent-success), from data-valid
 *   Disabled  #F2F2F2 fill, 10% border, 50% text
 *   label     14px Medium on a 20px line, 8px above the field
 *   message   12px Regular on a 16px line, 8px below; an error or success
 *             message carries a glyph as well as colour (FieldMessage)
 *
 * Error is read from `aria-invalid`, so what is drawn and what a screen reader
 * hears cannot disagree. Read-only fields take the disabled fill but keep the
 * full-strength text: they are readable, just not editable.
 */
const SHAPE = [
  "public-field w-full min-w-0 rounded-[var(--radius-sm)] border border-[var(--border-input)]",
  "text-[16px] tracking-[0.8px] text-[var(--text-primary)] placeholder:text-[var(--text-muted)]",
  "outline-none transition-colors duration-[var(--duration-fast)] ease-[var(--ease-standard)]",
  "hover:border-[var(--border-input-hover)]",
  "focus:border-[var(--brand-500-soft)] focus:hover:border-[var(--brand-500-soft)]",
  "data-[valid=true]:border-[var(--accent-success)]",
  "aria-[invalid=true]:border-[var(--accent-danger)] aria-[invalid=true]:hover:border-[var(--accent-danger)] aria-[invalid=true]:focus:border-[var(--accent-danger)]",
  "[&[readonly]]:bg-[var(--surface-app)] [&[readonly]]:hover:border-[var(--border-input)]",
  "disabled:cursor-not-allowed disabled:border-[var(--border-input-disabled)] disabled:bg-[var(--surface-app)] disabled:text-[var(--text-disabled)] disabled:placeholder:text-[var(--text-disabled)] disabled:hover:border-[var(--border-input-disabled)]",
].join(" ");

/**
 * TextField's states alone — edge, focus, error, success, disabled — with no
 * size, radius or type, for a public field whose frame sets its own (a comment
 * box, a store's reply). Same Default / Hover / Focus / Error / Disabled.
 */
export const PUBLIC_EDGE_STATES = [
  "public-field border border-[var(--border-input)] caret-[var(--accent-primary)] outline-none",
  "transition-colors duration-[var(--duration-fast)] ease-[var(--ease-standard)]",
  "hover:border-[var(--border-input-hover)] focus:border-[var(--brand-500-soft)] focus:hover:border-[var(--brand-500-soft)]",
  "aria-[invalid=true]:border-[var(--accent-danger)] aria-[invalid=true]:focus:border-[var(--accent-danger)]",
  "disabled:cursor-not-allowed disabled:border-[var(--border-input-disabled)] disabled:bg-[var(--surface-app)] disabled:text-[var(--text-disabled)]",
].join(" ");

/** The default white fill. A caller with another ground swaps only this. */
export const PUBLIC_FILL = "bg-[var(--surface-card)]";

/** Every state, no fill and no size: for fields whose frame draws their own. */
export const PUBLIC_FIELD_STATES = SHAPE;

const BASE = `${SHAPE} ${PUBLIC_FILL}`;

/** Single-line input. */
export const PUBLIC_INPUT = `${BASE} h-[var(--control-input-h)] px-4`;

/** Single-line input without the fill, for TextField's tones. */
export const PUBLIC_INPUT_UNFILLED = `${SHAPE} h-[var(--control-input-h)] px-4`;

/** Multi-line input; grows from three lines. */
export const PUBLIC_TEXTAREA = `${BASE} min-h-[112px] px-4 py-3 leading-6`;

/** A native select, with room on the right for the caller's caret. */
export const PUBLIC_SELECT = `${BASE} h-[var(--control-input-h)] cursor-pointer appearance-none pl-4 pr-10`;

/** The label above a field. */
export const PUBLIC_LABEL = "text-[14px] font-medium leading-5 text-[var(--text-primary)]";

/** Label, field and message, 8px apart. */
export const PUBLIC_FIELD_STACK = "flex min-w-0 flex-col gap-2";

/** A neutral line under a field (hint, counter). */
export const PUBLIC_HINT = "text-[12px] leading-4 text-[var(--text-secondary)]";
