/**
 * Overlay/Admin/Jobs (Figma 8237:25609): one line per scheduled job, from the
 * scheduler's own record (GET /admin/cron-runs). Pure, so tests/frontend can
 * check it.
 */

export type JobTask = {
  task: string;
  cadence: string;
  /** healthy | due | overdue | failed | never_run */
  state: string;
  due_at: string;
  next_at?: string | null;
  last_success_at: string | null;
  last_run: { status: string; failure: string | null; started_at: string } | null;
};

export type JobLine = { text: string; tone: "danger" | "muted" };

const MANILA = "Asia/Manila";
const clock = (iso: string) => new Date(iso).toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit", timeZone: MANILA });
const date = (iso: string) => `${new Date(iso).toLocaleDateString("en-GB", { day: "numeric", month: "short", timeZone: MANILA })}, ${clock(iso)}`;

/** "12 min ago", "3h ago", "1 day ago", "never". */
export function agoText(iso: string | null | undefined, now: number): string {
  if (!iso) return "never";
  const min = Math.max(0, Math.round((now - new Date(iso).getTime()) / 60_000));
  if (min < 60) return `${Math.max(1, min)} min ago`;
  const h = Math.round(min / 60);
  if (h < 24) return `${h}h ago`;
  const d = Math.round(h / 24);
  return d === 1 ? "1 day ago" : `${d} days ago`;
}

/** "Next in 20h", "Next in 45 min". */
export function nextIn(iso: string, now: number): string {
  const min = Math.max(1, Math.round((new Date(iso).getTime() - now) / 60_000));
  return min < 60 ? `Next in ${min} min` : `Next in ${Math.round(min / 60)}h`;
}

export function jobLine(t: JobTask, now: number): JobLine {
  const lastOk = `last success ${agoText(t.last_success_at, now)}`;
  // A monthly job's due moment can be days back: give it its date.
  const since = t.cadence === "monthly" ? date(t.due_at) : clock(t.due_at);
  if (t.state === "failed") return { text: `Failed at ${clock(t.last_run?.started_at ?? t.due_at)} · ${lastOk}`, tone: "danger" };
  if (t.state === "overdue") return { text: `Overdue since ${since} · ${lastOk}`, tone: "danger" };
  if (t.state === "due") return { text: "Due now · the scheduler picks it up shortly", tone: "muted" };
  if (t.state === "never_run") {
    if (new Date(t.due_at).getTime() <= now) return { text: `Never run · due since ${since}`, tone: "muted" };
    return { text: t.next_at ? `Never run · due ${date(t.next_at)}` : "Never run", tone: "muted" };
  }
  if (t.cadence === "hourly") return { text: `Every hour · last run ${agoText(t.last_run?.started_at, now)}`, tone: "muted" };
  if (!t.next_at) return { text: `Last success ${agoText(t.last_success_at, now)}`, tone: "muted" };
  if (t.cadence === "monthly") return { text: date(t.next_at), tone: "muted" };
  return { text: nextIn(t.next_at, now), tone: "muted" };
}

/** Needs a look first, then the rest by name. */
export function sortJobs(tasks: JobTask[]): JobTask[] {
  const rank = (s: string) => (s === "failed" ? 0 : s === "overdue" ? 1 : s === "never_run" ? 2 : s === "due" ? 3 : 4);
  return [...tasks].sort((a, b) => rank(a.state) - rank(b.state) || a.task.localeCompare(b.task));
}

/** Run now shows where a run is useful: anything not healthy. */
export const needsRun = (t: JobTask) => t.state !== "healthy";
