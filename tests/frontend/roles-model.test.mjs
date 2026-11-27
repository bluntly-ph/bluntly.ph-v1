import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

import { isStaffRole, isSuperAdminRole, roleLabel } from "../../lib/roles.ts";

/** Owner decisions B-D (2026-09-28): there is no moderator role. */

test("only Administrators and Super Admins are staff", () => {
  assert.equal(isStaffRole("administrator"), true);
  assert.equal(isStaffRole("super_admin"), true);
  for (const role of ["user", "seller", "moderator", "admin", "", null, undefined]) {
    assert.equal(isStaffRole(role), false, String(role));
  }
});

test("only a Super Admin is a Super Admin", () => {
  assert.equal(isSuperAdminRole("super_admin"), true);
  for (const role of ["administrator", "user", "seller", "moderator", null]) {
    assert.equal(isSuperAdminRole(role), false, String(role));
  }
});

test("roles read as words, and the retired one reads as nothing special", () => {
  assert.equal(roleLabel("administrator"), "Administrator");
  assert.equal(roleLabel("super_admin"), "Super Admin");
  assert.equal(roleLabel("user"), "Member");
  assert.equal(roleLabel("moderator"), "Member");
});

test("user management and special routing are Super Admin items (Settings link, rail)", () => {
  const nav = readFileSync(new URL("../../components/admin/AdminNav.tsx", import.meta.url), "utf8");
  const label = "Special routing";
  const item = nav.slice(nav.indexOf(`label: "${label}"`), nav.indexOf("}", nav.indexOf(`label: "${label}"`)));
  assert.match(item, /superAdminOnly: true/, `${label} is not Super Admin only`);
  assert.match(nav, /superAdmin \|\| !item\.superAdminOnly/);
  // People has no subtab row (2026-10-03): Users opens from Settings → Team,
  // and only the Super Admin is offered the link.
  // Quick actions offer it to the Super Admin only.
  assert.match(nav, /\{ label: "Manage roles", href: "\/admin\/users", superAdminOnly: true \}/);
  assert.match(nav, /QUICK_ACTIONS\.filter\(\(a\) => superAdmin \|\| !a\.superAdminOnly\)/);
  const settings = readFileSync(new URL("../../app/admin/settings/page.tsx", import.meta.url), "utf8");
  assert.match(settings, /getSuperAdminAccess\(\)/);
  assert.match(settings, /access\.allowed \? <Link href="\/admin\/users"/);
});

test("the Super Admin pages check the role on the server, not just the rail", () => {
  for (const page of ["users", "special-routing"]) {
    const src = readFileSync(new URL(`../../app/admin/${page}/page.tsx`, import.meta.url), "utf8");
    assert.match(src, /getSuperAdminAccess\(\)/, page);
    assert.match(src, /SuperAdminOnly/, page);
  }
});
