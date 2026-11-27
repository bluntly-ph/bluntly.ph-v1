/** Email change (backend 0084): the pure pieces, so tests/frontend can run them. */

/** "j•••@gmail.com": enough to recognise an address on screen, not to read it off a shoulder. */
export function maskEmail(email: string): string {
  const [user, domain] = email.split("@");
  if (!domain) return email;
  return `${user.slice(0, 1)}${"•".repeat(Math.max(3, user.length - 1))}@${domain}`;
}

/**
 * A light check before asking the API (which validates for real): one @, something
 * on both sides, a dot in the domain, no spaces.
 */
export function emailLooksValid(value: string): boolean {
  const v = value.trim();
  return v.length <= 320 && /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(v);
}
