"use client";

import Link from "next/link";
import { useState } from "react";
import {
  ArrowFatDown,
  ArrowFatUp,
  CaretDown,
  CaretRight,
  ChatCircle,
  ChatCircleText,
  CheckCircle,
  Coins,
  Flag,
  HandCoins,
  LinkSimple,
  PencilSimple,
  Prohibit,
  Question,
  ShieldWarning,
  WarningCircle,
} from "@phosphor-icons/react/dist/ssr";

import { AdminModal } from "@/components/admin/AdminModal";
import { PersonActions } from "@/components/admin/people/PersonActions";
import { TrustScoreCell } from "@/components/admin/people/TrustScore";
import { Avatar } from "@/components/ui/Avatar";
import { PersonCell, levelLabel } from "@/components/admin/queue/QueueCells";
import type { PersonInvestigation as Data } from "@/lib/moderation";

/**
 * The member investigation page, built to Screen/Admin/People/Person
 * (8005:11974) and its Activity (8007:12069), Interactions (8007:12991),
 * Reports (8007:13917) and Moderation (8007:14746) tabs, from one read
 * (GET /admin/people/{id}). Definitions of reciprocity and linked accounts are
 * in person_investigation_service; nothing here computes a fraud judgement.
 */

type Tab = "overview" | "activity" | "interactions" | "reports" | "moderation";
const RANGES = ["1M", "6M", "1Y"] as const;
const ROLE: Record<string, string> = {
  user: "Reviewer",
  administrator: "Administrator",
  super_admin: "Super Admin",
  moderator: "Reviewer",
};
const ACTION: Record<string, string> = {
  unpublish: "Review taken down",
  remove: "Content removed",
  restore: "Review restored",
  approve: "Earnings approved",
  reject: "Earnings rejected",
  publish: "Review published",
  escalate: "Escalated",
  investigation_set: "Marked under investigation",
  investigation_clear: "Investigation closed",
  suspend: "Account suspended",
  penalize: "Penalized",
  affiliate_link_attach: "Affiliate link attached",
  affiliate_link_revoke: "Affiliate link revoked",
  special_routing: "Routed by a Super Admin",
  cold_start_substitution: "Cold-start vote substitution",
  role_grant: "Role granted",
  role_revoke: "Role revoked",
};
const REPORT_STATUS: Record<string, string> = {
  open: "Open",
  upheld: "Upheld",
  dismissed: "Dismissed",
  restored: "Restored",
  escalated: "Escalated",
};

/** ₱ with two decimals. (lib/dashboard's `peso` is in a server-only module.) */
function peso(amount: string): string {
  return `₱${Number(amount).toLocaleString("en-PH", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

function ago(iso: string | null, now: number): string {
  if (!iso) return "—";
  const s = Math.max(0, Math.round((now - new Date(iso).getTime()) / 1000));
  if (s < 3600) return `${Math.max(1, Math.round(s / 60))}m ago`;
  if (s < 86400) return `${Math.round(s / 3600)}h ago`;
  return `${Math.round(s / 86400)}d ago`;
}

function shortDay(iso: string): string {
  return new Date(`${iso}T00:00:00`).toLocaleDateString("en-PH", { day: "numeric", month: "short" });
}

function ActivityIcon({ kind }: { kind: string }) {
  const box = "grid size-8 shrink-0 place-items-center rounded-[8px] bg-[var(--surface-app)]";
  if (kind === "vote_up") return <span className={box}><ArrowFatUp size={16} weight="fill" className="text-[var(--accent-success)]" /></span>;
  if (kind === "vote_down") return <span className={box}><ArrowFatDown size={16} weight="fill" className="text-[var(--accent-danger)]" /></span>;
  if (kind === "comment") return <span className={box}><ChatCircle size={16} weight="fill" /></span>;
  if (kind === "report") return <span className={box}><Flag size={16} /></span>;
  if (kind === "review") return <span className={box}><PencilSimple size={16} /></span>;
  if (kind === "question") return <span className={box}><Question size={16} /></span>;
  return <span className={box}><ChatCircleText size={16} /></span>;
}

const TYPE: Record<string, string> = {
  vote_up: "Vote",
  vote_down: "Vote",
  comment: "Comment",
  report: "Report",
  review: "Review",
  question: "Question",
  answer: "Answer",
};

function Card({ title, href, aside, children }: { title: string; href?: string; aside?: React.ReactNode; children: React.ReactNode }) {
  return (
    <section className="flex min-w-0 flex-col gap-4 rounded-[16px] border border-[var(--border-subtle)] bg-[var(--surface-card)] p-5">
      <div className="flex items-center gap-2">
        <h3 className="text-[16px] font-semibold leading-none">
          {href ? (
            <Link href={href} scroll={false} className="inline-flex items-center gap-1 hover:text-[var(--accent-primary)]">
              {title}
              <CaretRight size={14} className="text-[var(--text-secondary)]" />
            </Link>
          ) : (
            title
          )}
        </h3>
        <span className="flex-1" />
        {aside}
      </div>
      {children}
    </section>
  );
}

function ShareBar({ pct }: { pct: number }) {
  return (
    <span className="flex items-center gap-2">
      <span className="h-[5px] w-[46px] overflow-hidden rounded-full bg-[var(--surface-app)]">
        <span className="block h-full rounded-full bg-[var(--text-primary)]" style={{ width: `${Math.min(100, pct)}%` }} />
      </span>
      {Math.round(pct)}%
    </span>
  );
}

function Table({ head, children, minWidth = 900 }: { head: string[]; children: React.ReactNode; minWidth?: number }) {
  return (
    <div className="overflow-x-auto rounded-[16px] border border-[var(--border-subtle)]">
      <table className="w-full table-auto border-collapse text-left text-[14px]" style={{ minWidth }}>
        <thead className="bg-[var(--surface-app)] text-[12px] text-[var(--text-secondary)]">
          <tr>
            {head.map((h) => (
              <th key={h} scope="col" className="h-10 whitespace-nowrap px-3 font-normal">{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>{children}</tbody>
      </table>
    </div>
  );
}

function OpenLink({ href }: { href: string | null }) {
  if (!href) return null;
  return (
    <Link href={href} className="rounded-full border border-[var(--border-subtle)] px-3 py-1 text-[12px] hover:border-[var(--text-secondary)]">
      Open
    </Link>
  );
}

const REPORT_TONE: Record<string, { Icon: typeof CheckCircle; tone: string; weight?: "fill" }> = {
  open: { Icon: WarningCircle, tone: "text-[var(--accent-primary)]" },
  escalated: { Icon: ShieldWarning, tone: "text-[var(--accent-danger)]" },
  upheld: { Icon: CheckCircle, tone: "text-[var(--accent-success)]", weight: "fill" },
  dismissed: { Icon: Prohibit, tone: "text-[var(--text-secondary)]" },
  restored: { Icon: CheckCircle, tone: "text-[var(--text-secondary)]" },
};
const TARGET: Record<string, { label: string; Icon: typeof Flag }> = {
  review: { label: "Review", Icon: PencilSimple },
  comment: { label: "Comment", Icon: ChatCircle },
  question: { label: "Question", Icon: Question },
  answer: { label: "Answer", Icon: ChatCircleText },
  user: { label: "Account", Icon: Flag },
};

/**
 * Screen/Admin/People/Person/Reports (Figma 8007:13917) with its scope menu
 * (Menu/Person/ReportScope 8086:17314): reports against this member, or the
 * ones they filed. "From" is whoever filed it; System for automated signals.
 */
function ReportsView({ data, now }: { data: Data; now: number }) {
  const [scope, setScope] = useState<"received" | "filed">("received");
  const [open, setOpen] = useState(false);
  const name = data.person.name;
  const rows = data.reports.filter((r) => r.direction === scope);
  const label = (s: "received" | "filed") => (s === "received" ? `Against ${name}` : `Filed by ${name}`);
  return (
    <div className="flex flex-col gap-3">
      <div className="relative self-end">
        <button type="button" aria-haspopup="menu" aria-expanded={open} onClick={() => setOpen(!open)} className="inline-flex h-9 items-center gap-2 rounded-full border border-[var(--border-subtle)] px-4 text-[13px]">
          {label(scope)} <CaretDown size={12} />
        </button>
        {open ? (
          <div role="menu" className="absolute right-0 top-[calc(100%+6px)] z-30 w-[220px] rounded-[16px] border border-[var(--border-subtle)] bg-[var(--surface-card)] p-[6px] shadow-[var(--shadow-modal)]">
            {(["received", "filed"] as const).map((s) => (
              <button
                key={s}
                type="button"
                role="menuitemradio"
                aria-checked={scope === s}
                onClick={() => {
                  setScope(s);
                  setOpen(false);
                }}
                className={`flex w-full rounded-[10px] px-3 py-[10px] text-left text-[14px] hover:bg-[var(--surface-app)] ${scope === s ? "bg-[var(--surface-app)]" : ""}`}
              >
                {label(s)} ({data.reports.filter((r) => r.direction === s).length})
              </button>
            ))}
          </div>
        ) : null}
      </div>
      <Table head={["Reported", "Reason", "From", "Outcome", "Filed", "Action"]}>
        {rows.length === 0 ? (
          <tr><td colSpan={6} className="border-t border-[var(--border-subtle)] px-3 py-10 text-center text-[var(--text-secondary)]">{scope === "received" ? "No reports against this member." : "This member has filed no reports."}</td></tr>
        ) : (
          rows.map((r) => {
            const t = TARGET[r.target_type ?? ""] ?? { label: "Content", Icon: Flag };
            const o = REPORT_TONE[r.status] ?? REPORT_TONE.open;
            return (
              <tr key={r.id} data-testid="person-report-row" className="border-t border-[var(--border-subtle)]">
                <td className="px-3 py-[10px]">
                  <span className="flex items-center gap-[10px]">
                    <span className="grid size-[30px] shrink-0 place-items-center rounded-[8px] bg-[var(--surface-app)] text-[var(--text-secondary)]"><t.Icon size={16} aria-hidden /></span>
                    <span className="flex min-w-0 flex-col gap-1 leading-none">
                      <span className="max-w-[260px] truncate">{r.target_label}</span>
                      <span className="text-[12px] text-[var(--text-secondary)]">{t.label}</span>
                    </span>
                  </span>
                </td>
                <td className="px-3">{(r.reason ?? "report").replaceAll("_", " ").replace(/^./, (c) => c.toUpperCase())}</td>
                <td className="px-3">{r.other ? <PersonCell name={r.other.name} stage={r.other.trust_stage} href={`/admin/people/${r.other.id}`} /> : "System"}</td>
                <td className="px-3">
                  <span className="flex items-center gap-2">
                    <o.Icon size={16} weight={o.weight} className={o.tone} aria-hidden />
                    {REPORT_STATUS[r.status] ?? r.status}
                  </span>
                </td>
                <td className="px-3 text-[var(--text-secondary)]">{ago(r.at, now)}</td>
                <td className="px-3"><OpenLink href={r.href} /></td>
              </tr>
            );
          })
        )}
      </Table>
    </div>
  );
}

export function PersonInvestigation({ data, tab, now, canSuspend = false }: { data: Data; tab: Tab; now: number; canSuspend?: boolean }) {
  const [pairId, setPairId] = useState<string | null>(null);
  const p = data.person;
  const pair = data.interactions.find((i) => i.person.id === pairId) ?? null;
  const base = `/admin/people/${p.id}`;
  const hrefFor = (t: Tab) => `${base}?${new URLSearchParams({ ...(t === "overview" ? {} : { tab: t }), ...(data.range === "1M" ? {} : { range: data.range }) })}`;
  const days = data.daily.length - 1;
  // 1M draws a bar a day; 6M and 1Y a bar a week, so the bars stay readable.
  const step = data.daily.length > 40 ? 7 : 1;
  const bars: { day: string; total: number; spike: boolean }[] = [];
  for (let i = 0; i < data.daily.length; i += step) {
    const chunk = data.daily.slice(i, i + step);
    bars.push({
      day: chunk[0].day,
      total: chunk.reduce((n, d) => n + d.up + d.down, 0),
      spike: chunk.some((d) => d.day === data.spike?.day),
    });
  }
  const maxDay = Math.max(1, ...bars.map((b) => b.total));
  const upShare = data.votes_total ? (data.votes_up / data.votes_total) * 100 : 0;

  const tabs: { key: Tab; label: string; count?: number }[] = [
    { key: "overview", label: "Overview" },
    { key: "activity", label: "Activity", count: data.activity_total },
    { key: "interactions", label: "Interactions", count: data.interactions_total },
    { key: "reports", label: "Reports", count: data.signals.reports_against + data.signals.reports_filed },
    { key: "moderation", label: "Moderation", count: data.signals.moderation },
  ];

  return (
    <div className="flex flex-col gap-5">
      {/* Header */}
      <div className="flex flex-wrap items-center gap-4">
        <Avatar name={p.name} url={p.avatar_url ?? null} size={64} />
        <div className="min-w-0 flex-1">
          <h2 className="flex flex-wrap items-center gap-3 text-[32px] font-semibold leading-tight">
            {p.name}
            <span className="inline-flex items-center gap-1.5 text-[16px] font-normal">
              {p.status === "investigating" ? (
                <><WarningCircle size={16} weight="fill" className="text-[var(--accent-primary)]" /> Investigating</>
              ) : p.status === "suspended" ? (
                <><Prohibit size={16} weight="bold" className="text-[var(--accent-danger)]" /> Suspended</>
              ) : (
                <><CheckCircle size={16} weight="fill" className="text-[var(--accent-success)]" /> Active</>
              )}
            </span>
          </h2>
          <p className="mt-1 text-[14px] text-[var(--text-secondary)]">
            {[
              levelLabel(p.trust_stage),
              p.username ? `@${p.username}` : null,
              p.user_ref,
              ROLE[p.role] ?? p.role,
              `Joined ${new Date(p.joined).toLocaleDateString("en-PH", { day: "numeric", month: "short", year: "numeric" })}`,
            ].filter(Boolean).join(" · ")}
          </p>
          {/* The backend's effective Trust Score (override when set) and, when
              overridden, the system's own score beside it. */}
          <p className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1 text-[14px]" data-testid="person-trust-score">
            <span className="text-[var(--text-secondary)]">Trust Score</span>
            <TrustScoreCell score={p.reputation_score} computed={p.computed_score ?? null} overridden={Boolean(p.is_score_overridden)} />
          </p>
        </div>
        <Link href={`/u/${p.id}`} className="inline-flex h-9 items-center rounded-full border border-[var(--base-ink-800)] px-4 text-[12px]">
          Open profile
        </Link>
        <PersonActions
          person={{ id: data.person.id, name: data.person.name, role: data.person.role, status: data.person.status }}
          canSuspend={canSuspend}
          trust={{
            computed: p.computed_score ?? null,
            override: p.score_override ?? null,
            effective: p.reputation_score,
            overridden: Boolean(p.is_score_overridden),
            reason: p.score_override_reason ?? null,
            at: p.score_overridden_at ?? null,
          }}
        />
      </div>

      <nav aria-label="Investigation views" className="flex w-fit flex-wrap gap-[2px] rounded-[10px] bg-[var(--surface-app)] p-[3px]">
        {tabs.map((t) => (
          <Link
            key={t.key}
            href={hrefFor(t.key)}
            scroll={false}
            aria-current={tab === t.key ? "page" : undefined}
            className={`flex items-center gap-[6px] rounded-[8px] px-3 py-[5px] leading-none ${
              tab === t.key ? "bg-[var(--surface-card)] shadow-[var(--shadow-segment)]" : "text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
            }`}
          >
            <span className="text-[14px] font-medium">{t.label}</span>
            {t.count !== undefined ? <span className="text-[12px] text-[var(--text-secondary)]">{t.count}</span> : null}
          </Link>
        ))}
      </nav>

      {tab === "overview" ? (
        <div className="grid gap-4 xl:grid-cols-2">
          <Card
            title="Votes"
            href={hrefFor("activity")}
            aside={
              <span className="flex gap-[2px] rounded-full bg-[var(--surface-app)] p-[3px]">
                {RANGES.map((r) => (
                  <Link
                    key={r}
                    href={`${base}?${new URLSearchParams(r === "1M" ? {} : { range: r })}`}
                    scroll={false}
                    aria-current={data.range === r ? "true" : undefined}
                    className={`rounded-full px-[10px] py-[3px] text-[12px] font-medium ${
                      data.range === r ? "bg-[var(--surface-card)] shadow-[var(--shadow-segment)]" : "text-[var(--text-secondary)]"
                    }`}
                  >
                    {r}
                  </Link>
                ))}
              </span>
            }
          >
            <p className="flex items-baseline gap-2">
              <span className="text-[24px] font-semibold leading-none">{data.votes_total}</span>
              <span className="text-[12px] text-[var(--text-secondary)]">votes cast in {days} days</span>
            </p>
            <div className="flex h-2 gap-[3px] overflow-hidden rounded-full">
              {data.votes_total ? (
                <>
                  <span className="rounded-full bg-[var(--accent-success)]" style={{ width: `${upShare}%` }} />
                  <span className="flex-1 rounded-full bg-[var(--accent-danger)]" />
                </>
              ) : (
                <span className="flex-1 rounded-full bg-[var(--surface-app)]" />
              )}
            </div>
            <p className="flex gap-4 text-[12px] text-[var(--text-secondary)]">
              <span className="inline-flex items-center gap-1.5"><span className="size-2 rounded-[2px] bg-[var(--accent-success)]" />{data.votes_up} up · {Math.round(upShare)}%</span>
              <span className="inline-flex items-center gap-1.5"><span className="size-2 rounded-[2px] bg-[var(--accent-danger)]" />{data.votes_down} down · {data.votes_total ? 100 - Math.round(upShare) : 0}%</span>
            </p>
            <div className="flex h-[110px] items-end gap-[3px] overflow-hidden" aria-label={step === 1 ? "Votes per day" : "Votes per week"}>
              {bars.map((b) => (
                <span
                  key={b.day}
                  title={`${step === 1 ? "" : "Week of "}${shortDay(b.day)}: ${b.total} votes`}
                  className={`min-w-0 flex-1 rounded-[2px] ${b.spike ? "bg-[var(--accent-primary)]" : "bg-[var(--disabled-text)]"}`}
                  style={{ height: `${Math.max(b.total ? 6 : 2, (b.total / maxDay) * 100)}%` }}
                />
              ))}
            </div>
            <p className="flex justify-between text-[10px] text-[var(--text-secondary)]">
              <span>{shortDay(data.daily[0]?.day ?? "")}</span>
              {data.spike ? (
                <span className="text-[var(--text-primary)]">
                  {data.spike.up + data.spike.down} votes on {shortDay(data.spike.day)}
                </span>
              ) : (
                <span>No spike in this period</span>
              )}
              <span>{shortDay(data.daily[data.daily.length - 1]?.day ?? "")}</span>
            </p>
          </Card>

          <Card
            title="Top interactions"
            href={hrefFor("interactions")}
            aside={
              data.interactions.length >= 3 ? (
                <span className="text-[12px] text-[var(--text-secondary)]">
                  {Math.round(data.top3_share_pct)}% of votes go to 3 people
                </span>
              ) : null
            }
          >
            {data.interactions.length === 0 ? (
              <p className="text-[14px] text-[var(--text-secondary)]">No votes or comments on anyone else&apos;s reviews yet.</p>
            ) : (
              <table className="w-full text-left text-[14px]">
                <thead className="text-[12px] text-[var(--text-secondary)]">
                  <tr>
                    <th className="pb-2 font-normal">Person</th>
                    <th className="pb-2 font-normal">Up</th>
                    <th className="pb-2 font-normal">Down</th>
                    <th className="pb-2 font-normal">Comments</th>
                    <th className="pb-2 font-normal">Share</th>
                  </tr>
                </thead>
                <tbody>
                  {data.interactions.slice(0, 5).map((i) => (
                    <tr key={i.person.id} className="border-t border-[var(--border-subtle)]">
                      <td className="py-2"><PersonCell name={i.person.name} stage={i.person.trust_stage} levelName={i.person.trust_level_name} href={`/admin/people/${i.person.id}`} /></td>
                      <td>{i.up}</td>
                      <td>{i.down}</td>
                      <td>{i.comments}</td>
                      <td><ShareBar pct={i.share_pct} /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </Card>

          <Card title="Recent activity" href={hrefFor("activity")}>
            {data.activity.length === 0 ? (
              <p className="text-[14px] text-[var(--text-secondary)]">Nothing recorded yet.</p>
            ) : (
              <ul>
                {data.activity.slice(0, 6).map((a, i) => (
                  <li key={`${a.kind}-${a.at}-${i}`} className={i ? "border-t border-[var(--border-subtle)]" : ""}>
                    <Link href={a.href ?? "#"} className="flex items-center gap-3 py-2 text-[14px] hover:text-[var(--accent-primary)]">
                      <ActivityIcon kind={a.kind} />
                      <span className="min-w-0 flex-1 truncate">
                        {a.title}
                        {a.other && a.other.id !== p.id ? ` · ${a.other.name}` : ""}
                        {a.subtitle ? ` · ${a.subtitle}` : ""}
                      </span>
                      <span className="text-[12px] text-[var(--text-secondary)]">{ago(a.at, now).replace(" ago", "")}</span>
                    </Link>
                  </li>
                ))}
              </ul>
            )}
          </Card>

          <Card title="Signals">
            <ul className="text-[14px]">
              {[
                { icon: <Flag size={18} />, label: "Reports against", value: `${data.signals.reports_against} · ${data.signals.reports_against_upheld} upheld`, href: hrefFor("reports") },
                { icon: <Flag size={18} />, label: "Reports filed", value: `${data.signals.reports_filed} · ${data.signals.reports_filed_upheld} upheld`, href: hrefFor("reports") },
                { icon: <Prohibit size={18} />, label: "Moderation", value: `${data.signals.moderation} · ${data.signals.takedowns} ${data.signals.takedowns === 1 ? "takedown" : "takedowns"}`, href: hrefFor("moderation") },
                { icon: <Coins size={18} className="text-[var(--accent-primary)]" />, label: "Earned", value: data.signals.earned !== null ? peso(data.signals.earned) : "—", href: `/admin/payouts` },
                { icon: <HandCoins size={18} />, label: "Pending", value: data.signals.pending !== null ? peso(data.signals.pending) : "—", href: `/admin/payouts` },
              ].map((row) => (
                <li key={row.label} className="border-t border-[var(--border-subtle)] first:border-t-0">
                  <Link href={row.href} scroll={false} className="flex items-center gap-3 py-[9px] hover:text-[var(--accent-primary)]">
                    {row.icon}
                    <span className="flex-1">{row.label}</span>
                    <span>{row.value}</span>
                    <CaretRight size={14} className="text-[var(--text-secondary)]" />
                  </Link>
                </li>
              ))}
              <li className="border-t border-[var(--border-subtle)]">
                <details>
                  <summary className="flex cursor-pointer list-none items-center gap-3 py-[9px]">
                    {data.linked.length ? (
                      <ShieldWarning size={18} weight="fill" className="text-[var(--accent-danger)]" />
                    ) : (
                      <LinkSimple size={18} />
                    )}
                    <span className="flex-1">Linked accounts</span>
                    <span>
                      {data.linked.length}
                      {data.linked.length
                        ? ` · ${[...new Set(data.linked.map((l) => (l.basis === "shared_network" ? "shared network" : "shared payout account")))].join(", ")}`
                        : ""}
                    </span>
                    <CaretDown size={14} className="text-[var(--text-secondary)]" />
                  </summary>
                  {data.linked.length === 0 ? (
                    <p className="pb-2 text-[12px] text-[var(--text-secondary)]">
                      No shared network (last 30 days of up-votes) and no shared payout account. Devices are not
                      recorded, so no device link can exist.
                    </p>
                  ) : (
                    <ul className="flex flex-col gap-2 pb-2">
                      {data.linked.map((l) => (
                        <li key={`${l.person.id}-${l.basis}`} className="flex items-center gap-3 text-[12px]">
                          <PersonCell name={l.person.name} stage={l.person.trust_stage} href={`/admin/people/${l.person.id}`} />
                          <span className="text-[var(--text-secondary)]">{l.detail}</span>
                        </li>
                      ))}
                    </ul>
                  )}
                </details>
              </li>
            </ul>
          </Card>
        </div>
      ) : null}

      {tab === "activity" ? (
        <>
          <Table head={["Activity", "Author", "Type", "When", "Action"]}>
            {data.activity.map((a, i) => (
              <tr key={`${a.kind}-${a.at}-${i}`} className="border-t border-[var(--border-subtle)]">
                <td className="px-3 py-[10px]">
                  <span className="flex items-center gap-[10px]">
                    <ActivityIcon kind={a.kind} />
                    <span className="flex min-w-0 flex-col gap-1 leading-none">
                      <span>{a.title}</span>
                      {a.subtitle ? <span className="truncate text-[12px] text-[var(--text-secondary)]">{a.subtitle}</span> : null}
                    </span>
                  </span>
                </td>
                <td className="px-3">
                  {a.other ? <PersonCell name={a.other.name} stage={a.other.trust_stage} levelName={a.other.trust_level_name} href={`/admin/people/${a.other.id}`} /> : "—"}
                </td>
                <td className="px-3">{TYPE[a.kind] ?? a.kind}</td>
                <td className="px-3 text-[var(--text-secondary)]">{ago(a.at, now)}</td>
                <td className="px-3"><OpenLink href={a.href} /></td>
              </tr>
            ))}
          </Table>
          <p className="text-[12px] text-[var(--text-secondary)]">Showing the newest {data.activity.length} of {data.activity_total}</p>
        </>
      ) : null}

      {tab === "interactions" ? (
        <>
          <p className="text-[12px] text-[var(--text-secondary)]">
            Reciprocity is how evenly up-votes go both ways between the two members: 0% one-way, 100% every up-vote
            returned. About 20% is ordinary; 50–100% is what vote trading looks like.
          </p>
          <Table head={["Person", "Upvotes", "Downvotes", "Comments", "Share of votes", "Upvoted back", "Reciprocity", "Last", "Action"]} minWidth={1000}>
            {data.interactions.map((i) => (
              <tr key={i.person.id} className="border-t border-[var(--border-subtle)]">
                <td className="px-3 py-[10px]"><PersonCell name={i.person.name} stage={i.person.trust_stage} levelName={i.person.trust_level_name} href={`/admin/people/${i.person.id}`} /></td>
                <td className="px-3">{i.up}</td>
                <td className="px-3">{i.down}</td>
                <td className="px-3">{i.comments}</td>
                <td className="px-3"><ShareBar pct={i.share_pct} /></td>
                <td className="px-3">{i.up_back}</td>
                <td className={`px-3 ${i.reciprocity_pct >= 50 ? "font-medium text-[var(--accent-danger)]" : ""}`}>
                  {Math.round(i.reciprocity_pct)}%{i.same_network ? " · same network" : ""}
                </td>
                <td className="px-3 text-[var(--text-secondary)]">{ago(i.last_at, now)}</td>
                <td className="px-3">
                  <button type="button" onClick={() => setPairId(i.person.id)} className="rounded-full border border-[var(--border-subtle)] px-3 py-1 text-[12px] hover:border-[var(--text-secondary)]">
                    Open
                  </button>
                </td>
              </tr>
            ))}
          </Table>
          <p className="text-[12px] text-[var(--text-secondary)]">Showing {data.interactions.length} of {data.interactions_total}</p>
        </>
      ) : null}

      {tab === "reports" ? (
        <ReportsView data={data} now={now} />
      ) : null}

      {tab === "moderation" ? (
        <Table head={["Decision", "By", "Note", "When"]}>
          {data.moderation.length === 0 ? (
            <tr><td colSpan={4} className="border-t border-[var(--border-subtle)] px-3 py-10 text-center text-[var(--text-secondary)]">No staff action on this member or their content.</td></tr>
          ) : (
            data.moderation.map((m) => (
              <tr key={m.id} className="border-t border-[var(--border-subtle)]">
                <td className="px-3 py-[10px]">
                  <span className="flex flex-col gap-1 leading-none">
                    <span>{m.action === "restore" && m.target_type === "user" ? "Account reinstated" : (ACTION[m.action] ?? m.action.replaceAll("_", " "))}</span>
                    <span className="truncate text-[12px] text-[var(--text-secondary)]">{m.target_label}</span>
                  </span>
                </td>
                <td className="px-3">{m.moderator ?? "System"}</td>
                <td className="max-w-[320px] truncate px-3" title={m.notes ?? undefined}>{m.notes ?? m.reason?.replaceAll("_", " ") ?? "—"}</td>
                <td className="px-3 text-[var(--text-secondary)]">{ago(m.at, now)}</td>
              </tr>
            ))
          )}
        </Table>
      ) : null}

      {pair ? (
        <AdminModal
          title={`${p.name} and ${pair.person.name}`}
          subtitle={`Last interaction ${ago(pair.last_at, now)}`}
          width={560}
          onClose={() => setPairId(null)}
        >
          <div className="flex flex-col gap-4 p-6 text-[14px]">
            <dl className="grid grid-cols-2 gap-3">
              {[
                [`${p.name} → ${pair.person.name}`, `${pair.up} up · ${pair.down} down · ${pair.comments} comments`],
                [`${pair.person.name} → ${p.name}`, `${pair.up_back} up`],
                ["Reciprocity", `${Math.round(pair.reciprocity_pct)}%`],
                ["Same-day mutual up-votes", `${pair.same_day} ${pair.same_day === 1 ? "day" : "days"}`],
                ["Share of this member's votes", `${Math.round(pair.share_pct)}%`],
                ["Same network", pair.same_network ? "Yes (keyed network hash, last 30 days)" : "No"],
              ].map(([k, v]) => (
                <div key={k} className="rounded-[12px] bg-[var(--surface-app)] p-3">
                  <dt className="text-[12px] text-[var(--text-secondary)]">{k}</dt>
                  <dd className="mt-1 font-medium">{v}</dd>
                </div>
              ))}
            </dl>
            <Link href={`/admin/people/${pair.person.id}`} className="text-[var(--accent-trust)] hover:underline">
              Open {pair.person.name}&apos;s investigation
            </Link>
          </div>
        </AdminModal>
      ) : null}
    </div>
  );
}
