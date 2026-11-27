import Image from "next/image";
import Link from "next/link";
import {
  CaretRight,
  ChartLine,
  ClockCounterClockwise,
  Info,
  PencilSimple,
  Shield,
  Wallet,
} from "@phosphor-icons/react/dist/ssr";

import { DashboardSelect } from "@/components/dashboard/DashboardSelect";
import { Frame, Money, Panel, ReachRings } from "@/components/dashboard/DashboardParts";
import {
  barHeights,
  compact,
  pesoSplit,
  requirementValue,
  ringFraction,
  stepsLine,
  stepStates,
} from "@/components/dashboard/contributor-model";
import type { ContributorDashboard as Data, ContributorReach } from "@/lib/dashboard";

/**
 * The contributor dashboard, built to Figma Screen/Dashboard (7833:9534;
 * meeting 2026-10-02, 3:00): three actions (Payout, History, Performance), the
 * wallet card (total balance, commission, Honesty Fund, pending), earnings
 * earned vs returned with the best-performing products, the trust stage and
 * what the next one asks for, the Honesty Score, and the reach funnel.
 *
 * Every number comes from GET /users/me/contributor, read from the ledger, the
 * view counters, votes and link clicks. Where a stage's promotion is held for
 * a moderator, the card says so instead of implying it is due.
 */

const MUTED = "text-[var(--base-gray-400)]";

function NavCard({ href, label, Icon, tint = false }: { href: string; label: string; Icon: typeof Wallet; tint?: boolean }) {
  return (
    <Link href={href} className="flex min-w-0 flex-1 flex-col gap-4 rounded-[24px] bg-[var(--surface-card)] p-[14px] transition-shadow hover:shadow-[var(--shadow-card)]">
      <span className="flex items-start">
        <span className={`grid size-10 place-items-center rounded-[12px] ${tint ? "bg-[var(--status-high-bg)] text-[var(--accent-primary)]" : "bg-[var(--surface-app)] text-[var(--text-primary)]"}`}>
          <Icon size={20} aria-hidden />
        </span>
        <span className="flex-1" />
        <CaretRight size={16} aria-hidden />
      </span>
      <span className="text-[12px] font-medium leading-none">{label}</span>
    </Link>
  );
}

/** Payout, History, Performance: also drawn, live, while the dashboard loads (Figma 7855:10750). */
export function DashboardActions() {
  return (
    <nav aria-label="Dashboard" className="mb-4 flex gap-2 rounded-[32px] bg-[var(--surface-app)] p-2">
      <NavCard href="/dashboard/transfer" label="Payout" Icon={Wallet} tint />
      <NavCard href="/dashboard/history" label="History" Icon={ClockCounterClockwise} />
      <NavCard href="/dashboard/insights" label="Performance" Icon={ChartLine} />
    </nav>
  );
}

function WalletCard({ d }: { d: Data }) {
  return (
    <Frame label="Wallet" className="px-[3px] pt-[3px]">
      <div className="rounded-[32px] bg-[var(--surface-card)] p-5">
        {/* The card's ticket notch: a 14px half-circle cut from the right edge. */}
        <div
          className="relative h-[150px] overflow-hidden rounded-[24px] bg-[var(--accent-primary)] text-white"
          style={{
            WebkitMaskImage: "radial-gradient(circle 14px at 100% 50%, transparent 13.5px, #000 14px)",
            maskImage: "radial-gradient(circle 14px at 100% 50%, transparent 13.5px, #000 14px)",
          }}
        >
          <Image
            src="/figma/dashboard/wallet-swoosh-decor.svg"
            alt=""
            width={143}
            height={87}
            className="pointer-events-none absolute left-[-3.7px] top-[64.4px] h-[87.24px] w-[143.43px] max-w-none rotate-180"
          />
          <Image
            src="/figma/dashboard/wallet-mark.svg"
            alt=""
            width={20}
            height={12}
            className="absolute right-[21.9px] top-[25.8px] h-[12.32px] w-[20.25px] rotate-180"
          />
          <p className="absolute left-5 top-[18px] text-[10px] leading-none text-white/80">Total balance</p>
          <p className="absolute left-5 top-8 flex items-baseline">
            <Money value={d.total_balance} whole="text-[32px]" cents="text-[20px] font-normal text-white/55" />
          </p>
          <p className="absolute left-5 top-24 text-[10px] leading-none text-white/80">Commission</p>
          <p className="absolute left-5 top-[114px]">
            <Money value={d.commission_balance} whole="text-[16px]" cents="text-[12px] font-normal text-white/55" />
          </p>
          <p className="absolute left-[140px] top-24 text-[10px] leading-none text-white/80">Honesty Fund</p>
          <p className="absolute left-[140px] top-[114px]">
            <Money value={d.honesty_fund_balance} whole="text-[16px]" cents="text-[12px] font-normal text-white/55" />
          </p>
        </div>
      </div>
      <div className="flex items-center gap-4 px-5 pb-5 pt-4">
        <span className={`flex items-center gap-[6px] ${MUTED}`} title="Credited, still clearing: the marketplace has not paid Bluntly for it yet.">
          <ClockCounterClockwise size={16} aria-hidden />
          <span className="text-[14px] font-medium leading-none">{pesoSplit(d.pending).join("")}</span>
          <span className="text-[12px] leading-none">pending</span>
        </span>
        <Link href="/dashboard/transfer/details" className="flex flex-1 items-center justify-end gap-2 text-[12px] font-medium leading-none">
          <span className="grid size-7 place-items-center rounded-full border border-[var(--border-subtle)] bg-[var(--surface-card)]">
            <PencilSimple size={14} aria-hidden />
          </span>
          <span>
            Payout
            <br />
            details
          </span>
        </Link>
      </div>
    </Frame>
  );
}

/**
 * Screen/Dashboard/Empty (Figma 7855:10383): nothing has ever been credited,
 * so instead of an empty chart the card says how earning starts.
 */
function NoEarningsCard() {
  return (
    <Frame label="Earnings" className="p-[3px]">
      <Panel className="flex flex-col items-center gap-3 py-8 text-center">
        {/* eslint-disable-next-line @next/next/no-img-element -- a local SVG mascot */}
        <img src="/mascots/bunbun-neutral.svg" alt="" width={96} height={96} className="size-24" />
        <h2 className="text-[18px] font-semibold leading-none">No earnings yet</h2>
        <p className="max-w-[18rem] text-[13px] leading-[1.5] text-[var(--text-secondary)]">
          Write a review with an honest verdict. Once a moderator checks it, it can start earning.
        </p>
        <Link href="/reviews/new" className="mt-2 inline-flex h-12 w-full items-center justify-center rounded-full bg-[var(--accent-primary)] text-[15px] font-medium text-white">
          Write your first review
        </Link>
      </Panel>
    </Frame>
  );
}

function EarningsCard({ d }: { d: Data }) {
  const heights = barHeights(d.buckets);
  return (
    <Frame label="Earnings" className="p-[3px]">
      <Panel className="flex flex-col gap-5">
        <div className="flex items-center">
          <h2 className="flex-1 text-[16px] font-semibold leading-none">Earnings</h2>
          <DashboardSelect
            param="period"
            value={d.period}
            label="Earnings period"
            options={[
              { value: "week", label: "Weekly" },
              { value: "month", label: "Monthly" },
            ]}
          />
        </div>
        <div className="flex gap-6">
          <div className="flex flex-1 flex-col gap-1">
            <span className={`text-[12px] leading-none ${MUTED}`}>Earned</span>
            <Money value={d.earned} />
          </div>
          <div className={`flex flex-1 flex-col gap-1 ${MUTED}`}>
            <span className="text-[12px] leading-none">Returned</span>
            <Money value={d.returned} />
          </div>
        </div>
      </Panel>
      <div className="relative px-5 pb-4 pt-6">
        {heights.every((h) => h.up === 0 && h.down === 0) ? (
          <p className={`absolute inset-x-5 top-[72px] text-center text-[12px] leading-snug ${MUTED}`}>
            Nothing earned or returned {d.period === "week" ? "in the last 7 days" : "in the last 4 weeks"}.
          </p>
        ) : null}
        <ol aria-label={`Earned and returned, ${d.period === "week" ? "the last 7 days" : "the last 4 weeks"}`} className="flex gap-3">
          {d.buckets.map((b, i) => (
            <li key={b.start} className="flex min-w-0 flex-1 flex-col items-center">
              <span className="flex h-[120px] w-full flex-col items-center justify-end gap-[6px]">
                {b.current && Number(b.earned) > 0 ? (
                  <span className="text-[10px] leading-none text-[var(--semantic-success-500)]">{pesoSplit(b.earned)[0]}</span>
                ) : null}
                {heights[i].up > 0 ? (
                  <span className="w-full rounded-[8px] bg-[var(--semantic-success-500)]" style={{ height: heights[i].up }} />
                ) : null}
              </span>
              <span className="h-[6px] w-full" />
              <span className="flex h-8 w-full flex-col">
                {heights[i].down > 0 ? <span className="w-full rounded-[8px] bg-[var(--base-gray-200)]" style={{ height: heights[i].down }} /> : null}
              </span>
              <span className={`text-[10px] leading-none ${b.current ? "text-[var(--text-primary)]" : MUTED}`}>{b.label}</span>
              <span className="sr-only">
                {`${pesoSplit(b.earned).join("")} earned, ${pesoSplit(b.returned).join("")} returned`}
              </span>
            </li>
          ))}
        </ol>
      </div>
      <Panel className="flex flex-col gap-4">
        <div className="flex items-center text-[12px]">
          <h3 className="flex-1 font-normal text-[var(--accent-trust)]">Best performing</h3>
          <span className={`leading-none ${MUTED}`}>{d.period === "week" ? "This week" : "Last 4 weeks"}</span>
        </div>
        {d.best.length === 0 ? (
          <p className={`text-[12px] leading-relaxed ${MUTED}`}>
            Nothing earned, read or voted on in this window yet. Reviews with a shop link earn when readers buy through them.
          </p>
        ) : (
          d.best.map((row) => {
            const top = Math.max(...d.best.map((b) => Number(b.earned) || b.views || 1));
            const value = Number(row.earned) || row.views || 0;
            return (
              <Link key={row.review_id} href={`/reviews/${row.review_id}`} className="flex items-center gap-3">
                {row.image_url ? (
                  <Image src={row.image_url} alt="" width={48} height={48} className="size-12 shrink-0 rounded-[12px] object-cover" />
                ) : (
                  <span className="size-12 shrink-0 rounded-[12px] bg-[var(--surface-app)]" aria-hidden />
                )}
                <span className="flex min-w-0 flex-1 flex-col gap-[6px]">
                  <span className="line-clamp-2 text-[14px] font-medium leading-none">{row.product_name}</span>
                  <span className={`text-[10px] leading-none ${MUTED}`}>
                    {compact(row.views)} views · {compact(row.helped)} helped
                  </span>
                  <span className="h-1 w-full overflow-hidden rounded-[4px] bg-[var(--surface-app)]">
                    <span className="block h-1 rounded-[4px] bg-[var(--base-gray-400)]" style={{ width: `${Math.round((value / top) * 100)}%` }} />
                  </span>
                </span>
                <span className="flex shrink-0 flex-col items-end gap-[2px]">
                  <Money value={row.earned} whole="text-[16px]" cents="text-[12px]" />
                  <span className={`text-[10px] leading-none ${MUTED}`}>earned</span>
                </span>
              </Link>
            );
          })
        )}
      </Panel>
    </Frame>
  );
}

export function Ring({ size, stroke, fraction, colour, children }: { size: number; stroke: number; fraction: number; colour: string; children: React.ReactNode }) {
  const r = (size - stroke) / 2;
  const c = 2 * Math.PI * r;
  return (
    <span className="relative grid shrink-0 place-items-center" style={{ width: size, height: size }}>
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} aria-hidden className="absolute inset-0 -rotate-90">
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="var(--surface-app)" strokeWidth={stroke} />
        {fraction > 0 ? (
          <circle
            cx={size / 2}
            cy={size / 2}
            r={r}
            fill="none"
            stroke={colour}
            strokeWidth={stroke}
            strokeLinecap="round"
            strokeDasharray={`${c * fraction} ${c}`}
          />
        ) : null}
      </svg>
      <span className="relative font-semibold leading-none">{children}</span>
    </span>
  );
}

function TrustCard({ d }: { d: Data }) {
  const steps = stepStates(d.stage);
  const met = d.requirements.filter((r) => r.done).length;
  const progress = d.requirements.length ? met / d.requirements.length : 0;
  return (
    <Frame label="Trust stage" className="p-[3px]">
      <Panel className="flex flex-col gap-[18px]">
        <div className="flex items-center gap-3">
          <div className="flex min-w-0 flex-1 flex-col gap-2 leading-none">
            <h2 className="text-[20px] font-semibold">{d.level_name}</h2>
            <p className={`text-[12px] ${MUTED}`}>{stepsLine(d.requirements, d.next_level_name)}</p>
          </div>
          <Link href="/how-it-works" aria-label="How trust stages work" className="text-[var(--text-primary)]">
            <Info size={24} aria-hidden />
          </Link>
        </div>
        <ol aria-label="Trust stages" className="flex items-center">
          {steps.map((state, i) => (
            <li key={i} className={`flex items-center ${i < 4 ? "flex-1" : ""}`}>
              <span
                aria-current={i + 1 === d.stage ? "step" : undefined}
                className={`grid shrink-0 place-items-center rounded-full font-semibold leading-none ${
                  state === "done"
                    ? "size-8 bg-[var(--accent-primary)] text-[12px] text-white"
                    : state === "next"
                      ? "size-11 border-2 border-[var(--accent-primary)] bg-[var(--status-high-bg)] text-[16px] text-[var(--accent-primary)]"
                      : `size-8 bg-[var(--surface-app)] text-[12px] ${MUTED}`
                }`}
              >
                {i + 1}
              </span>
              {i < 4 ? (
                <span className="flex h-[2px] flex-1">
                  {steps[i + 1] === "done" ? (
                    <span className="flex-1 bg-[var(--accent-primary)]" />
                  ) : steps[i + 1] === "next" && state === "done" ? (
                    <>
                      <span className="bg-[var(--accent-primary)]" style={{ flexGrow: progress }} />
                      <span className="bg-[var(--border-subtle)]" style={{ flexGrow: 1 - progress }} />
                    </>
                  ) : (
                    <span className="flex-1 bg-[var(--border-subtle)]" />
                  )}
                </span>
              ) : null}
            </li>
          ))}
        </ol>
      </Panel>
      {d.next_level_name ? (
        <div className="flex flex-col gap-[14px] px-[17px] py-5">
          <h3 className="text-[12px] font-normal text-[var(--accent-trust)]">To reach {d.next_level_name}</h3>
          {/* Figma Requirements (7835:9589): three ~100px cards to a row, the
              label wrapping under its ring ("Receipt / reviews"). A stage with
              four or five requirements wraps to a second row rather than
              squeezing five rings into 390px. */}
          <ul className="grid grid-cols-3 items-start gap-2">
            {d.requirements.map((r) => (
              <li key={r.key} className="flex min-w-0 flex-col items-center gap-2 rounded-[16px] bg-[var(--surface-card)] px-2 py-[14px]">
                <Ring size={56} stroke={6} fraction={ringFraction(r.have, r.needed, r.done)} colour={r.done ? "var(--accent-success)" : "var(--accent-primary)"}>
                  <span className="text-[12px]">{requirementValue(r.key, r.have, r.needed)}</span>
                </Ring>
                <span className="text-center text-[13px] leading-[18px] [hyphens:auto] [overflow-wrap:break-word] min-[360px]:text-[14px]">{r.label}</span>
                <span className="sr-only">{r.done ? "Done" : `Needs ${r.needed}`}</span>
              </li>
            ))}
          </ul>
          {d.held_for_review ? (
            <p className={`text-[12px] leading-relaxed ${MUTED}`}>
              Every requirement is met. The promotion is waiting for a moderator to review how your votes were spread.
            </p>
          ) : null}
        </div>
      ) : null}
      <Panel className="flex items-center gap-4">
        <Ring size={72} stroke={7} fraction={Math.max(0, Math.min(1, d.honesty_score / 100))} colour="var(--accent-trust)">
          <span className="text-[16px]">{d.honesty_score}</span>
        </Ring>
        <div className="flex min-w-0 flex-1 flex-col gap-1">
          <span className="flex items-center gap-1 text-[14px] font-semibold leading-none">
            <Shield size={16} weight="fill" aria-hidden className="text-[var(--accent-trust)]" />
            Honesty Score
          </span>
          <p className={`text-[12px] leading-[1.5] ${MUTED}`}>
            Shown on your reviews and profile. {pesoSplit(d.honesty_fund_earned).join("")} from the Honesty Fund so far.
          </p>
        </div>
      </Panel>
    </Frame>
  );
}

function ReachCard({ d }: { d: Data }) {
  const now: ContributorReach = d.reach;
  const before = d.reach_previous;
  return (
    <Frame label="Your reach" className="flex flex-col gap-3 overflow-hidden px-5 pt-5">
      <div className="flex items-center">
        <h2 className="flex-1 text-[16px] font-semibold leading-none">Your reach</h2>
        <DashboardSelect
          param="reach"
          value={d.reach_choice}
          label="Reach month"
          options={[
            { value: "this", label: "This month" },
            { value: "last", label: "Last month" },
          ]}
        />
      </div>
      <ReachRings now={now} before={before} suffix={`vs ${d.reach_previous_month}`} label={`${d.reach_month}: views, people helped, link clicks and purchases`} />
    </Frame>
  );
}

export function ContributorDashboard({ data }: { data: Data | null }) {
  return (
    <div className="mx-auto w-full max-w-[390px] px-4 pb-10 pt-1 md:max-w-[880px] md:px-6 md:pt-6">
      <DashboardActions />
      {data === null ? (
        <p role="alert" className="rounded-[32px] bg-[var(--surface-app)] p-6 text-center text-[14px] text-[var(--text-secondary)]">
          Your dashboard could not be loaded. Nothing here is a zero; try again in a moment.
        </p>
      ) : (
        <div className="md:columns-2 md:gap-4">
          <WalletCard d={data} />
          {data.has_earned === false ? <NoEarningsCard /> : <EarningsCard d={data} />}
          <TrustCard d={data} />
          <ReachCard d={data} />
        </div>
      )}
    </div>
  );
}
