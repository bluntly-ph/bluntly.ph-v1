# Administrator / Super Admin migration

Owner decisions B–D (2026-09-28): the moderator role is gone. It is replaced by
**Administrator**, the operational role, and **Super Admin**, which adds user
management and the 2.5-star routing decision. This page covers the schema,
the data mapping, how to verify, how to roll back, and the production rollout.

**Production has not been migrated.** Nothing in this branch runs against
production, and every production step below waits for the owner's explicit
authorization.

## 1. Schema

| Migration | What it does | Reversible |
| --- | --- | --- |
| `0064_routing_enum_values` | `earn_eligible_status += pending_superadmin_routing`; `moderation_action += special_routing` (autocommit block) | enum values stay (PostgreSQL cannot drop them) |
| `0065_admin_superadmin_roles` | rebuilds `member_role` as `user, seller, administrator, super_admin` and `member_type` as `shopper, seller, administrator`; maps rows (§2); drops `users.is_super_admin` and `ck_users_super_admin_is_moderator` | yes: administrator and super_admin → moderator, `is_super_admin` restored from super_admin |
| `0066_review_special_route` | `reviews.special_route` (`honesty_fund`/`platform`), `special_routed_at`, `special_routed_by_id`; partial index on pending routing | yes |
| `0067_last_super_admin_guard` | trigger `users_keep_one_super_admin`: refuses an UPDATE or DELETE that removes the last active Super Admin; race-safe via an advisory lock | yes |

The PostgreSQL `moderator` value no longer exists in `member_role`, so no code
path, script or console can grant it.

`products.image_source = 'moderator'` is left as it is. It records image
**provenance** (supplied by a human at link-attach time), not a role, and it is
never shown in the UI.

## 2. Data mapping

Deterministic, from data the owner already set. The migration decides nobody's
authority:

| Before | After |
| --- | --- |
| `role = moderator` and `is_super_admin = true` | `super_admin` |
| `role = moderator` | `administrator` |
| `member_type = moderator` | `administrator` |
| anything else | unchanged |

`backend/tests/test_role_migration.py` runs the real migrations on a scratch
database: it seeds the old shapes, upgrades, checks the mapping, downgrades,
checks every row is back exactly, and upgrades again.

### What this would do to production (read-only inspection, 2026-09-28)

| Account | Today | After 0065 |
| --- | --- | --- |
| USR-000001 | moderator, `is_super_admin = true` (the account the old root-owner email matched) | **super_admin** |
| USR-000006 | moderator | administrator |

**Owner confirmation needed:** USR-000001 becoming the production Super Admin
follows from the flag the owner set earlier. If that is not the intended
person, change it before the rollout, or right after it from User management
with a second Super Admin in place. No personal email is written into the code
any more: `settings.root_owner_email` and its hard-coded default are gone.

## 3. Rollout to production (not executed)

Old and new builds cannot share a database. A build from before 0065 cannot
read the new role values, and a build from after it cannot read `moderator`.
The release is therefore coordinated:

1. The owner authorizes the production migration in writing.
2. Take a database backup (Supabase point-in-time recovery or `pg_dump` of `public.users`).
3. `python -m scripts.check_migration_safety`, then read what it flags. It will
   flag the DROP COLUMN and the data rewrite; both are intended.
4. Put the site in its maintenance window. Staff access is the only thing at
   risk: 2 accounts in production.
5. `cd backend && python -m alembic -x allow_production=1 upgrade head`.
6. Promote the Vercel build of this branch's merge commit.
7. Verify (§4). If anything is wrong, roll back (§5).

## 4. Verify

```sql
SELECT role, count(*) FROM users GROUP BY role;                  -- no 'moderator'
SELECT enum_range(NULL::member_role);                            -- {user,seller,administrator,super_admin}
SELECT count(*) FROM users WHERE role = 'super_admin' AND NOT is_suspended;  -- ≥ 1
SELECT tgname FROM pg_trigger WHERE tgname = 'users_keep_one_super_admin';
```

Then sign in as each staff account:
- An Administrator sees `/admin` without the Super Admin group, and `/admin/users` says "Super Admin only".
- The Super Admin sees User management and Special routing.
- `/moderate/review-queue` redirects to `/admin/review-queue`.

## 5. Roll back

`python -m alembic -x allow_production=1 downgrade 0063_seller_support_requests`,
then promote the previous build. The downgrade restores `moderator` for every
Administrator and Super Admin and sets `is_super_admin` from super_admin, so
the old build's root-owner check works again. Two things are lost on
downgrade:
- **Routing decisions:** a 2.5-star routing already recorded stays in
  `moderation_logs`, but its `special_route` column is dropped.
- **A pending review:** a review left in `pending_superadmin_routing` keeps
  that enum value, which the old build does not know. Route it before rolling
  back, or set it to `pending` by hand.

## 5a. The QA-patch migrations 0068–0070 (same release, not executed)

Production is at 0060. The branch head is `0070_vote_network_fingerprints`, and the one
`alembic upgrade head` in §3 applies 0061 to 0070 in order. The three QA-patch migrations
are additive:

| Revision | Adds | Risk |
|---|---|---|
| 0068 | indexes `ix_reviews_created_id`, `ix_reviews_wilson_created_id` (All Reviews) | a short lock on `reviews` while they build |
| 0069 | table `image_fingerprints`; partial index `ix_reviews_photo_url` | new table; photos uploaded earlier are not fingerprinted |
| 0070 | table `vote_network_fingerprints` (keyed network hashes, no IP column) | new table |
| 0071 | nullable JSONB column `products.specs` (Edit product "add spec", defense build) | none: a nullable column, no rewrite |

| 0072 | nullable `users.payout_account_name` varchar(120) (Payout details "Account name") | none: a nullable column, no rewrite |

0071 and 0072 were added on `defense-build-oct6` (2026-10-02); the branch head is now
`0072_payout_account_name`.

**0075 (session 7, 2026-10-03, branch `claude/elegant-gauss-2ikk4a`, NOT on production):**

| Revision | Adds | Risk |
|---|---|---|
| 0075 | enum value `withdrawn` on `seller_claim_status` (Seller console: Withdraw claim) | none: `ALTER TYPE … ADD VALUE IF NOT EXISTS`, autocommit block, no rewrite; 0074 code runs fine on a 0075 database |

Production is at 0074 (PR #9). As with 0071–0074: migrate production to 0075 BEFORE deploying
code that can write `withdrawn` (the ORM would otherwise fail on the first withdrawal), and only
on the owner's written authorization (§3).

**0076 (2026-10-03, same branch, NOT on production) — the Inbox and Messages:**

| Revision | Adds | Risk |
|---|---|---|
| 0076 | tables `conversations` + `conversation_messages`; enums `conversation_audience`, `conversation_topic`, `conversation_status`, `conversation_message_kind`; enum value `conversation` on `moderation_action`; COPIES every case chat (`platform_settings` rows `chat:claim:*`, `chat:appeal:*`, `chat:appeal-reviewer:*`) into conversations | low: new tables, RLS on, `anon` / `authenticated` revoked; the copy is an INSERT … SELECT that leaves the settings rows untouched. A DOWNGRADE drops everything written after 0076 (Inbox threads and, since 0076, case chat messages) — export the two tables first |

Owner decisions behind it (2026-10-03): a claim's / appeal's chat and its Inbox conversation are
ONE thread ("merge into Inbox"); sellers write to the team through New message instead of Contact
support (existing support requests stay in Queue → Support).

Before deploying 0076 code, besides migrating: create a PRIVATE Supabase Storage bucket named
`message-attachments` (attachments fail with 503 `attachments_unavailable` without it; text
messages are unaffected), and make sure `EMAIL_PROVIDER=resend` + `RESEND_API_KEY` are set if the
emailed copies of replies should actually go out (`SITE_URL` sets the link in them; default: the
first CORS origin).

**0077 (2026-10-04, same branch, NOT on production) — store ↔ product links:**

| Revision | Adds | Risk |
|---|---|---|
| 0077 | table `store_products` (store, product, status pending / approved / rejected / cancelled, who asked, who decided), enum `store_product_status`, partial unique index (one live link per store and product), enum value `store_product` on `moderation_action` | none: a new table (RLS on, API roles revoked) and an enum value; nothing existing changes |

**0078 (2026-10-04, same branch, NOT on production) — an owner gives a store up:**

| Revision | Adds | Risk |
|---|---|---|
| 0078 | enum value `store_release` on `moderation_action` (giving a store up is audited) | none: one enum value; the store goes back to unclaimed through existing columns. The downgrade is a no-op (PostgreSQL cannot drop an enum value) |

**0079 (2026-10-04, same branch, NOT on production) — admin exports are audited:**

| Revision | Adds | Risk |
|---|---|---|
| 0079 | enum value `data_export` on `moderation_action` (each Export CSV is recorded with its sections and period) | none: one enum value; the downgrade is a no-op |

**0080 (2026-10-04, same branch, NOT on production) — integration settings are audited:**

| Revision | Adds | Risk |
|---|---|---|
| 0080 | enum value `integration_change` on `moderation_action` (PayMongo keys saved / removed; the keys never appear in the log) | none: one enum value; the downgrade is a no-op |

**0081 (2026-10-04, defense-build-oct6, NOT on production) — a store can edit its answer:**

| Revision | Adds | Risk |
|---|---|---|
| 0081 | nullable column `answers.edited_at` (Figma Overlay/Store/EditAnswer 8202:22530; set by PATCH /questions/{id}/answers/{answer_id}, buyers see "Edited") | low: one nullable column, no backfill, no lock beyond the ALTER; the downgrade drops it |

**0082 (2026-10-04, defense-build-oct6, NOT on production) — a store's edited response shows "Edited":**

| Revision | Adds | Risk |
|---|---|---|
| 0082 | nullable column `seller_reviews.seller_response_edited_at` (Figma Confirm/Store/SaveResponse 8202:22699). From now on an edit keeps `seller_response_at` (the store's reply time reads it) and does not re-notify the reviewer | low: one nullable column; the downgrade drops it. Responses edited before 0082 already carry their last edit's time in `seller_response_at` (not recoverable) |

PayMongo keys need a new server secret before they can be saved: `INTEGRATION_SECRETS_KEY` (a Fernet
key, `python -c "from cryptography.fernet import Fernet;print(Fernet.generate_key().decode())"`).
Without it the API answers 503 `secret_storage_unavailable` and nothing is stored. Saving keys moves
no money: no payout path uses them.

Both new tables enable RLS and revoke `anon` and `authenticated`, as every application table
does.

**Tested locally (2026-09-30), never on production or shared TEST:**
- blank → 0070, and a two-step round trip;
- previous head → head on seeded data: 0061 seeded with PR #5's own defense seed, and 0067 with
  the current one. Every count, the summed Wilson and the summed reputation are identical, and
  the moderator became an administrator;
- `check_invariants --strict`: 26/26;
- under simulated Supabase default grants, no table is readable by the public roles;
- one migration head (`test_the_migration_chain_has_exactly_one_head`).

**Extra verification after §4:**

```sql
SELECT version_num FROM alembic_version;                          -- 0070_vote_network_fingerprints
SELECT relname, relrowsecurity FROM pg_class
 WHERE relname IN ('image_fingerprints', 'vote_network_fingerprints');   -- both true
SELECT count(*) FROM pg_indexes WHERE indexname IN ('ix_reviews_created_id',
 'ix_reviews_wilson_created_id', 'ix_reviews_photo_url', 'ix_image_fingerprints_sha256',
 'ix_image_fingerprints_uploader_id', 'ix_vote_network_author_network_created',
 'ix_vote_network_created');                                      -- 7
```

**Rollback** to 0067 drops the two tables and three indexes; no other data is touched. Set
`CLIENT_IP_SIGNING_SECRET` on production (the same value for web and API) when this ships.
Until then, votes cast through the site record no network, and nothing fails.

## 6. The first Super Admin on an empty database

TEST and local databases get their Super Admin from fixtures:
- **TEST:** the defense dataset persona `super_andrea`.
- **e2e:** the `superadmin` fixture.
- **Local:** `scripts/seed.py`'s Platform Admin.

A database with none, production included, uses the explicit bootstrap:

```bash
python -m scripts.bootstrap_super_admin --email <the owner's choice>            # dry run
python -m scripts.bootstrap_super_admin --email <the owner's choice> --apply    # TEST
python -m scripts.bootstrap_super_admin --email <…> --apply --allow-production  # production: owner only
```

It refuses when any active Super Admin already exists. Every later grant goes
through User management, audited with a human actor. It also refuses a
claimed seller, a suspended account and an unknown one. It writes a
`role_grant` audit row with `event = bootstrap`.

## 7. What changed for each role

See [ADMIN_PERMISSION_MATRIX.md](ADMIN_PERMISSION_MATRIX.md). These moved to the Super Admin:
- user search and role changes;
- the legacy user↔seller endpoint;
- membership tiers;
- naming QA testers and the priority thresholds, which were the old "root owner";
- the new 2.5-star routing queue.

Everything operational stays with Administrators. That includes the
investigation flag, which moved from User management to Reviewers.
