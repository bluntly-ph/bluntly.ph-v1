-- Reverse the October 2026 defense demo override (owner, 2026-10-07):
-- the demo earnings go back to Vash's QA sandbox design (0059_qa_sandbox_earnings).
--
-- On 2026-10-05 the owner overrode that design for the defense: the seeded
-- earnings (DEMO_SEED_2026_10.sql) were recorded as REAL Lazada commissions
-- with a 40/30/30 split and an invented ₱8,166.69 Lazada remittance, so the
-- reports and the Honesty Fund pool counted them as real money. The demo is
-- over. This puts every demo row back on the test-money rules:
--
--   * is_test = true, reviewer_share unchanged, gross = reviewer share,
--     platform and Honesty Fund shares 0 (ck_commission_test_no_revenue),
--     csv_source 'qa_sandbox', order_status 'qa_sandbox', row_reference
--     'review:<id>' — exactly what qa_sandbox_service.credit() writes;
--   * one test earning per review (uq_commission_one_qa_test): @zienxt's two
--     reviews already carry his two original QA credits, so the third, invented
--     sale (com_demo_zienxt) is deleted and its ₱350 leaves his wallet;
--   * the invented remittance is deleted: test money is never money received.
--
-- Wallets are otherwise unchanged and every payout stays as history (all four
-- went through PayPal SANDBOX). The four demo reviewers are named QA testers
-- through the app (POST /api/v1/admin/qa-sandbox/testers, audited) — not here.
--
-- Guarded: every row must be in the state the seed left it, or nothing changes.
-- Rollback: DEMO_SEED_2026_10_TO_TEST_MONEY_ROLLBACK.sql.
DO $$
DECLARE
  n integer;
BEGIN
  IF NOT EXISTS (SELECT 1 FROM commissions WHERE csv_source = 'DEMO-seed-2026-10')
     AND NOT EXISTS (SELECT 1 FROM marketplace_remittances WHERE reference = 'DEMO-remittance-2026-10') THEN
    RAISE NOTICE 'demo seed already reverted to test money: nothing to do';
    RETURN;
  END IF;

  SELECT count(*) INTO n FROM commissions WHERE csv_source = 'DEMO-seed-2026-10' AND NOT is_test;
  IF n <> 7 THEN RAISE EXCEPTION 'expected 7 real-flagged demo rows, found %', n; END IF;

  -- @zienxt: the invented third sale breaks one-test-credit-per-review; remove it
  -- and the ₱350 it put in the wallet (still there: the ₱700 payout drew on the
  -- two QA credits).
  UPDATE users SET wallet_balance = wallet_balance - 350.00
   WHERE id = 'e9549322-2b5d-4f74-bcae-0c5998bff7a6' AND wallet_balance >= 350.00;
  IF NOT FOUND THEN RAISE EXCEPTION '@zienxt''s wallet no longer holds the ₱350 of com_demo_zienxt'; END IF;
  DELETE FROM commissions WHERE commission_id = 'com_demo_zienxt' AND csv_source = 'DEMO-seed-2026-10'
    AND reviewer_id = 'e9549322-2b5d-4f74-bcae-0c5998bff7a6' AND reviewer_share = 350.00 AND NOT is_test;
  IF NOT FOUND THEN RAISE EXCEPTION 'com_demo_zienxt not in the seeded state'; END IF;

  -- @zienxt's two original QA credits, back to what the sandbox wrote.
  UPDATE commissions SET is_test = true, reviewer_share_bps = 10000, gross_amount = reviewer_share,
    platform_share = 0, honesty_fund_share = 0, csv_source = 'qa_sandbox',
    row_reference = 'review:' || review_id, order_status = 'qa_sandbox', platform = NULL, updated_at = now()
   WHERE id IN ('0abf02c1-1ad4-442d-b691-e5a04c4e705c', '9e79e63f-109f-4ad9-8039-f1bac9e15923')
     AND csv_source = 'DEMO-seed-2026-10' AND reviewer_id = 'e9549322-2b5d-4f74-bcae-0c5998bff7a6'
     AND reviewer_share = 350.00 AND NOT is_test;
  GET DIAGNOSTICS n = ROW_COUNT;
  IF n <> 2 THEN RAISE EXCEPTION 'expected @zienxt''s 2 QA credits in the seeded state, found %', n; END IF;

  -- @zaisias, @northpacificfan, @suvango, @abelli: one demo sale each becomes
  -- one labelled test credit on the same review.
  UPDATE commissions SET is_test = true, reviewer_share_bps = 10000, gross_amount = reviewer_share,
    platform_share = 0, honesty_fund_share = 0, csv_source = 'qa_sandbox',
    row_reference = 'review:' || review_id, order_status = 'qa_sandbox', platform = NULL, updated_at = now()
   WHERE commission_id IN ('com_demo_zaisias', 'com_demo_northpacificfan', 'com_demo_suvango', 'com_demo_abelli')
     AND csv_source = 'DEMO-seed-2026-10' AND reviewer_share = 350.00 AND NOT is_test;
  GET DIAGNOSTICS n = ROW_COUNT;
  IF n <> 4 THEN RAISE EXCEPTION 'expected 4 demo sales in the seeded state, found %', n; END IF;

  -- Money in: the marketplace never paid anything for test money.
  DELETE FROM marketplace_remittances
   WHERE reference = 'DEMO-remittance-2026-10' AND platform = 'lazada' AND cycle_month = DATE '2026-10-01'
     AND amount_received = 8166.69;
  IF NOT FOUND THEN RAISE EXCEPTION 'DEMO-remittance-2026-10 not in the seeded state'; END IF;

  IF EXISTS (SELECT 1 FROM commissions WHERE csv_source = 'DEMO-seed-2026-10') THEN
    RAISE EXCEPTION 'real-flagged demo rows remain';
  END IF;

  INSERT INTO moderation_logs (log_id, moderator_id, action, notes, context)
  VALUES ('mlog_demorevert2610', NULL, 'csv_import',
    'DEMO seed reverted to QA sandbox test money (owner, 2026-10-07): Vash''s design restored',
    jsonb_build_object('reverts', 'mlog_demoseed2610', 'to_test', 6, 'deleted', 'com_demo_zienxt',
      'wallet_debit', jsonb_build_object('e9549322-2b5d-4f74-bcae-0c5998bff7a6', '350.00'),
      'remittance_deleted', 'DEMO-remittance-2026-10', 'demo', true));
END $$;
