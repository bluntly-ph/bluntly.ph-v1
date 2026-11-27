/**
 * Search, link and dropdown-pill states — one set of classes per Figma state
 * set, so every search box on the site draws the same Default / Hover / Focus
 * / Filled, whatever its own frame says about its size and ground.
 *
 * Each export is STATES ONLY (edge, fill, wash, caret): the caller keeps the
 * height, radius and padding its screen's frame draws. The container carries
 * the state through :focus-within, so the inner <input> never draws a ring of
 * its own — the global :focus-visible outline sits in @layer base and gives
 * way to `outline-none` here.
 *
 *  SearchField/Inline (7761:7998) — the public search box.
 *    Default   white, 1px #d1d1d1 edge, placeholder #8c8c8c
 *    Focused   1.5px #EF5821 edge (1px border + a 0.5px inset, so nothing
 *              moves), the caret in brand, the clear ✕ shown
 *  LinkField (6943:925) — "Can't find it? Paste a link".
 *    Default / Filled  the frame's frosted card, no edge
 *    Focus     1px brand edge
 *  Admin/ToolbarSearch (8270:28869) — a console list's search pill.
 *    Default   white, 1px border/subtle
 *    Hover     1px 50% ink edge, 5% ink wash
 *    Focus     white, 1px brand edge + the 3px brand halo, outside the pill
 *    Filled    1px 30% ink edge (the ✕ is the caller's)
 *  Admin/TopSearch (8265:27300) — the console top bar.
 *    Default   page grey, no edge; Hover 5% darker
 *    Focus     white, 1px brand edge + halo; Filled white, 30% ink edge
 *  Dropdown/Pill (8267:27483) — period and category pickers.
 *    Default   white, 1px border/subtle; Hover 30% ink edge + 5% wash
 *    Pressed / Open  30% ink edge + 9% wash (Open: aria-expanded)
 *    Disabled  page grey, 10% edge, 50% text
 */

const MOTION = "transition-[border-color,box-shadow,background-color] duration-[var(--duration-fast)] ease-[var(--ease-standard)]";

/** "Filled": the field holds text (placeholder hidden). */
const FILLED = "has-[input:not(:placeholder-shown)]";

/**
 * SearchField/Inline's Focused state alone, for a search whose own frame draws
 * a different resting look (the home hero on the page grey, the results page's
 * 56px bar). `focus-within` also matches the element itself, so this goes on
 * the input or on the box around it.
 */
export const SEARCH_FOCUS = `focus-within:border-[var(--accent-primary)] focus-within:shadow-[inset_0_0_0_0.5px_var(--accent-primary)] caret-[var(--accent-primary)] ${MOTION}`;

/** SearchField/Inline, Default and Focused, on its container (or the input). */
export const SEARCH_FIELD_STATES = `border border-[var(--line-search)] bg-[var(--surface-card)] ${SEARCH_FOCUS}`;

/** The input inside any of these containers. */
export const SEARCH_INPUT =
  "min-w-0 flex-1 bg-transparent text-[var(--text-primary)] caret-[var(--accent-primary)] outline-none placeholder:text-[var(--base-gray-400)] [&::-webkit-search-cancel-button]:appearance-none";

/** LinkField's edge, on its container (the frosted card stays the caller's). */
export const LINK_FIELD_STATES = `border border-transparent focus-within:border-[var(--accent-primary)] ${MOTION}`;

/** Admin/ToolbarSearch, on its container. */
export const TOOLBAR_SEARCH_STATES = [
  "border border-[var(--border-subtle)] bg-[var(--surface-card)]",
  "hover:border-[var(--border-input-hover)] hover:[background-image:linear-gradient(var(--overlay-hover),var(--overlay-hover))]",
  `${FILLED}:border-[var(--border-input)]`,
  "focus-within:border-[var(--accent-primary)] focus-within:shadow-[var(--ring-field-focus)] focus-within:[background-image:none] focus-within:hover:border-[var(--accent-primary)]",
  MOTION,
].join(" ");

/** Admin/TopSearch, on its container. */
export const TOP_SEARCH_STATES = [
  "border border-transparent bg-[var(--surface-app)]",
  "hover:[background-image:linear-gradient(var(--overlay-hover),var(--overlay-hover))]",
  `${FILLED}:border-[var(--border-input)] ${FILLED}:bg-[var(--surface-card)]`,
  "focus-within:border-[var(--accent-primary)] focus-within:bg-[var(--surface-card)] focus-within:shadow-[var(--ring-field-focus)] focus-within:[background-image:none]",
  MOTION,
].join(" ");

/** Dropdown/Pill, on the button that opens the menu. */
export const DROPDOWN_PILL_STATES = [
  "cursor-pointer border border-[var(--border-subtle)] bg-[var(--surface-card)] text-[12px] font-medium leading-4 text-[var(--text-primary)]",
  "hover:border-[var(--border-input)] hover:[background-image:linear-gradient(var(--overlay-hover),var(--overlay-hover))]",
  "active:border-[var(--border-input)] active:[background-image:linear-gradient(var(--overlay-pressed),var(--overlay-pressed))]",
  "aria-expanded:border-[var(--border-input)] aria-expanded:[background-image:linear-gradient(var(--overlay-pressed),var(--overlay-pressed))]",
  "disabled:cursor-not-allowed disabled:border-[var(--border-input-disabled)] disabled:bg-[var(--surface-app)] disabled:text-[var(--text-disabled)] disabled:[background-image:none]",
  MOTION,
].join(" ");

/** The caret inside a Dropdown/Pill: turns over while its menu is open. */
export const DROPDOWN_CARET = "shrink-0 transition-transform duration-[var(--duration-fast)] group-aria-expanded:rotate-180";
