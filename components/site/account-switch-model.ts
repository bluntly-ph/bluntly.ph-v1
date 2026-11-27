/**
 * QA-061: "logging into a different account in a separate browser changes the
 * account shown in the first." Separate browsers, and separate profiles of one
 * browser, keep separate sessions; two tabs or windows of ONE profile share a
 * single sign-in cookie, as on any website, and the retest used those. What a
 * tab could not do was notice: it kept showing the old account while any
 * action from it already ran as the new one.
 *
 * So each page that knows its reader writes their handle to localStorage, and
 * every other tab of that profile hears the change (the `storage` event fires
 * only in the OTHER tabs) and says so, with a reload. Only a signed-in page
 * writes: a page that failed to load its reader must not announce a sign-out.
 */

export const ACCOUNT_KEY = "bluntly.account";

/**
 * What to tell a tab rendered for `mine` (null when signed out) when another
 * tab of its browser recorded `next`. Nothing when it is the same account, or
 * when the value was cleared.
 */
export function accountSwitchMessage(mine: string | null, next: string | null): string | null {
  const now = next?.trim();
  if (!now || now === mine?.trim()) return null;
  return `You signed in as @${now} in another tab of this browser. Anything you do here now acts as @${now}; reload to see this page as that account.`;
}
