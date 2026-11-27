import type { Metadata } from "next";
import Link from "next/link";
import { CaretRight, ChatCircle, Info, Plus, Receipt, Shield } from "@phosphor-icons/react/dist/ssr";

import { CashoutButton } from "@/components/dashboard/CashoutButton";
import { DashboardBar } from "@/components/dashboard/DashboardBar";
import { Money, ParentLink } from "@/components/dashboard/DashboardParts";
import { PayoutRing } from "@/components/dashboard/PayoutRing";
import { pesoSplit } from "@/components/dashboard/contributor-model";
import { SiteHeader } from "@/components/site/SiteHeader";
import { requireOnboardedUser } from "@/lib/dal";
import { getDashboard, getPayoutBalance, PAYOUT_MIN_PHP } from "@/lib/dashboard";
import { trustLevel } from "@/lib/trust";

export const metadata: Metadata = { title: "Payout — bluntly" };

/**
 * Payout, built to Figma Screen/Payout 7840:9380 and its locked state
 * Screen/Payout/Locked 7840:9462 (meeting 2026-10-02, 4:12): the cleared money
 * as a ring split into commission and Honesty Fund, "Minimum met" or "₱x to
 * go", then either how payouts work and where they go, or how to get there
 * faster; the footer requests the whole cleared amount.
 *
 * Every figure is GET /payouts/balance. Business Rules §15/§19: a request
 * draws only on CLEARED money (commission the marketplace has paid Bluntly
 * for), so the ring and the button measure the cleared part, never the wallet.
 * Payouts are sent by PayPal (Completion contract X.4: GCash and Maya are
 * simulated only), so the destination card shows the PayPal account.
 */
function withdrawalState(p: { status: string; scheduled_for: string; paid_at: string | null }): string {
  const on = (iso: string) => new Date(iso).toLocaleDateString("en-PH", { dateStyle: "medium" });
  switch (p.status) {
    case "scheduled":
      return `Requested · in the batch for ${on(p.scheduled_for)}`;
    case "processing":
      return "Being paid";
    case "paid":
      return p.paid_at ? `Paid ${on(p.paid_at)}` : "Paid";
    case "failed":
      return "Failed · back in your balance";
    case "cancelled":
      return "Cancelled · back in your balance";
    default:
      return p.status;
  }
}

function Card({ label, children, className = "" }: { label: string; children: React.ReactNode; className?: string }) {
  return (
    <section aria-label={label} className="w-full rounded-[32px] bg-[var(--surface-app)] p-[3px]">
      <div className={`w-full rounded-[32px] bg-[var(--surface-card)] ${className}`}>{children}</div>
    </section>
  );
}

function SectionLabel({ children }: { children: React.ReactNode }) {
  return <h2 className="text-[12px] font-normal leading-normal text-[var(--chart-honesty-fund)]">{children}</h2>;
}

function LegendTile({ label, value, colour }: { label: string; value: string; colour: string }) {
  return (
    <div className="flex min-w-0 flex-1 flex-col gap-1 rounded-[16px] bg-[var(--surface-app)] p-3">
      <span className="flex items-center gap-1.5 text-[12px] leading-none text-[var(--base-gray-400)]">
        <span aria-hidden className="size-2 rounded-full" style={{ background: colour }} />
        {label}
      </span>
      <Money value={value} whole="text-[16px]" cents="text-[12px]" tone="text-[var(--text-primary)]" />
    </div>
  );
}

type Step = { label: string; state: "current" | "next" | "upcoming" };

const STEPS: Step[] = [
  { label: "Request", state: "current" },
  { label: "Checked in 3–5 days", state: "next" },
  { label: "Sent to wallet", state: "upcoming" },
];

/** Payout status for an open request (Screen/Payout/Requested 7855:11171). */
function requestSteps(status: string): Step[] {
  return status === "processing"
    ? [
        { label: "Requested", state: "current" },
        { label: "Checked", state: "current" },
        { label: "Sending to PayPal", state: "next" },
      ]
    : [
        { label: "Requested", state: "current" },
        { label: "Checking · 3–5 days", state: "next" },
        { label: "Sent to PayPal", state: "upcoming" },
      ];
}

function Stepper({ steps = STEPS }: { steps?: Step[] }) {
  return (
    <ol className="flex w-full items-start">
      {steps.map((s, i) => (
        <li key={s.label} className="contents">
          {i > 0 ? (
            <span aria-hidden className="flex min-w-0 flex-1 pt-[21px]">
              <span className="h-[2px] w-full bg-[var(--border-subtle)]" />
            </span>
          ) : null}
          <span className="flex w-[88px] shrink-0 flex-col items-center gap-2">
            <span className="grid size-11 place-items-center">
              <span
                className={
                  s.state === "current"
                    ? "grid size-8 place-items-center rounded-full bg-[var(--accent-primary)] text-[12px] font-semibold leading-none text-white"
                    : s.state === "next"
                      ? "grid size-11 place-items-center rounded-full border-2 border-[var(--accent-primary)] bg-[var(--status-high-bg)] text-[16px] font-semibold leading-none text-[var(--accent-primary)]"
                      : "grid size-8 place-items-center rounded-full bg-[var(--surface-app)] text-[12px] font-semibold leading-none text-[var(--base-gray-400)]"
                }
              >
                {i + 1}
              </span>
            </span>
            <span
              className={`w-full text-center text-[12px] font-medium leading-none ${s.state === "current" ? "text-[var(--text-primary)]" : "text-[var(--base-gray-400)]"}`}
            >
              {s.label}
            </span>
          </span>
        </li>
      ))}
    </ol>
  );
}

function Tip({ href, Icon, label }: { href: string; Icon: typeof Receipt; label: string }) {
  return (
    <Link href={href} className="flex w-full items-center gap-3 rounded-[12px] focus-visible:outline focus-visible:outline-2 focus-visible:outline-[var(--accent-primary)]">
      <span className="grid size-10 shrink-0 place-items-center rounded-[12px] bg-[var(--surface-app)] text-[var(--text-primary)]">
        <Icon size={20} weight={Icon === Receipt ? "regular" : "fill"} aria-hidden />
      </span>
      <span className="min-w-0 flex-1 text-[14px] font-medium leading-none text-[var(--text-primary)]">{label}</span>
      <CaretRight size={16} aria-hidden className="text-[var(--base-gray-400)]" />
    </Link>
  );
}

export default async function TransferPage() {
  const me = await requireOnboardedUser();
  const [balance, { payouts }] = await Promise.all([getPayoutBalance(), getDashboard()]);
  const withdrawable = balance?.withdrawable ?? "0";
  const commission = balance?.withdrawable_commission ?? withdrawable;
  const honestyFund = balance?.withdrawable_honesty_fund ?? "0";
  const minimum = balance?.minimum_cashout ?? String(PAYOUT_MIN_PHP);
  const short = Number(balance?.short_of_minimum ?? Math.max(Number(minimum) - Number(withdrawable), 0));
  const met = Boolean(balance) && short <= 0;
  const amountLabel = pesoSplit(withdrawable).join("");
  // Below the minimum the ring already says what is to go (Locked 7840:9462).
  const reason = !balance
    ? "Your balance couldn't be loaded right now."
    : met && !balance.payout_account_set
      ? "Add a wallet to request your payout"
      : null;
  // Each request stays listed once settled: paid (with its reference) or why it failed.
  const requests = payouts.slice(0, 5);
  // An open request with nothing new to add to it (Screen/Payout/Requested
  // 7855:11171). Once enough new money clears, the page offers a top-up instead.
  const open = payouts.find((p) => p.status === "scheduled" || p.status === "processing");
  const requested = open && !met ? open : null;
  const requestedLabel = requested ? pesoSplit(requested.amount).join("") : null;

  return (
    <div className="flex min-h-dvh flex-col bg-[var(--surface-card)]">
      <div className="hidden md:block">
        <SiteHeader user={{ username: me.username, avatarUrl: me.avatar_url, role: me.role }} />
      </div>
      <div className="md:hidden">
        <DashboardBar backHref="/dashboard" trustLevel={trustLevel(me.trust_level_name, me.trust_stage)} />
      </div>

      <main className="mx-auto flex w-full max-w-[390px] flex-1 flex-col md:max-w-[480px] md:pt-8">
        <div className="flex flex-col gap-3 px-4 pb-4">
          <ParentLink href="/dashboard" label="Dashboard" />
          <div className="flex items-center px-1">
            <h1 className="flex-1 text-[24px] font-semibold leading-none text-[var(--text-primary)]">Payout</h1>
            <Link href="/how-it-works" aria-label="How payouts work" className="rounded-full text-[var(--base-gray-400)] focus-visible:outline focus-visible:outline-2 focus-visible:outline-[var(--accent-primary)]">
              <Info size={24} aria-hidden />
            </Link>
          </div>

          {balance?.qa_tester ? (
            <p role="note" className="rounded-[16px] bg-[rgba(55,113,200,0.12)] px-4 py-3 text-[12px] leading-[1.5] text-[var(--text-primary)]">
              <strong className="font-semibold">You&apos;re a QA tester.</strong> Earnings labelled &ldquo;Sandbox
              test&rdquo; are test money for checking payouts: request them here and they are paid through PayPal
              sandbox. No real money moves.
            </p>
          ) : null}

          <Card label="Cleared balance" className="flex flex-col items-center gap-5 p-5">
            {requested ? (
              <>
                <PayoutRing commission={requested.amount} honestyFund="0" minimum={minimum} sent>
                  <Money value={requested.amount} whole="text-[24px]" cents="text-[16px]" />
                  <span className="text-[12px] font-light leading-none" data-testid="payout-threshold">
                    {requested.status === "processing" ? "Being sent" : "Request sent"}
                  </span>
                </PayoutRing>
                <p className="-mt-2 w-full text-center text-[12px] leading-[1.5] text-[var(--base-gray-400)]">
                  {withdrawalState(requested)}
                </p>
                {Number(withdrawable) > 0 ? (
                  <p className="-mt-3 w-full text-center text-[12px] leading-[1.5] text-[var(--base-gray-400)]">
                    {amountLabel} more has cleared since. Once it reaches {pesoSplit(minimum).join("")} you can request it too.
                  </p>
                ) : null}
              </>
            ) : (
              <>
                <PayoutRing commission={commission} honestyFund={honestyFund} minimum={minimum}>
                  <Money value={withdrawable} whole="text-[24px]" cents="text-[16px]" />
                  <span className="text-[12px] font-light leading-none" data-testid="payout-threshold">
                    {met ? "Minimum met" : `${pesoSplit(String(short)).join("")} to go`}
                  </span>
                </PayoutRing>
                <div className="flex w-full gap-2">
                  <LegendTile label="Commission" value={commission} colour="var(--accent-primary)" />
                  <LegendTile label="Honesty Fund" value={honestyFund} colour="var(--chart-honesty-fund)" />
                </div>
                {balance && Number(balance.pending_clearance) > 0 ? (
                  <p className="-mt-2 w-full text-[12px] leading-[1.5] text-[var(--base-gray-400)]">
                    {pesoSplit(balance.pending_clearance).join("")} more is still clearing: commission counts once the
                    marketplace has paid Bluntly for that month.
                  </p>
                ) : null}
              </>
            )}
          </Card>

          {met || requested ? (
            <>
              {requested ? (
                <Card label="Payout status" className="flex flex-col gap-[10px] px-5 py-4">
                  <SectionLabel>Payout status</SectionLabel>
                  <Stepper steps={requestSteps(requested.status)} />
                </Card>
              ) : (
                <Card label="How payouts work" className="flex flex-col gap-[10px] px-5 py-4">
                  <SectionLabel>How payouts work</SectionLabel>
                  <Stepper />
                </Card>
              )}
              {balance?.payout_account_set ? (
                <Card label="Send to" className="flex items-center gap-[10px] px-5 py-3">
                  <span aria-hidden className="grid size-10 shrink-0 place-items-center rounded-[12px] bg-[#003087] text-[14px] font-semibold leading-none text-white">
                    P
                  </span>
                  <span className="flex min-w-0 flex-1 flex-col gap-[2px] leading-none">
                    <span className="truncate text-[14px] font-medium text-[var(--text-primary)]">
                      {balance.payout_account_masked ? `PayPal · ${balance.payout_account_masked}` : "PayPal"}
                    </span>
                    <span className="truncate text-[12px] text-[var(--base-gray-400)]">
                      {balance.payout_account_name ?? "Add the name on the account"}
                    </span>
                  </span>
                  <Link href="/dashboard/transfer/details" className="flex shrink-0 items-center gap-[2px] text-[12px] font-medium leading-none text-[var(--text-primary)]">
                    Change
                    <CaretRight size={16} aria-hidden />
                  </Link>
                </Card>
              ) : (
                <Card label="Payout wallet">
                  <Link href="/dashboard/transfer/details" className="flex items-center gap-[10px] rounded-[32px] px-5 py-3 focus-visible:outline focus-visible:outline-2 focus-visible:outline-[var(--accent-primary)]">
                    <span aria-hidden className="grid size-10 shrink-0 place-items-center rounded-[12px] bg-[var(--text-primary)] text-[var(--surface-card)]">
                      <Plus size={20} weight="bold" />
                    </span>
                    <span className="min-w-0 flex-1 text-[14px] font-medium leading-none text-[var(--text-primary)]">Add a payout wallet</span>
                    <CaretRight size={16} aria-hidden className="text-[var(--base-gray-400)]" />
                  </Link>
                </Card>
              )}
            </>
          ) : (
            <Card label="Get there faster" className="flex flex-col gap-2 px-5 py-4">
              <SectionLabel>Get there faster</SectionLabel>
              <Tip href="/dashboard/transfer/proof" Icon={Receipt} label="Add receipts and photos" />
              <span aria-hidden className="h-px w-full bg-[var(--border-subtle)]" />
              <Tip href="/dashboard/transfer/answers" Icon={ChatCircle} label="Answer open questions" />
              <span aria-hidden className="h-px w-full bg-[var(--border-subtle)]" />
              <Tip href="/dashboard/transfer/honest-reviews" Icon={Shield} label="Honest low-star reviews pay too" />
            </Card>
          )}

          {requests.length > 0 ? (
            <Card label="Your requests" className="flex flex-col gap-2 px-5 py-4">
              <SectionLabel>Your requests</SectionLabel>
              <ul className="flex flex-col gap-2">
                {requests.map((p) => (
                  <li key={p.id} className="text-[13px] text-[var(--text-primary)]" data-testid="withdrawal">
                    <span className="flex items-center justify-between gap-3">
                      <span className="[font-variant-numeric:tabular-nums]">{pesoSplit(p.amount).join("")}</span>
                      <span className="text-right text-[var(--base-gray-400)]">{withdrawalState(p)}</span>
                    </span>
                    {p.status === "paid" && p.provider_ref ? (
                      <span className="block text-right text-[11px] text-[var(--base-gray-400)]">Reference {p.provider_ref}</span>
                    ) : null}
                    {p.status === "failed" && p.failure_reason ? (
                      <span className="block text-right text-[11px] text-[var(--base-gray-400)]">{p.failure_reason}</span>
                    ) : null}
                  </li>
                ))}
              </ul>
            </Card>
          ) : null}
        </div>

        <div className="flex-1" />
        <div className="sticky bottom-0 bg-[var(--surface-card)] px-4 pb-6 pt-2">
          <CashoutButton
            canCashOut={Boolean(balance?.can_cash_out)}
            reason={reason}
            amountLabel={amountLabel}
            minimumMet={met}
            requested={requestedLabel ? `${requestedLabel} is locked until it's sent to your PayPal` : null}
          />
        </div>
      </main>
    </div>
  );
}
