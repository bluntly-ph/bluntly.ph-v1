"use client";

import { ArrowsClockwise, CheckCircle, WarningCircle, XCircle } from "@phosphor-icons/react/dist/ssr";

import { AdminModal } from "@/components/admin/AdminModal";

import { jobLine, needsRun, sortJobs, type JobTask } from "./jobs-model";

/**
 * Overlay/Admin/Jobs (Figma 8237:25609): every scheduled job, what it needs
 * and when it next runs. Run now opens the Activity log's own confirmation
 * (Confirm/Jobs/RunNow), which runs the job through the scheduler's period
 * lease. Money and data-deletion jobs are the Super Admin's to run by hand;
 * for anyone else their row has no button (the API refuses them too).
 */
export function JobsDialog({
  tasks,
  now,
  canRun,
  onRun,
  onClose,
}: {
  tasks: JobTask[];
  now: number;
  canRun: (task: string) => boolean;
  onRun: (task: string) => void;
  onClose: () => void;
}) {
  return (
    <AdminModal title="Scheduled jobs" width={560} onClose={onClose}>
      <ul className="flex flex-col px-6 py-2" data-testid="jobs-list">
        {sortJobs(tasks).map((t) => {
          const line = jobLine(t, now);
          const bad = t.state === "failed" || t.state === "overdue";
          return (
            <li key={t.task} data-testid="job-row" className="flex items-center gap-3 border-t border-[var(--border-subtle)] py-3 first:border-t-0">
              {bad ? (
                <WarningCircle size={18} weight="fill" className="shrink-0 text-[var(--accent-danger)]" aria-label="Needs a look" />
              ) : t.state === "never_run" ? (
                <XCircle size={18} className="shrink-0 text-[var(--text-muted)]" aria-label="Never run" />
              ) : t.state === "due" ? (
                <ArrowsClockwise size={18} className="shrink-0 text-[var(--chart-honesty-fund)]" aria-label="Due" />
              ) : (
                <CheckCircle size={18} weight="fill" className="shrink-0" aria-label="Healthy" />
              )}
              <span className="flex min-w-0 flex-1 flex-col gap-0.5">
                <span className="text-[14px]">{t.task.replaceAll("_", " ")}</span>
                <span className={`text-[12px] ${line.tone === "danger" ? "text-[var(--accent-danger)]" : "text-[var(--text-secondary)]"}`} suppressHydrationWarning>
                  {line.text}
                </span>
              </span>
              {needsRun(t) && canRun(t.task) ? (
                <button type="button" onClick={() => onRun(t.task)} className="h-8 shrink-0 rounded-full border border-[var(--border-subtle)] px-3 text-[12px] hover:bg-[var(--surface-app)]">
                  Run now
                </button>
              ) : null}
            </li>
          );
        })}
      </ul>
      <div className="border-t border-[var(--border-subtle)] px-6 py-4">
        <button type="button" onClick={onClose} className="h-9 rounded-full bg-[var(--accent-primary)] px-5 text-[12px] text-white">
          Done
        </button>
      </div>
    </AdminModal>
  );
}
