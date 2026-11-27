import assert from "node:assert/strict";
import test from "node:test";

import {
  DEFAULT_SORT,
  parseQueueFilters,
  PRIORITY_TIERS,
  queueApiQuery,
  queueHref,
  reportsApiQuery,
  tierLabel,
  tierSummary,
} from "../../components/admin/review-queue-model.ts";

/**
 * Admin priority tiers (dev note 2026-09-26) on the queue screen: the URL owns
 * the tier filter and the order, the API gets exactly what was chosen, and a
 * badge always explains itself in the server's own words.
 */

test("tier and sort come from the URL, validated against the vocabulary", () => {
  const f = parseQueueFilters(new URLSearchParams("tier=highest&sort=oldest"));
  assert.equal(f.tier, "highest");
  assert.equal(f.sort, "oldest");
  const bad = parseQueueFilters(new URLSearchParams("tier=critical&sort=random"));
  assert.equal(bad.tier, "");
  assert.equal(bad.sort, DEFAULT_SORT);
  assert.equal(DEFAULT_SORT, "tier", "the triage order is the default view");
});

test("the API is asked for the tier and the order", () => {
  const f = parseQueueFilters(new URLSearchParams("tier=low"));
  const q = new URLSearchParams(queueApiQuery(f));
  assert.equal(q.get("tier"), "low");
  assert.equal(q.get("sort"), "tier");
});

test("the Report tab keeps escalation order unless asked, so urgent reports stay on top", () => {
  const f = parseQueueFilters(new URLSearchParams("tier=high"));
  const q = new URLSearchParams(reportsApiQuery(f));
  assert.equal(q.get("sort"), "escalation");
  assert.equal(q.get("tier"), "high");
  const byTier = parseQueueFilters(new URLSearchParams("rsort=tier"));
  assert.equal(new URLSearchParams(reportsApiQuery(byTier)).get("sort"), "tier");
  assert.match(queueHref(byTier), /rsort=tier/);
});

test("links keep the tier and drop the default order", () => {
  const f = parseQueueFilters(new URLSearchParams("tier=neutral"));
  assert.match(queueHref(f), /tier=neutral/);
  assert.doesNotMatch(queueHref(f), /sort=/);
  assert.match(queueHref(f, { sort: "oldest" }), /sort=oldest/);
  assert.doesNotMatch(queueHref(f, { tier: "" }), /tier=/);
});

test("five tiers, most urgent first", () => {
  assert.deepEqual(PRIORITY_TIERS, ["highest", "high", "neutral", "low", "lowest"]);
});

test("Lowest reads as a routine spot-check, and every badge explains itself", () => {
  assert.equal(tierLabel({ tier: "lowest", routine_spot_check: true }), "Lowest · routine spot-check");
  assert.equal(tierLabel({ tier: "highest", routine_spot_check: false }), "Highest");
  const why = tierSummary({
    reasons: [
      { code: "wilson_band", label: "Wilson near threshold", detail: "…" },
      { code: "fraud_reports", label: "2 fraud reports", detail: "…" },
    ],
  });
  assert.equal(why, "Wilson near threshold + 2 fraud reports");
});
