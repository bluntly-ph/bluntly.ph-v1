# Integration verification

2026-09-28. Everything here was read-only. No production record, role,
environment variable or deployment was changed, no payout was sent, and no
secret was decrypted or printed.

| Integration | Checked how | Result | Owner action |
| --- | --- | --- | --- |
| **GitHub** | MCP: PR checks, job logs | PR #5 (`feat/reporting-module`) failed `Browser journeys` twice:<br>• a cross-spec race: the reporting statement journey versus br-journeys' March-1997 remittance (fixed in `460a80f`);<br>• br-journeys' hostile-input journey reloaded before its comment was saved: its check matched the comment box's own text (fixed in `746e291`, reproduced by delaying the POST).<br>From 14:33 UTC, Actions ended every new job in ~2s with no runner, including one re-run. | Check GitHub Actions billing / spending limit, then let CI run on both heads. |
| **Vercel** | MCP: project `bluntly-ph`, deployments, env var **names and targets only** | Production is `main` at `087a45b`. Preview builds of `feat/reporting-module` are READY. Production and Preview both define `API_URL`, `APP_ENV`, `CORS_ORIGINS`, `JWT_SECRET`, `PII_HASH_SALT`, `SUPABASE_*`, `PAYPAL_*`, `PAYOUT_PROVIDER`, `EMAIL_*`, `RESEND_API_KEY`, `OTP_*`, `USE_SUPABASE`, `LAZADA_POSTBACK_SECRET`. There is no `ROOT_OWNER_EMAIL` variable: the removed root-owner setting was only a code default, so removing it breaks no deployment. | None needed for this branch; it adds no environment variables. |
| **PayPal** | MCP transaction search (last 30 days); code review | 0 transactions on the connector's account. The code keeps PayPal sandbox-first: `PAYOUT_PROVIDER` defaults to `paypal_sandbox` and the base URL to `api-m.sandbox.paypal.com`. Sandbox mode refuses to submit to a non-sandbox host (`sandbox_url_mismatch`). QA test earnings are refused outright in live mode, and holders of test money are left out of live batches. `sender_batch_id` is unique per batch, and each submit carries a `PayPal-Request-Id`. | Confirm the live API's payout mode: `GET /api/v1/admin/payouts/provider` as staff. Not queried: it needs a production staff session. |
| **Supabase** | MCP | The connector asked for re-authorization partway through the session, so no further query ran. Production roles were read read-only before that (USR-000001 moderator + super-admin flag; USR-000006 moderator), recorded in [ADMIN_SUPERADMIN_MIGRATION.md](ADMIN_SUPERADMIN_MIGRATION.md). | Re-authorize the Supabase connector. TEST moves to 0067 with the merge (§ below). |
| **Figma** | MCP metadata + renders | Read at 10:46; at 14:00 the connector asked for re-authorization. See [ADMIN_FIGMA_PARITY.md](ADMIN_FIGMA_PARITY.md) and [SELLER_DASHBOARD_FIGMA_PARITY.md](SELLER_DASHBOARD_FIGMA_PARITY.md). | Re-authorize Figma (`/mcp`) to repeat the check against the live file. |
| **Google Drive / Sheets** (QA workbook) | Drive search; Sheets connector | Drive found no file with the workbook's id visible to the connected account, and the Sheets connector failed to connect (connection closed). | Share the workbook with the connected Google account, or reconnect Sheets. See [QA_CURRENT_RECONCILIATION.md](QA_CURRENT_RECONCILIATION.md). |

## TEST migration

TEST (`bluntly-ph-test`) is migrated by CI's isolated-database job, which runs
on `workflow_dispatch` or on `main`.

**TEST moves to 0067 with the merge, not before.** TEST is shared with
`main`'s CI, and 0065 rebuilds the role type. Once TEST is past `main`'s head,
`main`'s isolated-database job cannot run its `alembic upgrade head`. So the
migration comes from `main`'s own CI run after #5 and #7 are merged. A
dispatch on this branch was started at 14:15 UTC and cancelled within a minute,
before it reached TEST. While it was queued it displaced `main`'s pending
isolated-database job (run 36432246142, now "cancelled"). TEST is at `0061`
(#5's index), from #5's verification run 36420305158, so `main`'s job would fail
until #5 is merged in any case. That job runs `alembic upgrade head`
against TEST, then the suite. Its credentials live only in repository secrets,
so this container cannot reach TEST directly. The deterministic TEST Super
Admin (`super_andrea`) comes from the defense dataset: **Actions → Defense
environment → populate_test**.

Local verification of the same migrations:
- a scratch database went blank → head, seeded moderator rows, head →
  `0063` → head, with data preserved each way
  (`backend/tests/test_role_migration.py`);
- the cumulative CI database was upgraded in place (moderators became 553
  administrators and 19 super admins).
