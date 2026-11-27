/**
 * Overlay/Store/Account (Figma 8232:25342) "Change password": the three fields'
 * rules, checked before anything is sent (the API checks again). Pure, so
 * tests/frontend can check it.
 */

/** The three password fields: untouched means "not changing it". */
export function passwordCheck(current: string, next: string, repeat: string): { wanted: boolean; problem: string | null } {
  const wanted = Boolean(current || next || repeat);
  if (!wanted) return { wanted, problem: null };
  if (!current) return { wanted, problem: "Enter your current password." };
  if (next.length < 10) return { wanted, problem: "The new password needs at least 10 characters." };
  if (next !== repeat) return { wanted, problem: "The two new passwords don't match." };
  if (next === current) return { wanted, problem: "Choose a password different from the current one." };
  return { wanted, problem: null };
}
