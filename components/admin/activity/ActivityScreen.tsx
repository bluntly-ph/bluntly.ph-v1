"use client";

import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import {
  ArrowsClockwise,
  CaretDown,
  Check,
  CheckCircle,
  Coins,
  Eye,
  FileText,
  Gear,
  Lightning,
  ShieldCheck,
  UserGear,
  WarningCircle,
  XCircle,
} from "@phosphor-icons/react/dist/ssr";

import { ConfirmDialog } from "@/components/admin/ConfirmDialog";
import { JobsDialog } from "@/components/admin/activity/JobsDialog";
import { AdminExportButton } from "@/components/admin/export/AdminExport";
import type { JobTask } from "@/components/admin/activity/jobs-model";
import { conversationVerb, dayCount } from "@/components/admin/activity/activity-model";
import { OUTCOME_VERB } from "@/components/admin/activity/activity-outcome";
import { VERB, words } from "@/components/admin/activity/activity-words";
import { TOP_SEARCH_STATES } from "@/components/ui/search-styles";
import { MENU_ITEM } from "@/components/console/fields";

type Schemas = import("@/lib/api-types").components["schemas"];
type Entry = Schemas["ActivityRow"];
type Summary = Schemas["ActivitySummaryOut"];
type Task = JobTask;

const GROUP_LABEL: Record<string, string> = { moderation: "Moderation", system: "System", money: "Money", access: "Access", privacy: "Privacy" };
const ICON: Record<string, typeof Gear> = { moderation: ShieldCheck, money: Coins, access: UserGear, privacy: Eye, system: Gear };
const TARGETS: [string, string][] = [
  ["review", "Reviews"],
  ["user", "Members"],
  ["question", "Questions"],
  ["answer", "Answers"],
  ["comment", "Comments"],
  ["seller_review", "Store reviews"],
];
const RANGES: [string, string][] = [
  ["today", "Today"],
  ["7d", "Last 7 days"],
  ["30d", "Last 30 days"],
  ["all", "All time"],
];
const JOB_NOTE: Record<string, string> = {
  integrity_sweep: "Re-checks every review for voting rings and reused photos.",
  recompute_wilson_scores: "Recomputes the helpfulness score of every review.",
  recompute_all_trust: "Recomputes every member's trust stage from their record.",
  priority_tiers: "Re-ranks the queue's priority tiers.",
  expire_requests: "Closes review requests past their deadline.",
  pii_retention: "Deletes personal data past its retention period.",
  refresh_payout_batches: "Refreshes the payout batches waiting to be sent.",
  honesty_fund_distribution: "Distributes this month's Honesty Fund.",
  schedule_payouts: "Schedules this month's payouts.",
  send_emails: "Sends the queued emails and retries the ones that failed.",
  weekly_summaries: "Queues each store owner's Monday summary.",
};
const SUPER_ONLY = new Set(["honesty_fund_distribution", "schedule_payouts", "refresh_payout_batches", "pii_retention"]);

const time = (iso: string) => new Date(iso).toLocaleTimeString("en-PH", { hour: "numeric", minute: "2-digit", timeZone: "Asia/Manila" });
const dayKey = (iso: string) => new Date(iso).toLocaleDateString("en-CA", { timeZone: "Asia/Manila" });

function dayLabel(key: string, now: number): string {
  const today = new Date(now).toLocaleDateString("en-CA", { timeZone: "Asia/Manila" });
  const yesterday = new Date(now - 86_400_000).toLocaleDateString("en-CA", { timeZone: "Asia/Manila" });
  const d = new Date(`${key}T12:00:00+08:00`);
  const pretty = d.toLocaleDateString("en-GB", { day: "numeric", month: "short", timeZone: "Asia/Manila" });
  if (key === today) return "Today";
  if (key === yesterday) return `Yesterday, ${pretty}`;
  // Built from parts: Node and the browser punctuate a full en-GB weekday date
  // differently ("Fri 9 Oct" / "Fri, 9 Oct"), which broke hydration.
  const weekday = d.toLocaleDateString("en-GB", { weekday: "short", timeZone: "Asia/Manila" });
  return `${weekday}, ${pretty}`;
}

function ago(iso: string | null, now: number): string {
  if (!iso) return "never";
  const h = Math.round((now - new Date(iso).getTime()) / 3_600_000);
  return h < 1 ? "within the hour" : h < 48 ? `${h}h ago` : `${Math.round(h / 24)} days ago`;
}

function Menu({ label, value, options, onPick }: { label: string; value: string; options: [string, string][]; onPick: (v: string | null) => void }) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const close = (e: MouseEvent) => ref.current && !ref.current.contains(e.target as Node) && setOpen(false);
    window.addEventListener("mousedown", close);
    return () => window.removeEventListener("mousedown", close);
  }, [open]);
  const current = options.find(([k]) => k === value)?.[1] ?? label;
  return (
    <div ref={ref} className="relative">
      <button type="button" aria-haspopup="menu" aria-expanded={open} onClick={() => setOpen(!open)} className="flex h-8 items-center gap-2 rounded-full border border-[var(--border-subtle)] bg-[var(--surface-card)] px-3 text-[12px]">
        {current} <CaretDown size={12} />
      </button>
      {open ? (
        <div role="menu" aria-label={label} className="absolute left-0 top-[calc(100%+6px)] z-30 max-h-[320px] w-[220px] overflow-y-auto rounded-[16px] border border-[var(--border-subtle)] bg-[var(--surface-card)] p-[6px] shadow-[var(--shadow-modal)]">
          {[["", label] as [string, string], ...options].map(([k, text]) => (
            <button
              key={k || "any"}
              type="button"
              role="menuitemradio"
              aria-checked={value === k}
              onClick={() => {
                setOpen(false);
                onPick(k || null);
              }}
              className={MENU_ITEM}
            >
              {text}
              {value === k ? <Check size={16} aria-hidden /> : null}
            </button>
          ))}
        </div>
      ) : null}
    </div>
  );
}

function Card({ title, sub, children }: { title: string; sub?: string; children: React.ReactNode }) {
  return (
    <section aria-label={title} className="rounded-[16px] border border-[var(--border-subtle)] bg-[var(--surface-card)] p-4">
      <h2 className="text-[16px] font-semibold leading-none">{title}</h2>
      {sub ? <p className="mt-1 text-[12px] text-[var(--text-secondary)]">{sub}</p> : null}
      <div className="mt-3">{children}</div>
    </section>
  );
}

/**
 * Admin Activity log (Figma Screen/Admin/ActivityLog 8074:16245): everything
 * the team and the system did, newest first and grouped by day, with the
 * Person / Action / Target / Range menus (8080:*) and a search; beside it the
 * scheduled jobs (Run now: Confirm/Jobs/RunNow 8081:16369), today by type,
 * proof-of-purchase views this week and the team's actions today.
 */
export function ActivityScreen({
  entries,
  total,
  summary,
  tasks,
  limit,
  canRunAll,
  now,
}: {
  entries: Entry[] | null;
  total: number;
  summary: Summary | null;
  tasks: Task[] | null;
  limit: number;
  canRunAll: boolean;
  now: number;
}) {
  const router = useRouter();
  const pathname = usePathname() ?? "/admin/activity";
  const params = useSearchParams();
  const [q, setQ] = useState(params.get("q") ?? "");
  const [running, setRunning] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [runError, setRunError] = useState<string | null>(null);
  const [ran, setRan] = useState<string | null>(null);
  const [jobsOpen, setJobsOpen] = useState(false);

  function go(changes: Record<string, string | null>) {
    const next = new URLSearchParams(params.toString());
    for (const [k, v] of Object.entries(changes)) {
      if (v === null || v === "") next.delete(k);
      else next.set(k, v);
    }
    if (!("limit" in changes)) next.delete("limit");
    router.push(`${pathname}?${next.toString()}`, { scroll: false });
  }

  async function runNow(task: string) {
    setBusy(true);
    setRunError(null);
    try {
      const res = await fetch(`/api/bff/api/v1/admin/jobs/${task}/run`, { method: "POST" });
      const body = (await res.json().catch(() => ({}))) as { detail?: unknown; status?: string };
      if (!res.ok) return setRunError(typeof body.detail === "string" ? body.detail : "The job could not be started.");
      setRan(`${words(task)}: ${words(body.status ?? "done").replace(/^skipped /, "")}`);
      setRunning(null);
      router.refresh();
    } catch {
      setRunError("Couldn't reach the server.");
    } finally {
      setBusy(false);
    }
  }

  const range = params.get("range") ?? "7d";
  // The summary's "today" counts every action today, so it only stands in for
  // the Today header when nothing narrows the list.
  const unfiltered = !["q", "actor", "action", "target"].some((k) => params.get(k));
  const days: { key: string; rows: Entry[] }[] = [];
  for (const e of entries ?? []) {
    const key = dayKey(e.at);
    if (days.at(-1)?.key !== key) days.push({ key, rows: [] });
    days.at(-1)?.rows.push(e);
  }
  const unhealthy = (tasks ?? []).filter((t) => t.state === "failed" || t.state === "overdue");
  const healthy = (tasks ?? []).filter((t) => !unhealthy.includes(t));
  const healthyCount = (tasks ?? []).filter((t) => t.state === "healthy").length;
  const shownHealthy = healthy.slice(0, 3);
  const types = summary ? (Object.entries(summary.by_type) as [string, number][]) : [];
  const maxType = Math.max(1, ...types.map(([, n]) => n));

  return (
    <div className="flex flex-col gap-4">
      {/* Screen/Admin/ActivityLog (8074:16245): the line sits just under the
          title, Export CSV at its right. */}
      <div className="-mt-3 flex flex-wrap items-start gap-3">
        <p className="flex-1 text-[14px] text-[var(--text-secondary)]">Everything your team and the system did, newest first. Kept permanently.</p>
        <AdminExportButton initial={["activity", "moderation"]} />
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <form
          role="search"
          onSubmit={(e) => {
            e.preventDefault();
            go({ q: q.trim() || null });
          }}
        >
          <input value={q} onChange={(e) => setQ(e.target.value)} aria-label="Search actions, people or IDs" placeholder="Search actions, people or IDs" className={`h-8 w-[256px] rounded-[10px] px-3 text-[12px] caret-[var(--accent-primary)] outline-none placeholder:text-[var(--text-secondary)] ${TOP_SEARCH_STATES}`} />
        </form>
        <Menu label="Anyone" value={params.get("actor") ?? ""} options={[...(summary?.actors ?? []).map((a) => [a.id, a.name ?? "Staff member"] as [string, string]), ["system", "System"]]} onPick={(v) => go({ actor: v })} />
        <Menu label="All actions" value={params.get("action") ?? ""} options={Object.entries(GROUP_LABEL)} onPick={(v) => go({ action: v })} />
        <Menu label="All targets" value={params.get("target") ?? ""} options={TARGETS} onPick={(v) => go({ target: v })} />
        <Menu label="Last 7 days" value={range === "7d" ? "" : range} options={RANGES.filter(([k]) => k !== "7d")} onPick={(v) => go({ range: v })} />
      </div>

      <div className="grid grid-cols-[minmax(0,1fr)] gap-4 lg:grid-cols-[minmax(0,1fr)_328px]">
        <div className="flex min-w-0 flex-col gap-4">
          {entries === null ? (
            <p role="alert" className="rounded-[16px] border border-[var(--border-subtle)] p-6 text-[14px] text-[var(--text-secondary)]">The activity log could not be loaded.</p>
          ) : days.length === 0 ? (
            <p className="rounded-[16px] border border-[var(--border-subtle)] p-6 text-center text-[14px] text-[var(--text-secondary)]">Nothing recorded for these filters.</p>
          ) : (
            days.map((d, i) => (
              <section key={d.key} aria-label={dayLabel(d.key, now)} className="overflow-hidden rounded-[16px] border border-[var(--border-subtle)] bg-[var(--surface-card)]">
                <div className="flex items-center justify-between bg-[var(--surface-app)] px-4 py-3 text-[14px]">
                  <span className="font-medium" suppressHydrationWarning>{dayLabel(d.key, now)}</span>
                  <span className="text-[12px] text-[var(--text-secondary)]">
                    {dayCount(d.rows.length, {
                      today: unfiltered && dayLabel(d.key, now) === "Today" ? summary?.today_total : null,
                      cut: i === days.length - 1 && (entries?.length ?? 0) < total,
                    })}
                  </span>
                </div>
                <ul>
                  {d.rows.map((e) => {
                    const group = e.actor_id ? (e.group ?? "moderation") : "system";
                    const Icon = ICON[group] ?? Gear;
                    const target = e.target_label ? (e.href ? <Link href={e.href} className="font-medium hover:underline">{e.target_label}</Link> : <span className="font-medium">{e.target_label}</span>) : null;
                    const conv = e.action === "conversation" ? conversationVerb(e.notes) : null;
                    return (
                      <li key={e.id} data-testid="activity-entry" className="flex gap-3 border-t border-[var(--border-subtle)] px-4 py-3 first:border-t-0">
                        <span className="grid size-8 shrink-0 place-items-center rounded-full bg-[var(--surface-app)] text-[var(--text-secondary)]"><Icon size={16} aria-hidden /></span>
                        <div className="min-w-0 flex-1">
                          <p className="text-[14px] leading-[1.45]">
                            <span className="font-medium">{e.actor ?? "System"}</span> {conv ? conv.before : ((e.outcome ? OUTCOME_VERB[e.outcome] : undefined) ?? VERB[e.action] ?? words(e.action))} {target ?? (conv ? "a conversation" : null)}
                            {conv?.after ? ` ${conv.after}` : ""}
                          </p>
                          <p className="mt-[2px] text-[12px] text-[var(--text-secondary)]">
                            {GROUP_LABEL[group]} · {e.target_type ? words(e.target_type) : conv ? "Inbox" : "—"}
                            {e.target_ref ? ` ${e.target_ref.slice(0, 8)}` : ""}
                            {e.reason ? ` · Reason: ${words(e.reason)}` : ""}
                          </p>
                          {e.notes && !conv ? <p className="mt-2 rounded-[10px] bg-[var(--surface-app)] px-3 py-2 text-[13px]">{e.notes}</p> : null}
                        </div>
                        <span className="shrink-0 text-[12px] text-[var(--text-secondary)]" suppressHydrationWarning>{time(e.at)}</span>
                      </li>
                    );
                  })}
                </ul>
              </section>
            ))
          )}
          {entries && entries.length < total ? (
            <button type="button" onClick={() => go({ limit: String(Math.min(200, limit + 50)) })} disabled={limit >= 200} className="self-center text-[13px] text-[var(--accent-primary)] disabled:opacity-50">
              {limit >= 200 ? `Showing the latest 200 of ${total.toLocaleString("en-PH")} — narrow the filters` : "Load older"}
            </button>
          ) : null}
        </div>

        <aside className="flex flex-col gap-4">
          <Card title="Scheduled jobs" sub={tasks ? `${healthyCount} of ${tasks.length} healthy` : "Unavailable"}>
            {ran ? <p role="status" className="mb-2 text-[12px] text-[var(--accent-success)]">{ran}</p> : null}
            <ul className="flex flex-col gap-2">
              {unhealthy.map((t) => (
                <li key={t.task} data-testid="job-unhealthy" className="rounded-[12px] bg-[color-mix(in_srgb,var(--accent-danger)_10%,transparent)] p-3">
                  <p className="flex items-center gap-2 text-[14px] font-medium">
                    <WarningCircle size={16} weight="fill" className="text-[var(--accent-danger)]" aria-hidden />
                    <span className="flex-1">{words(t.task)}</span>
                  </p>
                  <p className="mt-1 text-[12px] text-[var(--text-secondary)]">
                    {t.state === "failed" ? `${t.last_run?.failure ?? "Failed"}. ` : "Overdue. "}Last success {ago(t.last_success_at, now)}.
                  </p>
                  {canRunAll || !SUPER_ONLY.has(t.task) ? (
                    <button type="button" onClick={() => setRunning(t.task)} className="mt-2 h-8 rounded-full border border-[var(--text-primary)] bg-[var(--surface-card)] px-3 text-[12px]">
                      Run now
                    </button>
                  ) : null}
                </li>
              ))}
              {shownHealthy.map((t) => (
                <li key={t.task} className="flex items-center gap-2 text-[13px]">
                  {t.state === "healthy" ? <CheckCircle size={16} weight="fill" className="text-[var(--accent-success)]" aria-hidden /> : t.state === "never_run" ? <XCircle size={16} className="text-[var(--text-muted)]" aria-hidden /> : <ArrowsClockwise size={16} className="text-[var(--chart-honesty-fund)]" aria-hidden />}
                  <span className="flex-1 truncate">{words(t.task)}</span>
                  {canRunAll || !SUPER_ONLY.has(t.task) ? (
                    <button type="button" aria-label={`Run ${words(t.task)} now`} onClick={() => setRunning(t.task)} className="text-[12px] text-[var(--text-secondary)] hover:text-[var(--text-primary)]">
                      {t.state === "healthy" ? `ok ${ago(t.last_success_at, now)}` : t.state === "never_run" ? "never run" : words(t.state)}
                    </button>
                  ) : (
                    <span className="text-[12px] text-[var(--text-secondary)]">{t.state === "healthy" ? `ok ${ago(t.last_success_at, now)}` : words(t.state)}</span>
                  )}
                </li>
              ))}
            </ul>
            {tasks && tasks.length > 0 ? (
              <button type="button" onClick={() => setJobsOpen(true)} className="mt-2 text-[12px] text-[var(--chart-honesty-fund)]">
                {healthy.length > 3 ? `See all jobs (+${healthy.length - 3} more)` : "See all jobs"}
              </button>
            ) : null}
          </Card>

          {summary ? (
            <>
              <Card title="Today by type" sub={`${summary.today_total} action${summary.today_total === 1 ? "" : "s"}`}>
                <ul className="flex flex-col gap-3">
                  {types.map(([k, n]) => (
                    <li key={k}>
                      <p className="flex justify-between text-[14px]"><span>{GROUP_LABEL[k]}</span><span>{n}</span></p>
                      <span className="mt-1 block h-[5px] rounded-full bg-[var(--surface-app)]">
                        <span className="block h-full rounded-full bg-[var(--accent-primary)]" style={{ width: `${Math.round((n / maxType) * 100)}%` }} />
                      </span>
                    </li>
                  ))}
                </ul>
              </Card>
              <Card title="Proof-of-purchase views" sub="Private evidence opened this week">
                {summary.receipt_views.length === 0 ? (
                  <p className="text-[13px] text-[var(--text-secondary)]">None this week.</p>
                ) : (
                  <ul className="flex flex-col gap-2">
                    {summary.receipt_views.map((v, i) => (
                      <li key={i} className="flex items-baseline justify-between gap-2 text-[13px]">
                        <span className="min-w-0 truncate">
                          <span className="font-medium">{v.actor ?? "System"}</span> viewed {v.href ? <Link href={v.href} className="hover:underline">{v.target}</Link> : v.target}
                        </span>
                        <span className="shrink-0 text-[12px] text-[var(--text-secondary)]" suppressHydrationWarning>{dayLabel(dayKey(v.at), now).split(",")[0]}</span>
                      </li>
                    ))}
                  </ul>
                )}
              </Card>
              <Card title="Team today" sub="Actions per person">
                {summary.team_today.length === 0 ? (
                  <p className="text-[13px] text-[var(--text-secondary)]">No staff action yet today.</p>
                ) : (
                  <ul className="flex flex-col gap-2">
                    {summary.team_today.map((t) => (
                      <li key={t.id} className="flex justify-between text-[14px]">
                        <button type="button" onClick={() => go({ actor: t.id, range: "today" })} className="truncate text-left hover:underline">{t.name ?? "Staff member"}</button>
                        <span>{t.count}</span>
                      </li>
                    ))}
                  </ul>
                )}
              </Card>
            </>
          ) : null}
        </aside>
      </div>

      {jobsOpen && tasks ? (
        <JobsDialog
          tasks={tasks}
          now={now}
          canRun={(task) => canRunAll || !SUPER_ONLY.has(task)}
          onRun={(task) => setRunning(task)}
          onClose={() => setJobsOpen(false)}
        />
      ) : null}
      <ConfirmDialog
        open={running !== null}
        title={running ? `Run ${words(running)} now?` : ""}
        confirmLabel="Run now"
        busy={busy}
        error={runError}
        onConfirm={() => running && void runNow(running)}
        onClose={() => setRunning(null)}
      >
        <ul className="flex flex-col gap-2">
          <li className="flex gap-2"><ArrowsClockwise size={16} className="mt-[2px] shrink-0" aria-hidden />{running ? JOB_NOTE[running] ?? "Runs the job for its current period." : ""}</li>
          <li className="flex gap-2"><Lightning size={16} className="mt-[2px] shrink-0" aria-hidden />Runs once per period: a period already done or in progress is left as it is.</li>
          <li className="flex gap-2"><FileText size={16} className="mt-[2px] shrink-0" aria-hidden />The run is recorded with the scheduled jobs.</li>
        </ul>
      </ConfirmDialog>
    </div>
  );
}

