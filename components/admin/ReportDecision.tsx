"use client";

import { useRouter } from "next/navigation";
import { useId, useState } from "react";

import { ConfirmDialog } from "@/components/admin/ConfirmDialog";
import type { ReportItem } from "@/lib/moderation";
import { FIELD_STATES } from "@/components/console/fields";

/**
 * The four answers an administrator can give one community report.
 *
 * BUSINESS-REQUIRED / DESIGN-SYSTEM ALIGNED (owner §30, 2026-09-16). The report
 * tab had no frame with controls and no endpoint behind one; both now exist
 * (`POST /admin/reports/{id}/decision`, migration 0049). Built from the
 * console's own pill-and-panel vocabulary, like the queue's decision bar.
 *
 *   Dismiss   the content stands. The report closes; nothing is done to it.
 *   Remove    the reported review is unpublished — it leaves the public site
 *             and returns to the review queue for a decision.
 *   Restore   a review that is down goes back up.
 *   Escalate  nothing is done to the content; the report is marked for a senior
 *             decision and leaves the open queue.
 *
 * Remove and Restore are armed before they fire, because both change what the
 * public can see. Dismiss is one press. Escalate asks first and says who gets it
 * (MQA-005): the report moves to Status › Escalated, every Super Admin is told,
 * and the screen follows it there, so it is never "lost". A Super Admin gives an
 * escalated report its final answer with the same controls, minus Escalate.
 *
 * Which pair is offered depends on the target. Only a review can be removed or
 * restored — a reported question or answer has no publish state this endpoint
 * can move — so for anything else the two content controls are absent rather
 * than present and failing.
 */

type Resolution = "dismissed" | "content_removed" | "content_restored" | "escalated";

export function ReportDecision({ item }: { item: ReportItem }) {
  const router = useRouter();
  const [confirmEscalate, setConfirmEscalate] = useState(false);
  const escalated = item.report.resolution === "escalated";
  const noteId = useId();
  const [note, setNote] = useState("");
  const [armed, setArmed] = useState<Resolution | null>(null);
  const [busy, setBusy] = useState<Resolution | null>(null);
  const [error, setError] = useState<string | null>(null);

  const target = item.target;
  const canActOnContent = target !== null;

  async function decide(resolution: Resolution) {
    if (busy) return;
    setBusy(resolution);
    setError(null);
    try {
      const res = await fetch(
        `/api/bff/api/v1/admin/reports/${item.report.id}/decision`,
        {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({ resolution, notes: note.trim() || null }),
        },
      );
      if (!res.ok) {
        const problem = (await res.json().catch(() => ({}))) as {
          detail?: string;
          title?: string;
        };
        setError(problem.detail ?? problem.title ?? "Couldn't record the decision.");
        return;
      }
      if (resolution === "escalated") {
        // Follow the report to where it now lives, open, with its new state.
        router.push(`/admin/review-queue?tab=report&rstatus=escalated&report=${item.report.id}`, { scroll: false });
        setConfirmEscalate(false);
        return;
      }
      router.refresh();
    } catch {
      setError("Couldn't reach the server.");
    } finally {
      setBusy(null);
      setArmed(null);
    }
  }

  const pill =
    "h-8 cursor-pointer rounded-[var(--radius-pill)] px-3 text-[12px] font-semibold " +
    "disabled:cursor-wait disabled:opacity-60 focus-visible:outline focus-visible:outline-2 " +
    "focus-visible:outline-offset-2 focus-visible:outline-[var(--accent-primary)]";

  return (
    <div className="mt-3 flex flex-col gap-2 border-t border-[var(--line-hairline-10)] pt-3">
      <label htmlFor={noteId} className="sr-only">
        Decision note for this report
      </label>
      <input
        id={noteId}
        value={note}
        onChange={(e) => setNote(e.target.value.slice(0, 1000))}
        placeholder="Note for the audit log (optional)"
        className={`h-8 rounded-[var(--radius-sm)] px-2.5 text-[12px] ${FIELD_STATES}`}
      />
      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          onClick={() => void decide("dismissed")}
          disabled={busy !== null || armed !== null}
          className={`${pill} border border-[var(--accent-success)] text-[var(--text-primary)]`}
        >
          {busy === "dismissed" ? "Dismissing…" : "Dismiss"}
        </button>

        {canActOnContent && target.is_published ? (
          <ContentAction
            resolution="content_removed"
            label="Remove content"
            confirmLabel="Confirm removal"
            tone="bg-[var(--accent-danger)]"
            armed={armed}
            busy={busy}
            pill={pill}
            onArm={setArmed}
            onConfirm={decide}
          />
        ) : null}

        {canActOnContent && !target.is_published ? (
          <ContentAction
            resolution="content_restored"
            label="Restore content"
            confirmLabel="Confirm restore"
            tone="bg-[var(--accent-success)]"
            armed={armed}
            busy={busy}
            pill={pill}
            onArm={setArmed}
            onConfirm={decide}
          />
        ) : null}

        {escalated ? null : (
          <button
            type="button"
            onClick={() => setConfirmEscalate(true)}
            disabled={busy !== null || armed !== null}
            className={`${pill} border border-[var(--base-ink-800)] text-[var(--text-secondary)]`}
          >
            Escalate
          </button>
        )}
      </div>
      <ConfirmDialog
        open={confirmEscalate}
        title="Escalate to a Super Admin?"
        confirmLabel="Escalate"
        busyLabel="Escalating…"
        busy={busy === "escalated"}
        error={error}
        tone="ink"
        onConfirm={() => void decide("escalated")}
        onClose={() => setConfirmEscalate(false)}
      >
        <p>Every Super Admin is notified and one of them decides it. The content stays as it is meanwhile.</p>
        <p>The report moves to Status › Escalated, where you can still find it.</p>
      </ConfirmDialog>

      {!canActOnContent ? (
        <p className="text-[10px] text-[var(--text-muted)]">
          This report is not against a review, so it can only be dismissed{escalated ? "" : " or escalated"} from here.
        </p>
      ) : null}

      {error ? (
        <p role="alert" className="text-[12px] text-[var(--accent-danger)]">
          {error}
        </p>
      ) : null}
    </div>
  );
}

/**
 * A control that changes what the public sees: press, then confirm.
 *
 * At module scope, not inside `ReportDecision`. A component declared during
 * render is a new type on every render, so React unmounts and remounts its
 * subtree — which, on a confirm control, is exactly the state you do not want
 * thrown away mid-press. `react-hooks/static-components` is the rule; losing
 * the armed state is the bug.
 */
function ContentAction({
  resolution,
  label,
  confirmLabel,
  tone,
  armed,
  busy,
  pill,
  onArm,
  onConfirm,
}: {
  resolution: Resolution;
  label: string;
  confirmLabel: string;
  tone: string;
  armed: Resolution | null;
  busy: Resolution | null;
  pill: string;
  onArm: (resolution: Resolution | null) => void;
  onConfirm: (resolution: Resolution) => void;
}) {
  if (armed === resolution) {
    return (
      <>
        <button
          type="button"
          onClick={() => onConfirm(resolution)}
          disabled={busy !== null}
          className={`${pill} ${tone} text-white`}
        >
          {busy === resolution ? "Working\u2026" : confirmLabel}
        </button>
        <button
          type="button"
          onClick={() => onArm(null)}
          disabled={busy !== null}
          className={`${pill} border border-[var(--base-ink-800)] text-[var(--text-primary)]`}
        >
          Cancel
        </button>
      </>
    );
  }
  return (
    <button
      type="button"
      onClick={() => onArm(resolution)}
      disabled={busy !== null || armed !== null}
      className={`${pill} border border-[var(--base-ink-800)] text-[var(--text-primary)]`}
    >
      {label}
    </button>
  );
}

export default ReportDecision;
