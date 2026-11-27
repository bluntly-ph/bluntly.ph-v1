import assert from "node:assert/strict";
import test from "node:test";
import { readFileSync } from "node:fs";

/**
 * The account menu's four owner requirements (P0.2, P0.4, P0.5, P0.12,
 * 2026-09-16), guarded at the source.
 *
 * These live in JSX this runner cannot render, and every one of them is a
 * property of the markup rather than of a pure function: a link that must not
 * exist, a control that must really submit, a button that must stay inert. The
 * repository already tests a route's exports this way
 * (`telemetry-route.test.mjs`); this is the same technique pointed at the
 * pieces a refactor would quietly undo.
 */

const read = (path) =>
  readFileSync(new URL(path, import.meta.url), "utf8").replace(/\r/g, "");

const NAV = read("../../components/site/ProfileNavPanel.tsx");
const PROFILE_PAGE = read("../../app/profile/page.tsx");
const GOOGLE = read("../../components/auth/GoogleButton.tsx");

/* ---------------------------------------------- P0.4: only real destinations */

test("the account menu offers nothing that does not exist", () => {
  for (const ghost of ["Bookmarks", "Recent reads", "Recent Reads", "/bookmarks", "/saved"]) {
    assert.ok(
      !NAV.includes(`label: "${ghost}"`) && !NAV.includes(`href: "${ghost}"`),
      `${ghost} is back in the account menu`,
    );
  }
});

test("every menu entry points at a route in the site map", () => {
  const siteMap = read("../../lib/site-map.ts");
  const hrefs = [...NAV.matchAll(/href: "(\/[^"]*)"/g)].map((m) => m[1]);
  assert.ok(hrefs.length >= 8, "the menu lost its entries");
  for (const href of hrefs) {
    assert.ok(siteMap.includes(`path: "${href}"`), `${href} is not a route in lib/site-map.ts`);
  }
});

/* ------------------------- P0.12: Admin, for Administrators and Super Admins */

test("Admin is in the menu", () => {
  assert.match(NAV, /href: "\/admin", icon: \w+, label: "Admin"/);
});

test("Admin is added only for staff (owner decisions B-D)", () => {
  assert.match(NAV, /const staff = isStaffRole\(user\?\.role\);/);
  // The entry must be appended through that flag, not rendered unconditionally.
  assert.match(NAV, /staff \? \[\.\.\.ACCOUNT_GROUP, ADMIN_ITEM\] : ACCOUNT_GROUP/);
  assert.doesNotMatch(NAV, /"moderator"/);
});

test("hiding the entry is not the boundary — the route guards itself", () => {
  const access = read("../../lib/route-access.ts");
  assert.match(access, /\/admin/);
});

/* ------------------------------------------ P0.5: log out really logs out */

test("the account menu's log out submits the server action, not a link", () => {
  assert.match(NAV, /<form action=\{logout\}/, "the account menu has no log-out form");
  assert.match(NAV, /type="submit"/, "the account menu's log out is not a submit");
  assert.match(
    NAV,
    /import \{ logout \} from "@\/app\/actions\/auth"/,
    "the account menu does not import the real action",
  );
});

/* --------------------------------- owner, 2026-09-28: the profile's controls */

test("log out lives in the side navigation only, not on the profile page", () => {
  assert.ok(!/logout/.test(PROFILE_PAGE), "the profile page has a log-out control again");
});

test("the profile's Share and Edit profile sit behind its ⋯ menu", () => {
  const menu = read("../../components/profile/ProfileMenu.tsx");
  assert.match(PROFILE_PAGE, /<ProfileMenu /);
  assert.match(menu, /label: "Share profile"/);
  assert.match(menu, /label: "Edit profile"/);
  assert.match(menu, /router\.push\("\/profile\/edit"\)/);
  // The chips the owner removed stay removed.
  assert.ok(!/href="\/earnings"/.test(PROFILE_PAGE), "the Earnings chip is back");
  assert.ok(!/href="\/profile\/edit"/.test(PROFILE_PAGE), "the Edit profile chip is back");
});

test("Feed is in the side navigation, signed in or out", () => {
  assert.match(NAV, /FEED_ITEM: Item = \{ href: "\/feed", icon: \w+, label: "Feed" \}/);
  assert.match(NAV, /ACCOUNT_GROUP[^=]*= \[\s*FEED_ITEM/);
  assert.match(NAV, /PUBLIC_GROUP[^=]*= \[\s*FEED_ITEM/);
});

test("the log-out action destroys the session server-side", () => {
  const actions = read("../../app/actions/auth.ts");
  const logout = actions.slice(actions.indexOf("export async function logout"));
  assert.match(logout, /destroySession\(\)/, "logout does not destroy the session");
});

/* ------------------------- P0.2: Continue with Google, disabled and honest */

test("the Google button is disabled and says so to assistive tech", () => {
  assert.match(GOOGLE, /disabled/);
  assert.match(GOOGLE, /aria-disabled="true"/);
});

test("the Google button navigates nowhere, under any configuration", () => {
  // Not "the disabled branch navigates nowhere" — there is no other branch.
  // The live hand-off was removed once the contract audit showed the backend
  // publishes no OAuth route: a flag-gated branch that can only 404 is not
  // readiness, it is a switch that ships a broken sign-in the moment an
  // environment variable is set.
  assert.ok(!/href=/.test(GOOGLE), "the Google button has an href");
  assert.ok(
    !/router\.push|window\.location|onClick=/.test(GOOGLE),
    "the Google button navigates",
  );
  // Comments stripped: the docblock explains at length why the flag was
  // removed, and a test that cannot tell prose from code would forbid it
  // saying so.
  const code = GOOGLE.replace(/\/\*[\s\S]*?\*\//g, "").replace(/\/\/.*$/gm, "");
  assert.ok(
    !/NEXT_PUBLIC_GOOGLE_AUTH/.test(code),
    "an env flag is back, and it can only turn on a 404",
  );
});

test("no auth screen reaches for an OAuth endpoint that does not exist", () => {
  // The whole point, checked where a reader would actually meet it.
  const screens = [
    "../../app/(auth)/login/page.tsx",
    "../../app/(auth)/signup/SignupForm.tsx",
  ];
  let checked = 0;
  for (const path of screens) {
    let source;
    try {
      source = read(path);
    } catch {
      continue;
    }
    checked += 1;
    assert.ok(!/oauth\/google/.test(source), `${path} calls an endpoint that has no route`);
  }
  assert.equal(checked, screens.length, "an auth screen was renamed and went unchecked");
});

test("the label is the one the owner asked for", () => {
  assert.match(GOOGLE, /Continue with Google/);
});
