import assert from "node:assert/strict";
import test from "node:test";

import {
  barHeights,
  change,
  commissionArcLabels,
  compact,
  payoutRing,
  earningsLine,
  voteBars,
  pesoSplit,
  requirementValue,
  ringFraction,
  share,
  stepStates,
  stepsLine,
} from "../../components/dashboard/contributor-model.ts";

/** The contributor dashboard (Figma Screen/Dashboard 7833:9534). */

test("money splits into the whole part and the smaller cents", () => {
  assert.deepEqual(pesoSplit("1790.04"), ["₱1,790", ".04"]);
  assert.deepEqual(pesoSplit("0.00"), ["₱0", ".00"]);
  assert.deepEqual(pesoSplit("-36.5"), ["−₱36", ".50"]);
  assert.deepEqual(pesoSplit(null), ["₱0", ".00"]);
});

test("counts read like the design", () => {
  assert.equal(compact(758), "758");
  assert.equal(compact(1300), "1.3k");
  assert.equal(compact(47_000), "47k");
  assert.equal(compact(216_400), "216k");
});

test("earned and returned share one scale; any money shows", () => {
  const h = barHeights([
    { earned: "90.00", returned: "0.00" },
    { earned: "45.00", returned: "12.00" },
    { earned: "0.10", returned: "0.00" },
    { earned: "0.00", returned: "0.00" },
  ]);
  assert.deepEqual(h[0], { up: 95, down: 0 });
  assert.equal(h[1].up, 48);
  assert.equal(h[1].down, 13);
  assert.equal(h[2].up, 4);
  assert.deepEqual(h[3], { up: 0, down: 0 });
  assert.deepEqual(barHeights([{ earned: "0", returned: "0" }]), [{ up: 0, down: 0 }]);
});

test("the stepper fills reached stages and rings the next one", () => {
  assert.deepEqual(stepStates(1), ["done", "next", "upcoming", "upcoming", "upcoming"]);
  assert.deepEqual(stepStates(0), ["next", "upcoming", "upcoming", "upcoming", "upcoming"]);
  assert.deepEqual(stepStates(5), ["done", "done", "done", "done", "done"]);
});

test("requirement rings and their labels", () => {
  assert.equal(ringFraction(2, 3, false), 2 / 3);
  assert.equal(ringFraction(38, 20, true), 1);
  assert.equal(ringFraction(1, 0, false), 0); // "no strikes" not met
  assert.equal(requirementValue("receipt_reviews", 2, 3), "2/3");
  assert.equal(requirementValue("helpful_votes", 38.4, 60), "38");
  assert.equal(stepsLine([{ done: true }, { done: true }, { done: false }], "Verified Buyer"), "2 of 3 steps to Verified Buyer");
  assert.equal(stepsLine([{ done: false }], "Contributor"), "0 of 1 step to Contributor");
  assert.equal(stepsLine([], null), "The top of the ladder");
});

test("funnel shares and month-on-month change", () => {
  assert.equal(share(3000, 216000), "1.4%");
  assert.equal(share(1200, 3000), "40%");
  assert.equal(share(19, 17), null); // more helped than viewed this month: not a funnel step
  assert.equal(share(5, 0), null);
  assert.equal(change(112, 100), "+12%");
  assert.equal(change(98, 100), "−2%");
  assert.equal(change(5, 0), null);
});

test("payout ring: share of the minimum below it, of the whole above it", () => {
  // Locked (Figma 7840:9462): ₱142 + ₱44.50 of a ₱300 minimum; the rest is track.
  const locked = payoutRing("142.00", "44.50", "300");
  assert.equal(locked.met, false);
  assert.ok(Math.abs(locked.commission - 142 / 300) < 1e-9);
  assert.ok(Math.abs(locked.honestyFund - 44.5 / 300) < 1e-9);
  // Met (7840:9380): ₱1,378.04 + ₱412.00 fill the ring between them.
  const met = payoutRing("1378.04", "412.00", "300");
  assert.equal(met.met, true);
  assert.ok(Math.abs(met.commission + met.honestyFund - 1) < 1e-9);
  // Nothing yet: an empty track, not "Minimum met".
  assert.deepEqual(payoutRing("0", "0", "300"), { commission: 0, honestyFund: 0, met: false });
});

test("earnings line: nice top and points across the box", () => {
  const { points, top } = earningsLine(["0", "12.5", "27"], 100, 50);
  assert.equal(top, 30);
  assert.equal(points, "0.0,50.0 50.0,29.2 100.0,5.0");
  assert.equal(earningsLine([0, 0], 10, 10).top, 30);
});

test("vote bars share one scale; any vote shows", () => {
  assert.deepEqual(voteBars([{ up: 10, down: 1 }, { up: 5, down: 0 }]), [{ up: 80, down: 8 }, { up: 40, down: 0 }]);
  assert.deepEqual(voteBars([{ up: 0, down: 0 }]), [{ up: 0, down: 0 }]);
});

test("each commission share is labelled on its own arc, upright, only where it fits", () => {
  const parts = [
    { key: "you", value: 350 },
    { key: "fund", value: 350 },
    { key: "bluntly", value: 466.67 },
  ];
  const [you, fund, bluntly] = commissionArcLabels(parts, 196, 26, 32);
  assert.deepEqual([you.text, fund.text, bluntly.text], ["₱350.00", "₱350.00", "₱466.67"]);
  assert.ok(you.show && fund.show && bluntly.show);
  // The fund's arc sits at the bottom: its path runs counter-clockwise (sweep 0)
  // so the text is not upside down; the upper arcs run clockwise (sweep 1).
  assert.match(fund.d, / 0 0 0 /);
  assert.match(you.d, / 0 0 1 /);
  assert.match(bluntly.d, / 0 0 1 /);
  // The first arc starts just past the top (12 o'clock), after half the gap.
  const [x, y] = you.d.split(" ").slice(1, 3).map(Number);
  assert.ok(x > 98 && y < 20);
});

test("an empty or tiny share gets no label", () => {
  const [zero, tiny] = commissionArcLabels(
    [{ key: "a", value: 0 }, { key: "b", value: 1 }, { key: "c", value: 999 }], 196, 26, 32);
  assert.equal(zero.show, false);
  assert.equal(zero.d, "");
  assert.equal(tiny.show, false);
});
