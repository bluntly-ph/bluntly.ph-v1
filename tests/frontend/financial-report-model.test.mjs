import assert from "node:assert/strict";
import test from "node:test";

import {
  SECTIONS,
  generateBody,
  manilaDay,
  manilaMonth,
  monthFromSearch,
  monthLabel,
  monthOptions,
  pesoParts,
  quarterOptions,
  sectionsLabel,
  shareWidths,
  yearOptions,
} from "../../components/admin/reports/financial-model.ts";

/**
 * The Reports screen and Generate report dialog (Figma 8028:12886, 8028:13346).
 * Money stays the API's decimal string; periods are Manila calendar periods.
 */

// 2026-09-30 17:30 UTC is already 1 October in Manila.
const LATE_SEPT_UTC = Date.UTC(2026, 8, 30, 17, 30);

test("amounts split into the whole part and grey cents, never through a float", () => {
  assert.deepEqual(pesoParts("30132.5"), ["₱30,132", "50"]);
  assert.deepEqual(pesoParts("0.10"), ["₱0", "10"]);
  assert.deepEqual(pesoParts("-1120.00"), ["−₱1,120", "00"]);
  assert.deepEqual(pesoParts(null), ["—", ""]);
});

test("the month is the Manila month", () => {
  assert.equal(manilaMonth(LATE_SEPT_UTC), "2026-10");
  assert.equal(monthLabel("2026-09"), "September 2026");
  const months = monthOptions(LATE_SEPT_UTC);
  assert.equal(months.length, 12);
  assert.deepEqual(months[0], { value: "2026-10", label: "October 2026" });
  assert.deepEqual(months[10], { value: "2025-12", label: "December 2025" });
});

test("quarters and years count back from the current Manila one", () => {
  const quarters = quarterOptions(LATE_SEPT_UTC);
  assert.deepEqual(quarters[0], { value: "2026-4", label: "Q4 2026" });
  assert.deepEqual(quarters[4], { value: "2025-4", label: "Q4 2025" });
  assert.deepEqual(yearOptions(LATE_SEPT_UTC).map((y) => y.value), ["2026", "2025", "2024"]);
});

test("a malformed ?month falls back to the current month", () => {
  assert.equal(monthFromSearch("2026-08", LATE_SEPT_UTC), "2026-08");
  assert.equal(monthFromSearch(["2026-07", "x"], LATE_SEPT_UTC), "2026-07");
  for (const bad of [undefined, "2026-13", "2026-8", "Sept", "2026-08-01"]) {
    assert.equal(monthFromSearch(bad, LATE_SEPT_UTC), "2026-10");
  }
});

test("sections read like the design's table cell", () => {
  assert.equal(sectionsLabel(SECTIONS.map((s) => s.key)), "All 4");
  assert.equal(sectionsLabel(["money_out", "money_in"]), "Money in, Money out");
});

test("generated dates are Manila days", () => {
  assert.equal(manilaDay("2026-08-31T17:00:00Z"), "1 Sep 2026");
});

test("bar segments are proportions of the positive shares", () => {
  assert.deepEqual(shareWidths(["40.00", "30.00", "30.00"]), [40, 30, 30]);
  assert.deepEqual(shareWidths(["0.00", "0.00", "0.00"]), [0, 0, 0]);
  assert.deepEqual(shareWidths(["-5.00", "5.00", "15.00"]), [0, 25, 75]);
});

test("the dialog sends exactly what the API accepts, sections in print order", () => {
  const all = ["liabilities", "revenue"];
  assert.deepEqual(generateBody("month", "2026-09", { start: "", end: "" }, all), {
    kind: "month",
    year: 2026,
    month: 9,
    sections: ["revenue", "liabilities"],
  });
  assert.deepEqual(generateBody("quarter", "2026-2", { start: "", end: "" }, ["money_in"]), {
    kind: "quarter",
    year: 2026,
    quarter: 2,
    sections: ["money_in"],
  });
  assert.deepEqual(generateBody("year", "2025", { start: "", end: "" }, ["money_out"]), {
    kind: "year",
    year: 2025,
    sections: ["money_out"],
  });
  assert.deepEqual(generateBody("custom", "", { start: "2026-09-01", end: "2026-09-15" }, ["revenue"]), {
    kind: "custom",
    start_date: "2026-09-01",
    end_date: "2026-09-15",
    sections: ["revenue"],
  });
  assert.equal(generateBody("custom", "", { start: "2026-09-15", end: "2026-09-01" }, ["revenue"]), "The end date is before the start date.");
  assert.equal(generateBody("custom", "", { start: "", end: "2026-09-01" }, ["revenue"]), "Choose a start and an end date.");
  assert.equal(generateBody("month", "2026-09", { start: "", end: "" }, []), "Choose at least one section.");
});
