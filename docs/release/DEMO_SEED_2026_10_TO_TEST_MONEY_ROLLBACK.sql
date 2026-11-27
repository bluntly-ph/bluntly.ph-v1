-- Undo DEMO_SEED_2026_10_TO_TEST_MONEY.sql: put the demo rows back exactly as
-- DEMO_SEED_2026_10.sql left them (real-flagged, 40/30/30, the invented Lazada
-- remittance). Only for recovering from a mistaken run. Removing the four QA
-- testers is done in the app (DELETE /api/v1/admin/qa-sandbox/testers/{id}).
DO $$
DECLARE
  n integer;
BEGIN
  IF NOT EXISTS (SELECT 1 FROM moderation_logs WHERE log_id = 'mlog_demorevert2610') THEN
    RAISE EXCEPTION 'the reversal has not been applied';
  END IF;

  UPDATE commissions SET is_test = false, reviewer_share_bps = 3000,
    gross_amount = 1166.67, platform_share = 466.67, honesty_fund_share = 350.00,
    csv_source = 'DEMO-seed-2026-10', row_reference = 'DEMO-zienxt-qa_cab7b588f667',
    order_status = 'completed', platform = 'lazada', updated_at = now()
   WHERE id = '0abf02c1-1ad4-442d-b691-e5a04c4e705c' AND is_test AND csv_source = 'qa_sandbox';
  IF NOT FOUND THEN RAISE EXCEPTION 'QA credit 0abf02c1 not in the reverted state'; END IF;
  UPDATE commissions SET is_test = false, reviewer_share_bps = 3000,
    gross_amount = 1166.67, platform_share = 466.67, honesty_fund_share = 350.00,
    csv_source = 'DEMO-seed-2026-10', row_reference = 'DEMO-zienxt-qa_a1a327d464a4',
    order_status = 'completed', platform = 'lazada', updated_at = now()
   WHERE id = '9e79e63f-109f-4ad9-8039-f1bac9e15923' AND is_test AND csv_source = 'qa_sandbox';
  IF NOT FOUND THEN RAISE EXCEPTION 'QA credit 9e79e63f not in the reverted state'; END IF;

  UPDATE commissions SET is_test = false, reviewer_share_bps = 3000,
    gross_amount = 1166.67, platform_share = 466.67, honesty_fund_share = 350.00,
    csv_source = 'DEMO-seed-2026-10', row_reference = 'DEMO-' || substr(commission_id, 10) || '-sale',
    order_status = 'completed', platform = 'lazada', updated_at = now()
   WHERE commission_id IN ('com_demo_zaisias', 'com_demo_northpacificfan', 'com_demo_suvango', 'com_demo_abelli')
     AND is_test AND csv_source = 'qa_sandbox';
  GET DIAGNOSTICS n = ROW_COUNT;
  IF n <> 4 THEN RAISE EXCEPTION 'expected 4 reverted demo credits, found %', n; END IF;

  INSERT INTO commissions (commission_id, target_type, review_id, reviewer_id, reviewer_share_bps,
    gross_amount, platform_share, reviewer_share, honesty_fund_share, currency, csv_source,
    row_reference, order_status, cycle_month, platform, cleared_at, is_test)
  VALUES ('com_demo_zienxt', 'review', 'edd1375f-8f43-44b4-9276-d464634e1ae3', 'e9549322-2b5d-4f74-bcae-0c5998bff7a6', 3000,
    1166.67, 466.67, 350.00, 350.00, 'PHP', 'DEMO-seed-2026-10',
    'DEMO-zienxt-sale', 'completed', DATE '2026-10-01', 'lazada', now(), false);
  UPDATE users SET wallet_balance = wallet_balance + 350.00 WHERE id = 'e9549322-2b5d-4f74-bcae-0c5998bff7a6';

  INSERT INTO marketplace_remittances (platform, cycle_month, amount_received, received_on, reference)
  VALUES ('lazada', DATE '2026-10-01', 8166.69, DATE '2026-10-06', 'DEMO-remittance-2026-10');

  DELETE FROM moderation_logs WHERE log_id = 'mlog_demorevert2610';
END $$;
