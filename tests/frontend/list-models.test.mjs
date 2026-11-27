import assert from "node:assert/strict";
import test from "node:test";

import {
  applyAppeals,
  applyClaims,
  applyCycles,
  applyImports,
  applyMonths,
  applyPayouts,
  monthState,
  shortfall,
  registrationLabel,
  registrationNumber,
  wantsDecidedAppeals,
} from "../../components/admin/list-models.ts";

const day = (d) => `2026-10-${String(d).padStart(2, "0")}T00:00:00Z`;

test("claims: registration, marketplace, search and sort", () => {
  const rows = [
    { created_at: day(1), seller_display_name: "Zeta Store", seller_platform: "shopee", registration_kind: "dti", registration_number: "123", claimant: { display_name: "Ana" } },
    { created_at: day(3), seller_display_name: "Alpha Shop", seller_platform: "lazada", registration_kind: "sec", registration_number: "CS1", marketplace_shop_name: "alpha.ph" },
    { created_at: day(2), seller_display_name: "Mid Store", seller_platform: "shopee", registration_kind: null, registration_number: null },
  ];
  // First in, first out unless asked otherwise.
  assert.deepEqual(applyClaims([...rows], {}).map((r) => r.seller_display_name), ["Zeta Store", "Mid Store", "Alpha Shop"]);
  assert.deepEqual(applyClaims([...rows], { sort: "newest" }).map((r) => r.seller_display_name), ["Alpha Shop", "Mid Store", "Zeta Store"]);
  assert.deepEqual(applyClaims([...rows], { sort: "store" }).map((r) => r.seller_display_name), ["Alpha Shop", "Mid Store", "Zeta Store"]);
  assert.deepEqual(applyClaims([...rows], { reg: "none" }).map((r) => r.seller_display_name), ["Mid Store"]);
  assert.deepEqual(applyClaims([...rows], { market: "shopee", reg: "dti" }).map((r) => r.seller_display_name), ["Zeta Store"]);
  assert.deepEqual(applyClaims([...rows], { q: "ALPHA.PH" }).map((r) => r.seller_display_name), ["Alpha Shop"]);
  assert.deepEqual(applyClaims([...rows], { q: "ana" }).map((r) => r.seller_display_name), ["Zeta Store"]);
});

test("appeals: status (proof = substantiation requested), rating, lowest first", () => {
  const rows = [
    { created_at: day(1), status: "open", review_rating: 2, seller_name: "A", reason: "Never ordered" },
    { created_at: day(2), status: "substantiation_requested", review_rating: 1, seller_name: "B", reason: "Fake", reviewer: { display_name: "Rico" } },
    { created_at: day(3), status: "open", review_rating: 3, seller_name: "C", reason: "Wrong store" },
  ];
  assert.deepEqual(applyAppeals([...rows], { status: "proof" }).map((r) => r.seller_name), ["B"]);
  assert.deepEqual(applyAppeals([...rows], { rating: "3" }).map((r) => r.seller_name), ["C"]);
  assert.deepEqual(applyAppeals([...rows], { sort: "rating" }).map((r) => r.seller_name), ["B", "A", "C"]);
  assert.deepEqual(applyAppeals([...rows], { q: "rico" }).map((r) => r.seller_name), ["B"]);
  assert.equal(wantsDecidedAppeals({ status: "upheld" }), true);
  assert.equal(wantsDecidedAppeals({ status: "open" }), false);
});

test("payouts: amount bands and order", () => {
  const rows = [
    { amount: "499.99", created_at: day(3), display_name: "Ana", payout_id: "po_1" },
    { amount: "500.00", created_at: day(1), display_name: "Ben", payout_id: "po_2" },
    { amount: "2500", created_at: day(2), username: "cara", payout_id: "po_3" },
  ];
  assert.deepEqual(applyPayouts([...rows], {}).map((r) => r.payout_id), ["po_2", "po_3", "po_1"]);
  assert.deepEqual(applyPayouts([...rows], { sort: "highest" }).map((r) => r.payout_id), ["po_3", "po_2", "po_1"]);
  assert.deepEqual(applyPayouts([...rows], { amount: "under500" }).map((r) => r.payout_id), ["po_1"]);
  assert.deepEqual(applyPayouts([...rows], { amount: "500to2000" }).map((r) => r.payout_id), ["po_2"]);
  assert.deepEqual(applyPayouts([...rows], { q: "PO_3" }).map((r) => r.payout_id), ["po_3"]);
});

test("Honesty Fund cycles and affiliate months / imports", () => {
  const cycles = [
    { month: "2026-08", status: "distributed", pool: "100" },
    { month: "2026-10", status: "collecting", pool: "50" },
    { month: "2026-09", status: "not_distributed", pool: "300" },
  ];
  assert.deepEqual(applyCycles([...cycles], {}).map((c) => c.month), ["2026-10", "2026-09", "2026-08"]);
  assert.deepEqual(applyCycles([...cycles], { sort: "pool" }).map((c) => c.month), ["2026-09", "2026-08", "2026-10"]);
  assert.deepEqual(applyCycles([...cycles], { status: "not_distributed" }).map((c) => c.month), ["2026-09"]);

  const months = [
    { cycle_month: "2026-07", net: "100", remitted: "100", status: "remitted" },
    { cycle_month: "2026-08", net: "200", remitted: "150", status: "remitted" },
    { cycle_month: "2026-09", net: "80", remitted: null, status: "awaiting_remittance" },
  ];
  assert.equal(shortfall(months[1]), 50);
  assert.deepEqual(months.map(monthState), ["settled", "short", "waiting"]);
  assert.deepEqual(applyMonths([...months], { sort: "shortfall" }).map((m) => m.cycle_month), ["2026-09", "2026-08", "2026-07"]);
  assert.deepEqual(applyMonths([...months], { status: "short" }).map((m) => m.cycle_month), ["2026-08"]);

  const imports = [
    { imported_at: day(1), filename: "shopee-aug.csv", unattributed: 4 },
    { imported_at: day(2), filename: "lazada-sep.csv", unattributed: 9 },
  ];
  assert.deepEqual(applyImports([...imports], {}).map((i) => i.filename), ["lazada-sep.csv", "shopee-aug.csv"]);
  assert.deepEqual(applyImports([...imports], { sort: "unattributed" }).map((i) => i.unattributed), [9, 4]);
  assert.deepEqual(applyImports([...imports], { q: "shopee" }).map((i) => i.filename), ["shopee-aug.csv"]);
});

test("registration reads the kind once (Figma 7992:11327 \"DTI 3482917\")", () => {
  assert.equal(registrationLabel("dti", "DTI-2718281"), "DTI 2718281");
  assert.equal(registrationLabel("sec", "SEC CS201918442"), "SEC CS201918442");
  assert.equal(registrationLabel("dti", "3482917"), "DTI 3482917");
  assert.equal(registrationNumber("dti", null), "—");
  assert.equal(registrationNumber("dti", "DTI"), "DTI");
});
