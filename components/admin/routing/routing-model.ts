/**
 * Screen/Admin/SpecialRouting (Figma 8178:20045) and Overlay/Routing/Track
 * (8178:20344), pure. The frame's options are "Commission" / "Honesty Fund";
 * owner decision A (2026-09-28) sets the two real destinations, Honesty Fund and
 * Platform, so the splits below are the rules' (core/constants.py: platform 40,
 * reviewer 30, Honesty Fund 30), not the frame's sample.
 */

export type Destination = "honesty_fund" | "platform";

export const DESTINATIONS: { key: Destination; label: string; meaning: string; split: [string, number][] }[] = [
  {
    key: "honesty_fund",
    label: "Honesty Fund",
    meaning: "The reviewer's share goes to the Honesty Fund, as for a Hard pass: no affiliate link. The review stays up and still counts.",
    split: [["Platform", 40], ["Fund", 60]],
  },
  {
    key: "platform",
    label: "Platform",
    meaning: "The review may carry the official affiliate link; every sale's reviewer share is kept by the platform. The Honesty Fund's 30% is unchanged.",
    split: [["Platform", 70], ["Fund", 30]],
  },
];

const HOUR = 3_600_000;

/** "4 days", "20 h", "under 1 h"; `late` from a day on (drawn in the warning colour). */
export function waiting(sinceIso: string | null | undefined, now: number): { label: string; late: boolean } {
  if (!sinceIso) return { label: "—", late: false };
  const ms = Math.max(0, now - new Date(sinceIso).getTime());
  const hours = Math.floor(ms / HOUR);
  if (hours < 1) return { label: "under 1 h", late: false };
  if (hours < 24) return { label: `${hours} h`, late: false };
  const days = Math.floor(hours / 24);
  return { label: `${days} day${days === 1 ? "" : "s"}`, late: true };
}

type Item = { escalated_at?: string | null; created_at: string; product_name?: string | null; title: string };

/** The oldest waiting item (by escalation, else creation). */
export function oldest<T extends Item>(items: T[]): T | null {
  const at = (i: Item) => new Date(i.escalated_at ?? i.created_at).getTime();
  return items.reduce<T | null>((o, i) => (o === null || at(i) < at(o) ? i : o), null);
}

/** Decisions this Manila month, and who made them ("By Zient P." or "By 2 Super Admins"). */
export function routedThisMonth(
  history: { at: string; actor_name?: string | null }[],
  now: number,
): { count: number; by: string | null } {
  const month = (ms: number) => new Date(ms).toLocaleDateString("en-CA", { timeZone: "Asia/Manila" }).slice(0, 7);
  const mine = history.filter((h) => month(new Date(h.at).getTime()) === month(now));
  const names = [...new Set(mine.map((h) => h.actor_name).filter((n): n is string => Boolean(n)))];
  return { count: mine.length, by: names.length === 0 ? null : names.length === 1 ? `By ${names[0]}` : `By ${names.length} Super Admins` };
}
