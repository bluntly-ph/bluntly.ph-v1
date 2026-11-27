/**
 * The character counter under a console textarea. Counts code points, as the
 * API does (Python len), so an emoji is one character on both sides.
 *
 * The field never blocks typing (no maxLength): the Figma over-limit state —
 * danger border, danger counter, "N over" — has to be reachable, and a paste
 * that runs long should be trimmed by the writer, not cut silently.
 */
export type CountState = {
  count: number;
  max: number;
  /** More characters than allowed: the field is invalid and submit stays off. */
  over: boolean;
  /** How many characters to remove (0 when within the limit). */
  excess: number;
  /** Fewer non-blank characters than required (only when a minimum is given and something was typed). */
  short: boolean;
  /** "1,020 / 1,000" */
  label: string;
};

const fmt = (n: number) => n.toLocaleString("en-PH");

export function countState(value: string, max: number, min = 0): CountState {
  const count = Array.from(value).length;
  const excess = Math.max(0, count - max);
  const trimmed = Array.from(value.trim()).length;
  return {
    count,
    max,
    over: excess > 0,
    excess,
    short: min > 0 && trimmed > 0 && trimmed < min,
    label: `${fmt(count)} / ${fmt(max)}`,
  };
}

/** The message shown in the field's error state, or null when there is none. */
export function countProblem(state: CountState, min = 0): string | null {
  if (state.over) return `${fmt(state.excess)} character${state.excess === 1 ? "" : "s"} over the limit. Shorten it to send.`;
  if (state.short) return `At least ${fmt(min)} characters.`;
  return null;
}
