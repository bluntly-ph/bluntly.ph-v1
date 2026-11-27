/**
 * Console form fields (Admin and Seller), one set of classes instead of a FIELD
 * string per screen. States are Figma Admin/Input and Admin/Textarea (Admin
 * Components · States 8265:27081): default border/input (30 %), hover 50 %,
 * focus brand border + 3px brand ring, error danger border + 3px danger ring
 * (driven by aria-invalid, so the visual state and what a screen reader hears
 * never disagree), disabled on the page grey with a 10 % border and 50 % text.
 */
/**
 * The states alone (edge, ring, fill, text colour), for a console field or
 * select whose screen draws its own size: Admin/Input Type=Text and Type=Select
 * Default / Hover / Focus / Error / Disabled (8265:27082–27230).
 */
export const FIELD_STATES =
  "console-field border border-[var(--border-input)] bg-[var(--surface-card)] text-[var(--text-primary)] caret-[var(--accent-primary)] outline-none placeholder:text-[var(--text-muted)] transition-[border-color,box-shadow] duration-[var(--duration-fast)] hover:border-[var(--border-input-hover)] focus:border-[var(--accent-primary)] focus:shadow-[var(--ring-field-focus)] focus:hover:border-[var(--accent-primary)] aria-[invalid=true]:border-[var(--accent-danger)] aria-[invalid=true]:shadow-[var(--ring-field-error)] aria-[invalid=true]:focus:border-[var(--accent-danger)] disabled:cursor-not-allowed disabled:border-[var(--border-input-disabled)] disabled:bg-[var(--surface-app)] disabled:text-[var(--text-disabled)]";

const BASE = `${FIELD_STATES} w-full min-w-0 rounded-[12px] text-[14px]`;

/** Single-line input, 44px (modals and overlays). */
export const FIELD_INPUT = `${BASE} h-11 px-4`;

/** Single-line input, 40px (dense settings rows). */
export const FIELD_INPUT_COMPACT = `${BASE} h-10 px-4`;

/** Multi-line input. */
export const FIELD_TEXTAREA = `${BASE} p-3 leading-[21px]`;

/** The small uppercase label above a field. */
export const FIELD_LABEL = "text-[12px] font-medium uppercase tracking-[0.04em] text-[var(--text-secondary)]";

/** The line under a field (hint, counter). */
export const FIELD_HINT = "text-[12px] text-[var(--text-secondary)]";

/** The message under a field in its error state. */
export const FIELD_ERROR = "text-[12px] text-[var(--accent-danger)]";

/**
 * A menu row: Admin/MenuItem (7958:10889). Hover the 5% ink wash, Pressed 9%;
 * Selected (aria-checked) is Medium weight with a 16px Check and NEVER a fill,
 * so hover and selected can't be mistaken for each other.
 */
export const MENU_ITEM =
  "flex w-full items-center justify-between gap-2 rounded-[10px] px-3 py-[10px] text-left text-[14px] leading-5 text-[var(--text-primary)] outline-none hover:bg-[var(--overlay-hover)] focus-visible:bg-[var(--overlay-hover)] active:bg-[var(--overlay-pressed)] aria-checked:font-medium";
