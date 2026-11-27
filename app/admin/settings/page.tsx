import type { Metadata } from "next";
import Link from "next/link";
import { CheckCircle, CurrencyCircleDollar, Info, WarningCircle } from "@phosphor-icons/react/dist/ssr";

import { AdminExportButton } from "@/components/admin/export/AdminExport";
import { ConnectPayMongoButton } from "@/components/admin/settings/ConnectPayMongo";
import { getSuperAdminAccess } from "@/lib/dal";
import { getAdminSettings, type AdminSettings } from "@/lib/settings-admin";

export const metadata: Metadata = { title: "Settings — bluntly admin" };

const SECTIONS = [
  ["team", "Team"],
  ["earning", "Earning rules"],
  ["payouts", "Payouts"],
  ["notifications", "Notifications"],
  ["integrations", "Integrations"],
  ["privacy", "Data & privacy"],
] as const;
const ROLE: Record<string, string> = { super_admin: "Super Admin", administrator: "Administrator" };
const pct = (v: string | number) => `${Math.round(Number(v) * 100)}%`;
const ordinal = (n: number) => `${n}${n % 10 === 1 && n !== 11 ? "st" : n % 10 === 2 && n !== 12 ? "nd" : n % 10 === 3 && n !== 13 ? "rd" : "th"}`;

function Section({ id, title, sub, action, children }: { id: string; title: string; sub: string; action?: React.ReactNode; children: React.ReactNode }) {
  return (
    <section id={id} aria-labelledby={`${id}-h`} className="scroll-mt-4 rounded-[16px] border border-[var(--border-subtle)] bg-[var(--surface-card)] p-5">
      <div className="flex items-start gap-3">
        <div className="flex-1">
          <h2 id={`${id}-h`} className="text-[16px] font-semibold leading-none">{title}</h2>
          <p className="mt-1 text-[12px] text-[var(--text-secondary)]">{sub}</p>
        </div>
        {action}
      </div>
      <div className="mt-4">{children}</div>
    </section>
  );
}

function Value({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex flex-col gap-2">
      <span className="text-[12px] text-[var(--text-secondary)]">{label}</span>
      <span className="flex h-[48px] items-center rounded-[12px] border border-[var(--border-subtle)] bg-[var(--surface-app)] px-4 text-[16px] [font-variant-numeric:tabular-nums]">{value}</span>
    </div>
  );
}

const Note = ({ children }: { children: React.ReactNode }) => (
  <p className="mt-3 flex items-start gap-2 rounded-[12px] bg-[var(--surface-app)] px-3 py-2 text-[12px] text-[var(--text-secondary)]">
    <Info size={14} className="mt-[1px] shrink-0" aria-hidden /> <span>{children}</span>
  </p>
);

function Status({ status }: { status: string }) {
  return status === "connected" ? (
    <span className="flex items-center gap-1 text-[12px] text-[var(--accent-success)]"><CheckCircle size={14} weight="fill" aria-hidden /> Connected</span>
  ) : status === "manual" ? (
    <span className="flex items-center gap-1 text-[12px] text-[var(--chart-honesty-fund)]"><CurrencyCircleDollar size={14} aria-hidden /> By hand</span>
  ) : (
    <span className="flex items-center gap-1 text-[12px] text-[var(--accent-primary)]"><WarningCircle size={14} weight="fill" aria-hidden /> Not connected</span>
  );
}

function ago(iso: string | null | undefined, now: number): string {
  if (!iso) return "No recorded action";
  const h = Math.round((now - new Date(iso).getTime()) / 3_600_000);
  return h < 1 ? "Within the hour" : h < 48 ? `${h}h ago` : `${Math.round(h / 24)}d ago`;
}

/**
 * Admin Settings (Figma Screen/Admin/Settings 8076:16388): who has access, how
 * money moves, and what Bluntly tells you about. READ-ONLY by design: every
 * value is the one the services run on (GET /admin/settings). Changing the
 * earning rules or the commission split moves money and waits on an owner
 * decision; role changes already live in Users (Super Admin).
 */
export default async function SettingsPage() {
  const [data, access] = await Promise.all([getAdminSettings(), getSuperAdminAccess()]);
  // eslint-disable-next-line react-hooks/purity -- read once per request, on the server
  const now = Date.now();
  if (!data) {
    return <p role="alert" className="text-[14px] text-[var(--text-secondary)]">Settings could not be loaded. Nothing has changed; try again in a moment.</p>;
  }
  const s: AdminSettings = data;
  const split = [
    ["Reviewer", s.split_reviewer, "bg-[var(--accent-primary)]"],
    ["Honesty Fund", s.split_honesty_fund, "bg-[color-mix(in_srgb,var(--accent-primary)_60%,white)]"],
    ["Platform", s.split_platform, "bg-[color-mix(in_srgb,var(--accent-primary)_30%,white)]"],
  ] as const;
  return (
    <div className="flex flex-col gap-4">
      <p className="text-[14px] text-[var(--text-secondary)]">Who has access, how money moves, and what Bluntly tells you about.</p>
      <div className="grid gap-4 lg:grid-cols-[180px_minmax(0,1fr)]">
        <nav aria-label="Settings sections" className="lg:sticky lg:top-0 lg:self-start">
          <ul className="flex flex-wrap gap-1 lg:flex-col">
            {SECTIONS.map(([id, label]) => (
              <li key={id}>
                <a href={`#${id}`} className="block rounded-[10px] px-3 py-2 text-[14px] hover:bg-[var(--surface-app)]">{label}</a>
              </li>
            ))}
          </ul>
        </nav>
        <div className="flex min-w-0 flex-col gap-4">
          <Section
            id="team"
            title="Team"
            sub="People with admin access."
            action={access.allowed ? <Link href="/admin/users" className="flex h-8 items-center rounded-full bg-[var(--accent-primary)] px-3 text-[12px] text-white">Manage roles</Link> : null}
          >
            <div className="overflow-x-auto">
              <table className="w-full min-w-[520px] border-collapse text-left text-[14px]">
                <thead className="text-[12px] text-[var(--text-secondary)]">
                  <tr>
                    {["Person", "Role", "Last staff action"].map((h) => (
                      <th key={h} scope="col" className="border-b border-[var(--border-subtle)] pb-2 font-normal">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {s.team.map((m) => (
                    <tr key={m.id} data-testid="team-row" className="border-b border-[var(--border-subtle)] last:border-0">
                      <td className="py-[9px]">
                        <span className="flex flex-col leading-tight">
                          <span>{m.name ?? "Staff member"}</span>
                          {m.email ? <span className="text-[12px] text-[var(--text-secondary)]">{m.email}</span> : null}
                        </span>
                      </td>
                      <td>{ROLE[m.role] ?? m.role}</td>
                      <td className="text-[var(--text-secondary)]" suppressHydrationWarning>{ago(m.last_action_at, now)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {s.team_total > s.team.length ? <p className="mt-2 text-[12px] text-[var(--text-secondary)]">Showing the {s.team.length} most recently active of {s.team_total}.</p> : null}
            <Note>{access.allowed ? "Roles are granted and removed in Users; the last active Super Admin cannot be demoted." : "Roles are managed by the Super Admin."} Sign-in times are not recorded, so the list shows each person&rsquo;s latest audited action.</Note>
          </Section>

          <Section id="earning" title="Earning rules" sub="When a review can earn, and how commission is split.">
            <div className="grid gap-3 sm:grid-cols-2">
              <Value label="Wilson score gate" value={s.wilson_gate.toFixed(2)} />
              <Value label="Minimum Stage-2 voters" value={String(s.min_stage2_voters)} />
            </div>
            <p className="mt-4 text-[12px] text-[var(--text-secondary)]">Commission split</p>
            <div className="mt-2 grid gap-3 sm:grid-cols-3">
              {split.map(([label, v]) => <Value key={label} label={label} value={pct(v)} />)}
            </div>
            <div className="mt-3 flex h-[6px] overflow-hidden rounded-full" aria-hidden>
              {split.map(([label, v, cls]) => <span key={label} className={cls} style={{ width: pct(v) }} />)}
            </div>
            <Note>These are the live rules (ranking and commission constants). Changing them moves money, so they are not editable here until the owner approves it; every earnings decision is recorded in the Activity log.</Note>
          </Section>

          <Section id="payouts" title="Payouts" sub="How and when reviewers get paid.">
            <div className="grid gap-3 sm:grid-cols-3">
              <Value label="Payout minimum" value={`₱${Number(s.payout_minimum).toLocaleString("en-PH", { minimumFractionDigits: 2 })}`} />
              <Value label="Payout day" value={`${ordinal(s.payout_day)} of each month`} />
              <Value label="Honesty Fund day" value={`${ordinal(s.honesty_fund_day)} of each month`} />
            </div>
            <Note>PayPal, sent by hand: each payout is sent from the Bluntly account and marked as sent in Payouts. There is no automatic transfer.</Note>
          </Section>

          <Section id="notifications" title="Notifications" sub="What the team is told about.">
            <p className="text-[14px]">Staff email alerts are not set up.</p>
            <Note>Queue pressure, failed scheduled jobs, escalated reports and failed payouts show in the top bar&rsquo;s activity bell, the Overview&rsquo;s Needs attention card and the Activity log&rsquo;s Scheduled jobs card.</Note>
          </Section>

          <Section id="integrations" title="Integrations" sub="Services Bluntly connects to.">
            <ul>
              {s.integrations.map((i) => (
                <li key={i.key} className="flex items-center gap-3 border-b border-[var(--border-subtle)] py-3 last:border-0">
                  <span className="flex min-w-0 flex-1 flex-col leading-tight">
                    <span className="text-[14px] font-medium">{i.name}</span>
                    <span className="text-[12px] text-[var(--text-secondary)]">{i.detail}</span>
                  </span>
                  <Status status={i.status} />
                  {i.key === "affiliate" ? <Link href="/admin/affiliate-links?tab=imports" className="flex h-8 items-center rounded-full border border-[var(--text-primary)] px-3 text-[12px]">Import report</Link> : null}
                  {i.key === "paymongo" ? <ConnectPayMongoButton connected={i.detail.startsWith("Keys saved")} canEdit={access.allowed} /> : null}
                </li>
              ))}
            </ul>
          </Section>

          <Section id="privacy" title="Data & privacy" sub="How long Bluntly keeps things." action={<AdminExportButton initial={["activity"]} />}>
            <dl>
              {s.retention.map((r) => (
                <div key={r.label} className="flex justify-between gap-4 border-b border-[var(--border-subtle)] py-3 text-[14px] last:border-0">
                  <dt>{r.label}</dt>
                  <dd className="text-right text-[var(--text-secondary)]">{r.value}</dd>
                </div>
              ))}
            </dl>
          </Section>
        </div>
      </div>
    </div>
  );
}
