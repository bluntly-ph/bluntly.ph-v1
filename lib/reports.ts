import "server-only";

import { apiFetch } from "./api/client";
import { ApiError } from "./api/errors";
import { getSessionToken } from "./session";
import { periodQuery, type PeriodParams } from "@/components/reports/report-model";

/**
 * The four system reports (backend/app/services/reporting, docs/REPORTING_MODULE.md).
 *
 * Every figure is computed by the API from the ledger; these types mirror the
 * response schemas and every amount stays a decimal string. Per-user data, so
 * nothing here is ever cached.
 *
 * Each read returns a result rather than throwing, so a page can tell "you may
 * not see this" (forbidden) from "the period is invalid" (invalid) from "the
 * server is unreachable" (unavailable) — three different things to say.
 */

export type ReportPeriod = {
  kind: "month" | "year" | "range";
  label: string;
  start: string;
  end: string;
  timezone: string;
  cycle_months: string[];
};

export type ReportMeta = {
  title: string;
  period: ReportPeriod;
  generated_at: string;
  currency: string;
  notes: string[];
};

export type ReportResult<T> =
  | { ok: true; report: T }
  | { ok: false; reason: "forbidden" | "not_found" | "invalid" | "unavailable"; detail?: string };

async function read<T>(path: string, period: PeriodParams, extra: Record<string, string> = {}):
  Promise<ReportResult<T>> {
  try {
    const query = periodQuery(period, extra);
    const report = await apiFetch<T>(`${path}${query ? `?${query}` : ""}`, {
      token: await getSessionToken(),
    });
    return { ok: true, report };
  } catch (error) {
    if (error instanceof ApiError) {
      if (error.status === 401 || error.status === 403) return { ok: false, reason: "forbidden" };
      if (error.status === 404) return { ok: false, reason: "not_found" };
      if (error.status === 422) return { ok: false, reason: "invalid", detail: error.message };
    }
    return { ok: false, reason: "unavailable" };
  }
}

// --------------------------------------------------------------- 4. reviewer

export type EarningsStatement = {
  meta: ReportMeta;
  reviewer: { id: string; username: string | null; display_name: string | null };
  summary: {
    lifetime_earned: string;
    earned_in_period: string;
    clearing: string;
    withdrawable: string;
    paid_lifetime: string;
    paid_in_period: string;
    in_flight: string;
    wallet_balance: string;
    minimum_cashout: string;
    can_cash_out: boolean;
  };
  reviews: {
    review_id: string | null;
    review_ref: string | null;
    title: string | null;
    product: string | null;
    verdict: string | null;
    star_rating: string | null;
    earning_status: string | null;
    marketplaces: string[];
    sales: number;
    commission_gross: string;
    reviewer_earning: string;
    cleared: string;
    clearing: string;
  }[];
  entries: {
    commission_id: string | null;
    recognised_at: string;
    cycle_month: string;
    review_title: string | null;
    product: string | null;
    marketplace: string | null;
    commission_gross: string;
    reviewer_earning: string;
    status: string;
    cleared_at: string | null;
  }[];
  entries_truncated: boolean;
  fund_distributions: { distribution_id: string | null; cycle_month: string; amount: string }[];
  payouts: {
    payout_id: string | null;
    requested_at: string;
    amount: string;
    method: string;
    destination: string | null;
    batch_id: string | null;
    reference: string | null;
    status: string;
    processed_at: string | null;
  }[];
};

export const EARNINGS_STATEMENT_PATH = "/api/v1/reports/earnings-statement";

export function getEarningsStatement(period: PeriodParams) {
  return read<EarningsStatement>(EARNINGS_STATEMENT_PATH, period);
}

// --------------------------------------------------------------- 3. seller

export type RatingBlock = {
  review_count: number;
  overall_median: number | null;
  overall_mean: number | null;
  recommendation_rate: number | null;
  distribution: Record<string, number>;
  dimensions: {
    key: string;
    label: string;
    kind: "graded" | "yes_no";
    median: number | null;
    mean: number | null;
    rate: number | null;
    answered: number;
  }[];
  responded: number;
};

export type SellerRatingSummary = {
  meta: ReportMeta;
  seller: { id: string; display_name: string; platform: string; claim_status: string };
  period_summary: RatingBlock;
  all_time_summary: RatingBlock;
  rows: {
    seller_review_id: string;
    created_at: string;
    reviewer: string | null;
    title: string | null;
    overall_rating: string;
    customer_service: number;
    packaging_quality: number;
    accuracy: boolean;
    order_completeness: boolean;
    would_recommend: boolean;
    has_store_response: boolean;
  }[];
  rows_truncated: boolean;
};

export function sellerRatingPath(sellerId: string) {
  return `/api/v1/sellers/${encodeURIComponent(sellerId)}/reports/rating-summary`;
}

export function getSellerRatingSummary(sellerId: string, period: PeriodParams) {
  return read<SellerRatingSummary>(sellerRatingPath(sellerId), period);
}

// --------------------------------------------------------------- 2. commissions

export type Totals = {
  commissions: number;
  reversals: number;
  qa_test_entries: number;
  gross: string;
  platform_share: string;
  reviewer_share: string;
  honesty_fund_share: string;
  cleared_gross: string;
  clearing_gross: string;
  by_marketplace: {
    marketplace: string;
    commissions: number;
    gross: string;
    platform_share: string;
    reviewer_share: string;
    honesty_fund_share: string;
    cleared_gross: string;
    clearing_gross: string;
  }[];
};

export type CommissionPayoutReport = {
  meta: ReportMeta;
  totals: Totals;
  remittances: {
    marketplace: string;
    cycle_month: string;
    attributed_gross: string;
    amount_received: string | null;
    difference: string | null;
    received_on: string | null;
    reference: string | null;
    status: string;
  }[];
  commissions: {
    commission_id: string | null;
    cycle_month: string;
    recognised_at: string;
    marketplace: string | null;
    sub_id: string | null;
    review_ref: string | null;
    review_title: string | null;
    product: string | null;
    reviewer: string | null;
    verdict: string | null;
    star_rating: string | null;
    order_status: string | null;
    imported_commission: string;
    reconciled_amount: string | null;
    reconciliation_status: string;
    reconciled_at: string | null;
    allocation: string;
    platform_share: string;
    reviewer_share: string;
    honesty_fund_share: string;
  }[];
  page: { total: number; limit: number; offset: number };
  payout_summary: {
    reviewer_id: string;
    reviewer: string | null;
    wallet_balance: string;
    clearing: string;
    withdrawable: string;
    threshold: string;
    eligible_for_cashout: boolean;
    payout_account_on_file: boolean;
    requested_amount: string;
    paid_in_period: string;
    latest_payout_status: string | null;
    latest_payout_batch: string | null;
    latest_payout_at: string | null;
  }[];
  payouts: {
    payout_id: string | null;
    reviewer: string | null;
    amount: string;
    method: string;
    batch_id: string | null;
    reference: string | null;
    status: string;
    requested_at: string;
    processed_at: string | null;
  }[];
  threshold: string;
  provider: { method?: string; api_base_is_sandbox?: boolean; api_submission_available?: boolean };
};

export const COMMISSIONS_PATH = "/api/v1/admin/reports/commissions-payouts";

export function getCommissionPayoutReport(period: PeriodParams, page: { limit: number; offset: number }) {
  return read<CommissionPayoutReport>(COMMISSIONS_PATH, period, {
    limit: String(page.limit),
    offset: String(page.offset),
  });
}

// --------------------------------------------------------------- 1. honesty fund

export type HonestyFundReport = {
  meta: ReportMeta;
  formula: {
    defined: boolean;
    distribution_enabled: boolean;
    holding_period_defined: boolean;
    note: string;
  };
  fund_total: string;
  fund_total_cleared: string;
  distributed_total: string;
  cycles: {
    cycle_month: string;
    commissions: number;
    fund_inflow: string;
    fund_inflow_cleared: string;
    distributed: string;
    distribution_status: string;
  }[];
  reviews: {
    review_id: string;
    review_ref: string | null;
    title: string;
    product: string | null;
    reviewer: string | null;
    verdict: string;
    star_rating: string;
    routed_at: string | null;
    routed_in_period: boolean;
    eligibility: string;
    exclusion_reason: string | null;
    photo_provided: boolean;
    weighted_helpful_votes: string;
    voter_evidence: number;
    evidence_floor: number;
    meets_evidence_floor: boolean;
    price_paid: string | null;
    honesty_score: string;
    commission_base: string;
    fund_attributable: string;
    computed_share: string | null;
    computed_share_status: string;
    distributed_amount: string;
    distribution_status: string;
  }[];
  eligible_count: number;
  excluded_count: number;
  pending_routing_count: number;
};

export const HONESTY_FUND_PATH = "/api/v1/admin/reports/honesty-fund";

export function getHonestyFundReport(period: PeriodParams) {
  return read<HonestyFundReport>(HONESTY_FUND_PATH, period);
}
