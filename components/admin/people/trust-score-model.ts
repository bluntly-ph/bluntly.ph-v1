/**
 * The admin Trust Score override's pure helpers. Tested in
 * tests/frontend/trust-score-model.test.mjs. The score itself is always the
 * backend's (0095): nothing here computes one.
 */

/** "80.00" → "80", "72.50" → "72.5"; "—" when there is no score. */
export function formatScore(value: string | number | null | undefined): string {
  if (value === null || value === undefined || value === "") return "—";
  const n = Number(value);
  return Number.isFinite(n) ? String(Math.round(n * 100) / 100) : "—";
}

/** "72.5" → 72.5; null unless 0–100 with at most two places (the API's CHECK). */
export function parseScore(raw: string): number | null {
  const t = raw.trim();
  if (!/^\d{1,3}(\.\d{1,2})?$/.test(t)) return null;
  const n = Number(t);
  return n >= 0 && n <= 100 ? n : null;
}
