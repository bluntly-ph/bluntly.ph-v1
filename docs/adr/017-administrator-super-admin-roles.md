# ADR-017: Administrator and Super Admin replace moderator; Super Admin routes 2.5-star "It depends"

- **Status:** Accepted / implemented on `feat/admin-superadmin-architecture`
  (2026-09-28). Supersedes the staff model of ADR/0038, which had
  `role = moderator` plus an `is_super_admin` column plus a hard-coded
  root-owner email. Production not migrated; see
  `docs/ADMIN_SUPERADMIN_MIGRATION.md`.
- **Context:** The owner decided four things:
  - **A.** A 2.5★ "It depends" review escalates to a Super Admin, who alone
    routes it to the HONESTY FUND or the PLATFORM.
  - **B.** There is no moderator role; it is replaced by ADMINISTRATOR.
  - **C.** An Administrator runs operational approvals but no user management.
  - **D.** A SUPER_ADMIN inherits everything an Administrator does, manages
    users and roles, makes the 2.5 routing decision, and can never be the
    last one removed.

  The old model encoded authority three ways: a role, a flag no API wrote, and
  an email in the code. Only one person could appoint staff, and adding a
  second Super Admin was impossible by design.

## Decision

1. **One source of truth: `users.role`.** The values are
   `user | seller | administrator | super_admin`.
   - `require_staff` admits both staff roles; `require_super_admin` admits one.
   - Both read the database row on every request, never a token claim.
   - The flag, its check constraint and `settings.root_owner_email` are removed
     (migration 0065 maps the data deterministically).
2. **User management belongs to the Super Admin.** That covers user search,
   role changes, the legacy user↔seller endpoint, membership tiers, the QA
   tester list and the priority thresholds.
   - Administrators keep every operational queue.
   - The investigation flag (§11) is operational, so it moved to the Reviewers
     screen, which Administrators still reach.
3. **The last active Super Admin cannot be removed.**
   - The service serialises every role change on one transaction-scoped
     advisory lock, then counts.
   - A database trigger (0067) refuses the same through any other path, on the
     same lock.
   - A reset that deliberately wipes accounts says so with
     `SET LOCAL bluntly.allow_no_super_admin = 'on'`.
   - An empty database gets its first Super Admin only through the explicit
     `scripts/bootstrap_super_admin.py`.
4. **2.5★ "It depends" is escalated, not guessed.**
   - The administrator's earnings approval sets `pending_superadmin_routing`
     (audited `escalate`).
   - A thread update into 2.5★ does the same and switches the link off.
   - A Super Admin sets `reviews.special_route`:
     - **HONESTY FUND** puts the thread on the fund track (`honesty_fund`,
       no link);
     - **PLATFORM** puts it on the commission route (`approved`, a link may be
       attached), and `earnings.split_for_review` moves the reviewer's 30% to
       the platform's share. The fund's 30% is untouched.
   - The decision is audited (`special_routing`) and idempotent for the same
     destination. It is final otherwise (409), and a row lock makes concurrent
     submissions decide once.
   - A sale attributed to a thread still waiting is **held**, not credited.
     The CSV import dedupes by file and line, and the lifecycle import retries
     unreconciled completed sales, so the sale is recognised once routed.
   - The route clears when the thread moves off 2.5★.
5. **The console is `/admin`.** `/moderate/*` redirects there permanently.
   The Super Admin sections sit in the same console, in a rail group only a
   Super Admin sees. Each page also checks the role on the server.

## Consequences

- An old build cannot read the new role values, and a new build cannot read
  `moderator`. The production rollout is therefore a coordinated release,
  documented and not executed.
- **PLATFORM's accounting effect is an interpretation, to confirm.** The
  owner named the destination but not its arithmetic. The reviewer's share
  going to the platform mirrors how the fund track moves the same share, and
  it leaves the fund's own share alone. Changing it is one function
  (`reviewer_routes_to_platform`).
- **Held sales need a second import to be recognised** once their thread is
  routed. The Special Routing page says so.
- Every new privileged surface is covered server-side:
  - `test_admin_user_management.py`: matrix, spoofed claims, last Super Admin,
    concurrency, bootstrap;
  - `test_special_routing_api.py`;
  - `test_role_migration.py`: real migrations, forward and back;
  - `e2e/admin-journeys.spec.ts`: 16 journeys.
