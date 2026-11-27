import Link from "next/link";
import {
  ArrowDownRight,
  ArrowUUpLeft,
  ArrowUpRight,
  CaretRight,
  Package,
} from "@phosphor-icons/react/dist/ssr";

import { peso } from "@/lib/dashboard";
import type { AffiliateEarnings, EarningsRange } from "@/lib/moderation";

/**
 * "Affiliate earnings" (Card/Money 7896:22710): verified commission for the
 * period with its change against the period before, what was lost to returns,
 * what is still pending by marketplace, and a bar per month (per week for 1M)
 * with verified above the axis and returned below it.
 *
 * Every figure is from the canonical affiliate store; see
 * overview_panels_service for the exact rules. An empty ledger draws flat bars
 * and zeros, not an illustration.
 */

const RANGES: EarningsRange[] = ["1M", "6M", "1Y"];
const VERSUS: Record<EarningsRange, string> = {
  "1M": "vs previous 4 weeks",
  "6M": "vs previous 6 months",
  "1Y": "vs previous year",
};
const PLATFORM: Record<string, string> = { shopee: "Shopee", lazada: "Lazada", amazon: "Amazon", other: "Other" };

function Money({ amount }: { amount: string }) {
  const [whole, decimals] = peso(amount).split(".");
  return (
    <span className="flex items-baseline whitespace-nowrap font-semibold leading-none">
      <span className="text-[32px]">{whole}</span>
      <span className="text-[20px] font-normal">.{decimals}</span>
    </span>
  );
}

/** A round axis maximum: 1, 2, 2.5 or 5 times a power of ten. */
function niceMax(value: number): number {
  if (value <= 0) return 1000;
  const power = 10 ** Math.floor(Math.log10(value));
  for (const step of [1, 2, 2.5, 5, 10]) {
    if (step * power >= value) return step * power;
  }
  return 10 * power;
}

function axisLabel(n: number): string {
  if (n === 0) return "0";
  const sign = n < 0 ? "−" : "";
  const abs = Math.abs(n);
  return `${sign}₱${abs >= 1000 ? `${+(abs / 1000).toFixed(1)}k` : Math.round(abs)}`;
}

export function AffiliateEarningsCard({ data, range }: { data: AffiliateEarnings | null; range: EarningsRange }) {
  const verified = (data?.buckets ?? []).map((b) => Number(b.verified));
  const returned = (data?.buckets ?? []).map((b) => Number(b.returned));
  const upMax = niceMax(Math.max(0, ...verified));
  const downMax = Math.max(0, ...returned) > 0 ? niceMax(Math.max(...returned)) : upMax / 20;
  const UP = 180;
  const DOWN = 46;

  return (
    <section
      aria-labelledby="earnings-heading"
      className="flex min-w-0 flex-col gap-[14px] rounded-[16px] border border-[var(--border-subtle)] bg-[var(--surface-card)] p-5"
    >
      <div className="flex items-center gap-[6px]">
        <h2 id="earnings-heading" className="text-[16px] font-semibold leading-none">
          <Link href="/admin/affiliate-links" className="inline-flex items-center gap-1 hover:text-[var(--accent-primary)]">
            Affiliate earnings
            <CaretRight size={14} className="text-[var(--text-secondary)]" />
          </Link>
        </h2>
        <span className="flex-1" />
        <nav aria-label="Period" className="flex gap-[2px] rounded-full bg-[var(--surface-app)] p-[3px]">
          {RANGES.map((r) => (
            <Link
              key={r}
              href={r === "6M" ? "/admin" : `/admin?range=${r}`}
              scroll={false}
              aria-current={r === range ? "true" : undefined}
              className={`rounded-full px-[10px] py-[3px] text-[12px] font-medium leading-none ${
                r === range
                  ? "bg-[var(--surface-card)] text-[var(--text-primary)] shadow-[var(--shadow-segment)]"
                  : "text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
              }`}
            >
              {r}
            </Link>
          ))}
        </nav>
      </div>

      {data === null ? (
        <p role="status" className="text-[13px] text-[var(--text-secondary)]">
          The affiliate ledger could not be loaded.
        </p>
      ) : (
        <div className="flex flex-col gap-6 md:flex-row md:justify-between">
          <div className="flex flex-col justify-between gap-6 md:w-[273px]">
            <div className="flex flex-col gap-1">
              <span className="flex items-center gap-[6px] text-[12px] leading-none text-[var(--text-secondary)]">
                <span className="size-2 rounded-[2px] bg-[var(--accent-primary)]" aria-hidden />
                Verified
              </span>
              <span className="flex items-center gap-[10px]">
                <Money amount={data.verified} />
                {data.delta_pct !== null ? (
                  <span
                    className={`flex items-center gap-[2px] rounded-full bg-[var(--surface-app)] py-[2px] pl-[6px] pr-2 text-[12px] font-medium leading-none ${
                      data.delta_pct >= 0 ? "text-[var(--accent-success)]" : "text-[var(--accent-danger)]"
                    }`}
                  >
                    {data.delta_pct >= 0 ? <ArrowUpRight size={12} /> : <ArrowDownRight size={12} />}
                    {Math.abs(Math.round(data.delta_pct))}%
                  </span>
                ) : null}
              </span>
              <span className="text-[12px] leading-none text-[var(--text-secondary)]">
                {data.delta_pct !== null ? VERSUS[range] : "nothing verified in the period before"}
              </span>
            </div>

            <div className="flex flex-col gap-6 md:w-[219px]">
              <div className="flex flex-col gap-2 text-[12px] leading-none">
                <p className="flex items-center gap-[6px] border-t border-[var(--border-subtle)] pb-2 pt-[10px] font-medium">
                  <ArrowUUpLeft size={16} /> Lost
                </p>
                <p className="flex items-center gap-[6px]">
                  <span className="size-2 rounded-[2px] bg-[var(--base-gray-200)]" aria-hidden />
                  <span className="flex-1 text-[var(--text-secondary)]">Returned</span>
                  {data.returned_pct !== null ? (
                    <span className="text-[var(--text-secondary)]">{data.returned_pct.toFixed(1)}%</span>
                  ) : null}
                  <span className="font-medium">{peso(data.returned)}</span>
                </p>
                <p className="flex items-center gap-[6px]" title="Returns that arrived after the commission was paid out">
                  <span className="flex-1 text-[var(--text-secondary)]">Absorbed</span>
                  <span className="font-medium">{peso(data.absorbed)}</span>
                </p>
              </div>

              <div className="flex flex-col gap-2 text-[12px] leading-none">
                <p className="flex items-center gap-[6px] border-t border-[var(--border-subtle)] pb-2 pt-[10px] font-medium">
                  <Package size={16} /> Pending · {data.pending_orders} {data.pending_orders === 1 ? "order" : "orders"}
                </p>
                {data.pending.length === 0 ? (
                  <p className="text-[var(--text-secondary)]">No orders waiting on a marketplace.</p>
                ) : (
                  data.pending.map((p) => (
                    <p key={p.platform} className="flex items-center gap-[6px]">
                      <span className="flex-1 text-[var(--text-secondary)]">{PLATFORM[p.platform] ?? p.platform}</span>
                      <span className="text-[var(--text-secondary)]">{p.orders}</span>
                      <span className="font-medium">{peso(p.amount)}</span>
                    </p>
                  ))
                )}
              </div>
            </div>
          </div>

          <figure className="flex min-w-0 flex-1 gap-2" aria-label="Verified and returned commission by period">
            <div className="relative h-[248px] w-[34px] shrink-0 text-[10px] leading-none text-[var(--text-secondary)]">
              <span className="absolute left-0 top-[45px]">{axisLabel(upMax)}</span>
              <span className="absolute left-0 top-[110px]">{axisLabel(upMax / 2)}</span>
              <span className="absolute left-0 top-[174px]">0</span>
              <span className="absolute left-0 top-[203px]">{axisLabel(-downMax)}</span>
            </div>
            <div className="relative flex h-[248px] min-w-0 flex-1 items-start gap-[14px]">
              <span className="absolute inset-x-0 top-[51px] h-px bg-[var(--border-subtle)]" aria-hidden />
              <span className="absolute inset-x-0 top-[116px] h-px bg-[var(--border-subtle)]" aria-hidden />
              {(data.buckets ?? []).map((b, i) => {
                const last = i === data.buckets.length - 1;
                const up = Math.round((Number(b.verified) / upMax) * (UP - 51));
                const down = Math.min(DOWN, Math.round((Number(b.returned) / downMax) * 29));
                return (
                  <div key={b.start} className="relative flex h-full min-w-0 flex-1 flex-col items-center">
                    <div className="flex h-[180px] w-full flex-col justify-end">
                      <div
                        className={`w-full rounded-t-[6px] bg-[var(--accent-primary)] ${last ? "" : "opacity-85"}`}
                        style={{ height: up }}
                        title={`${b.label}: ${peso(b.verified)} verified`}
                      />
                    </div>
                    <div className="h-px w-full bg-[var(--disabled-text)]" aria-hidden />
                    <div className="flex h-[46px] w-full flex-col">
                      <div
                        className="w-full rounded-b-[6px] bg-[var(--base-gray-200)]"
                        style={{ height: down }}
                        title={`${b.label}: ${peso(b.returned)} returned`}
                      />
                    </div>
                    <span className={`text-[10px] leading-none ${last ? "text-[var(--text-primary)]" : "text-[var(--text-secondary)]"}`}>
                      {b.label}
                    </span>
                    <span className="sr-only">{`${peso(b.verified)} verified, ${peso(b.returned)} returned`}</span>
                  </div>
                );
              })}
            </div>
          </figure>
        </div>
      )}
    </section>
  );
}
