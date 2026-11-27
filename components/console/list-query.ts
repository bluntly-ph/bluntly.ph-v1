/**
 * URL helpers for console lists (ListControls): the current query plus a
 * patch, empty values dropped, so links stay short and shareable.
 */

/** A filter group; an option may carry a count, drawn after its label (Figma Admin/FilterChip). */
export type FilterGroup = { key: string; title: string; options: ([string, string] | [string, string, number])[] };

export function listHref(basePath: string, params: Record<string, string>, patch: Record<string, string> = {}): string {
  const next = { ...params, ...patch };
  const p = new URLSearchParams();
  for (const [k, v] of Object.entries(next)) if (v) p.set(k, v);
  const s = p.toString();
  return s ? `${basePath}?${s}` : basePath;
}

/** The first value of each search param, as plain strings. */
export function flatParams(sp: Record<string, string | string[] | undefined>, keys: string[]): Record<string, string> {
  const out: Record<string, string> = {};
  for (const k of keys) {
    const v = sp[k];
    const s = (Array.isArray(v) ? v[0] : v) ?? "";
    if (s) out[k] = s.slice(0, 120);
  }
  return out;
}
