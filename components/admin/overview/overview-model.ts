/**
 * The Overview v4 cards' pure parts (Screen/Admin/Overview v4, 8444:38623).
 */

/** "Jisulife Official" → "JO", "maricel.d" → "MD", "Zient" → "ZI". */
export function initials(name: string | null | undefined): string {
  const clean = (name ?? "").replace(/^@/, "").trim();
  if (!clean) return "?";
  const parts = clean.split(/[\s._-]+/).filter(Boolean);
  const letters = parts.length > 1 ? parts[0][0] + parts[1][0] : clean.slice(0, 2);
  return letters.toUpperCase();
}

/**
 * The next send date for a payout schedule that runs on `day` of every month
 * (SettingsOut.payout_day, Manila): this month's if it is today or later, else
 * next month's, clamped to the month's last day. Returned as a calendar date.
 */
export function nextMonthlyDate(day: number, today: { y: number; m: number; d: number }): { y: number; m: number; d: number } {
  const clampDay = (y: number, m: number) => Math.min(day, new Date(Date.UTC(y, m + 1, 0)).getUTCDate());
  const thisMonth = clampDay(today.y, today.m);
  if (today.d <= thisMonth) return { y: today.y, m: today.m, d: thisMonth };
  const m = (today.m + 1) % 12;
  const y = today.y + (today.m === 11 ? 1 : 0);
  return { y, m, d: clampDay(y, m) };
}

/** Today in Manila as a calendar date. */
export function manilaToday(now: number): { y: number; m: number; d: number } {
  const parts = new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Manila", year: "numeric", month: "2-digit", day: "2-digit" })
    .formatToParts(new Date(now));
  const get = (t: string) => Number(parts.find((p) => p.type === t)?.value);
  return { y: get("year"), m: get("month") - 1, d: get("day") };
}

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const WEEKDAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];

/** "Fri, 10 Oct", as the frame writes the send date (fixed names: ICU says "Sept"). */
export function shortDate(date: { y: number; m: number; d: number }, weekday = true): string {
  const dt = new Date(Date.UTC(date.y, date.m, date.d, 12));
  const dm = `${dt.getUTCDate()} ${MONTHS[dt.getUTCMonth()]}`;
  return weekday ? `${WEEKDAYS[dt.getUTCDay()]}, ${dm}` : dm;
}

type Item = { key: string; label: string; count: number | null; detail?: string | null };
type Group = { key: string; label: string; items: Item[] };

/**
 * Needs attention as v4 lays it out: Moderation, Integrity and Money in the
 * first column; Catalog and Sellers in the second. The API's groups are kept
 * as counted (needs_attention_service); only "Seller claims & appeals" moves
 * from Catalog into the frame's Sellers group, where it reads "Claims &
 * appeals". Every row the API returns is drawn, so "N open" stays the sum of
 * what is on screen. v4's "No 3D model yet" and "New seller sign-ups" are not
 * drawn: there is no 3D model and no seller sign-up to count (owner rules).
 */
export function attentionColumns(groups: Group[]): Group[][] {
  const byKey = new Map(groups.map((g) => [g.key, { ...g, items: [...g.items] }]));
  const catalog = byKey.get("catalog");
  const sellerRows = catalog ? catalog.items.filter((i) => i.key === "seller_claims_appeals") : [];
  if (catalog) catalog.items = catalog.items.filter((i) => i.key !== "seller_claims_appeals");
  const sellers: Group | undefined = sellerRows.length
    ? { key: "sellers", label: "Sellers", items: sellerRows.map((i) => ({ ...i, label: "Claims & appeals" })) }
    : undefined;
  const pick = (keys: string[]) =>
    keys.map((k) => (k === "sellers" ? sellers : byKey.get(k))).filter((g): g is Group => Boolean(g && g.items.length));
  const known = new Set(["moderation", "integrity", "money", "catalog"]);
  const extra = groups.filter((g) => !known.has(g.key) && g.items.length);
  return [pick(["moderation", "integrity", "money"]), [...pick(["catalog", "sellers"]), ...extra]];
}

/** The sum of the rows drawn; one item can sit in two rows, so it is said as a sum. */
export function attentionOpen(groups: Group[]): number {
  return groups.flatMap((g) => g.items).reduce((n, i) => n + (i.count ?? 0), 0);
}
