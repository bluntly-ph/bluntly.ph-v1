/**
 * Screen/Seller/StoreProfile (Figma 8209:23011) and Overlay/Store/RequestChange
 * (8209:23626): the change options, the message a request sends, and the row
 * labels. Pure, so tests/frontend can check it.
 */

export type ChangeKind = "name" | "link" | "registration" | "give_up";

export const CHANGE_OPTIONS: {
  kind: ChangeKind;
  label: string;
  hint: string;
  field?: string;
  placeholder?: string;
  note: string;
}[] = [
  {
    kind: "name",
    label: "Store name",
    hint: "The marketplace renamed the shop",
    field: "New store name",
    placeholder: "Exactly as it shows on {platform}",
    note: "A moderator checks it against the marketplace. Your reviews and ratings stay with the store.",
  },
  {
    kind: "link",
    label: "Store link",
    hint: "The shop moved to a new URL",
    field: "New store link",
    placeholder: "The shop’s page on {platform}",
    note: "A moderator checks the link opens your shop. Your reviews and ratings stay with the store.",
  },
  {
    kind: "registration",
    label: "Registration details",
    hint: "New DTI or SEC registration",
    field: "New DTI or SEC number",
    placeholder: "As printed on the certificate",
    note: "A moderator checks the new registration against your shop before it replaces the old one. Only you and moderators see it.",
  },
  {
    kind: "give_up",
    label: "Give up this store",
    hint: "Someone else runs it now",
    note: "You confirm on the next step. The store goes back to unclaimed and its new owner can claim it.",
  },
];

const SUBJECT: Record<Exclude<ChangeKind, "give_up">, string> = {
  name: "Store name change",
  link: "Store link change",
  registration: "Registration details change",
};

/** Ready to send: give up needs nothing more; the others need the new value. */
export function changeReady(kind: ChangeKind, value: string): boolean {
  if (kind === "give_up") return true;
  const v = value.trim();
  return kind === "registration" ? v.length >= 3 : v.length >= 2;
}

/** The API field each change writes (POST /sellers/{id}/change-requests). */
export const CHANGE_FIELD: Record<Exclude<ChangeKind, "give_up">, "display_name" | "store_url" | "registration"> = {
  name: "display_name",
  link: "store_url",
  registration: "registration",
};

/** One change being written in the dialog. Several go in one request (MQA-017). */
export type ChangeDraft = { kind: Exclude<ChangeKind, "give_up">; value: string; regKind?: "dti" | "sec" };

/** Ready to send: at least one change, and every chosen one filled in. */
export function changesReady(drafts: ChangeDraft[]): boolean {
  return drafts.length > 0 && drafts.every((d) => changeReady(d.kind, d.value));
}

/** The request body's `changes`: one entry per chosen change, in the dialog's order. */
export function changesPayload(drafts: ChangeDraft[]): { field: string; value: string; kind?: string }[] {
  return drafts.map((d) => ({
    field: CHANGE_FIELD[d.kind],
    value: d.value.trim(),
    ...(d.kind === "registration" ? { kind: d.regKind ?? "dti" } : {}),
  }));
}

/** "Store name and store link change", as the thread is titled (MQA-026). */
export function changesTitle(drafts: ChangeDraft[]): string {
  const labels = drafts.map((d, i) => (i === 0 ? SUBJECT[d.kind].replace(/ change$/, "") : SUBJECT[d.kind].replace(/ change$/, "").toLowerCase()));
  if (!labels.length) return "";
  return `${labels.length === 1 ? labels[0] : `${labels.slice(0, -1).join(", ")} and ${labels.at(-1)}`} change`;
}

export const CHANGE_STATUS: Record<string, { label: string; tone: "warning" | "success" | "critical" }> = {
  pending: { label: "Waiting for a moderator", tone: "warning" },
  approved: { label: "Approved", tone: "success" },
  rejected: { label: "Not approved", tone: "critical" },
};

/** "shopee.ph/jisulife.official" from a full URL; the raw text if it isn't one. */
export function linkLabel(url: string | null | undefined): string | null {
  if (!url) return null;
  try {
    const u = new URL(url);
    return `${u.host.replace(/^www\./, "")}${u.pathname === "/" ? "" : u.pathname}`.replace(/\/$/, "");
  } catch {
    return url;
  }
}

/** "DTI · ending 4821". */
export function registrationLabel(kind: string | null | undefined, last4: string | null | undefined): string | null {
  if (!kind && !last4) return null;
  const k = kind ? kind.toUpperCase() : "Registration";
  return last4 ? `${k} · ending ${last4}` : k;
}

const MANILA = "Asia/Manila";

/** "March 2026". */
export function monthYear(iso: string): string {
  return new Intl.DateTimeFormat("en-GB", { month: "long", year: "numeric", timeZone: MANILA }).format(new Date(iso));
}

/** "12 Aug 2026". */
export function dayMonthYear(iso: string): string {
  return new Intl.DateTimeFormat("en-GB", { day: "numeric", month: "short", year: "numeric", timeZone: MANILA }).format(new Date(iso));
}
