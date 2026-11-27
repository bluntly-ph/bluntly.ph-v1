/**
 * DTI / SEC registration number *format* (QA-075) — the claim form's rule.
 *
 * The exact rule `backend/app/core/registration_format.py` enforces on the
 * server; both are held to one case table, `shared/registration-numbers.json`,
 * by a test on each side. Submit stays disabled until this passes.
 *
 * A format check only. Bluntly has no link to the DTI or SEC registries, so a
 * well-formed number proves nothing about whether the registration exists or
 * whose it is; an administrator still checks it against the shop name (Business
 * Rules §9). Nothing may say "verified" because this passed.
 *
 *   DTI  6 to 10 digits, optionally after "DTI" ("DTI-3318207"); spaces and
 *        hyphens are separators.
 *   SEC  up to three letters then 5 to 15 digits, with one optional 2-4 digit
 *        suffix after a hyphen ("2021030012345-01"); spaces ignored.
 *   Both refuse a placeholder: one digit repeated, or an ascending run.
 */

export type RegistrationKind = "dti" | "sec";

const DTI = /^[0-9]{6,10}$/;
const SEC = /^[A-Z]{0,3}[0-9]{5,15}(?:-[0-9]{2,4})?$/;
const ASCENDING = "01234567890123456789";

function normalize(kind: RegistrationKind, value: string): string {
  const raw = value.trim().toUpperCase().replace(/\s+/g, "");
  if (kind === "dti") {
    const digits = raw.replace(/-/g, "");
    return digits.startsWith("DTI") ? digits.slice(3) : digits;
  }
  return raw;
}

function isPlaceholder(digits: string): boolean {
  return digits.length > 0 && (new Set(digits).size === 1 || ASCENDING.includes(digits));
}

/** Why `value` is not a well-formed number of this kind, or null if it is. */
export function registrationFormatError(kind: string, value: string | null | undefined): string | null {
  if (kind !== "dti" && kind !== "sec") return "Choose DTI or SEC.";
  const number = normalize(kind, value ?? "");
  if (!number) return "Enter the registration number.";
  let digits: string;
  if (kind === "dti") {
    if (!DTI.test(number)) return "A DTI business name number is 6 to 10 digits.";
    digits = number;
  } else {
    if (!SEC.test(number)) {
      return "An SEC registration number is up to three letters, then 5 to 15 digits (for example CS201012345).";
    }
    digits = number.split("-", 1)[0].replace(/[^0-9]/g, "");
  }
  if (isPlaceholder(digits)) return "That looks like a placeholder, not a registration number.";
  return null;
}
