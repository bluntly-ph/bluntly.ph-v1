import { payoutRing } from "@/components/dashboard/contributor-model";

/**
 * Chart/Threshold ring (Figma 7842:9432): 208px, a 16.64px band (8% of the
 * ring) on the app-grey track. Commission (brand orange) runs clockwise from
 * the top, then the Honesty Fund (blue), with a small gap between the arcs.
 * Below the minimum each arc is its share of the minimum, so the track left
 * over is what is still to go (Screen/Payout/Locked 7840:9462).
 */
const SIZE = 208;
const BAND = 16.64;
const R = (SIZE - BAND) / 2;
const C = 2 * Math.PI * R;
// Round caps reach half a band past each end; this leaves ~6px of air between arcs.
const GAP = BAND + 6;

function Arc({ start, length, colour }: { start: number; length: number; colour: string }) {
  const visible = Math.max(length * C - GAP, 0.01);
  return (
    <circle
      cx={SIZE / 2}
      cy={SIZE / 2}
      r={R}
      fill="none"
      stroke={colour}
      strokeWidth={BAND}
      strokeLinecap="round"
      strokeDasharray={`${visible} ${C}`}
      strokeDashoffset={-(start * C + GAP / 2)}
    />
  );
}

export function PayoutRing({
  commission,
  honestyFund,
  minimum,
  sent = false,
  children,
}: {
  commission: string;
  honestyFund: string;
  minimum: string;
  /**
   * A request is open (Screen/Payout/Requested 7855:11171): one full arc for
   * the amount requested. A payout records no commission/Honesty Fund split,
   * so none is drawn.
   */
  sent?: boolean;
  children: React.ReactNode;
}) {
  const ring = sent ? { commission: 1, honestyFund: 0 } : payoutRing(commission, honestyFund, minimum);
  return (
    <div className="relative grid size-[208px] shrink-0 place-items-center">
      <svg width={SIZE} height={SIZE} viewBox={`0 0 ${SIZE} ${SIZE}`} aria-hidden className="absolute inset-0 -rotate-90">
        <circle cx={SIZE / 2} cy={SIZE / 2} r={R} fill="none" stroke="var(--surface-app)" strokeWidth={BAND} />
        {ring.commission > 0 ? <Arc start={0} length={ring.commission} colour="var(--accent-primary)" /> : null}
        {ring.honestyFund > 0 ? (
          <Arc start={ring.commission} length={ring.honestyFund} colour="var(--chart-honesty-fund)" />
        ) : null}
      </svg>
      <div className="relative flex flex-col items-center gap-1 text-[var(--text-primary)]">{children}</div>
    </div>
  );
}
