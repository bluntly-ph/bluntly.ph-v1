"use client";

import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { CaretDown } from "@phosphor-icons/react/dist/ssr";

import { ConfirmDialog } from "@/components/admin/ConfirmDialog";
import { countState } from "@/components/console/counted-model";
import { CountedTextarea } from "@/components/console/CountedTextarea";
import { formatScore, parseScore } from "@/components/admin/people/trust-score-model";
import { FIELD_STATES } from "@/components/console/fields";

const REASON_MAX = 1000;

async function detail(res: Response, fallback: string): Promise<string> {
  const p = (await res.json().catch(() => ({}))) as { detail?: unknown };
  return typeof p.detail === "string" ? p.detail : fallback;
}

export type TrustState = {
  computed: string | null;
  override: string | null;
  effective: string | null;
  overridden: boolean;
  reason: string | null;
  at: string | null;
};

/**
 * Menu/Person/Actions (Figma 8010:12514): mark or clear the investigation
 * (any staff; §11, votes count half) and suspend or reinstate the account
 * (Super Admin only; votes weigh nothing and the member is signed out). Staff
 * accounts are never suspended here: their role is changed in Users first.
 */
export function PersonActions({
  person,
  canSuspend,
  trust = null,
}: {
  person: { id: string; name: string; role: string; status: string };
  canSuspend: boolean;
  /**
   * The Trust Score override (owner 2026-10-05; RESEARCH 769c038): set, change
   * or clear it, with a reason, through PUT /admin/people/{id}/trust-score.
   * The dialog shows the system's score, the override and the effective one;
   * it never computes a score itself.
   */
  trust?: TrustState | null;
}) {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [confirm, setConfirm] = useState<"suspend" | "reinstate" | null>(null);
  const [override, setOverride] = useState<"set" | "clear" | null>(null);
  const [scoreText, setScoreText] = useState("");
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    function onClick(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    }
    window.addEventListener("mousedown", onClick);
    return () => window.removeEventListener("mousedown", onClick);
  }, [open]);

  const investigating = person.status === "investigating";
  const suspended = person.status === "suspended";
  const staff = person.role === "administrator" || person.role === "super_admin";

  const newScore = parseScore(scoreText);
  const overrideInvalid =
    reason.trim().length < 3 ||
    countState(reason, REASON_MAX).over ||
    (override === "set" && newScore === null);

  async function call(path: string, body: object, fallback: string): Promise<boolean> {
    setBusy(true);
    setError(null);
    try {
      const res = await fetch(`/api/bff/api/v1/admin/${path}`, {
        method: "PUT",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(body),
      });
      if (!res.ok) {
        setError(await detail(res, fallback));
        return false;
      }
      router.refresh();
      return true;
    } catch {
      setError("Couldn't reach the server.");
      return false;
    } finally {
      setBusy(false);
    }
  }

  const ITEM = "flex w-full rounded-[10px] px-3 py-[10px] text-left text-[14px] hover:bg-[var(--surface-app)] disabled:cursor-not-allowed disabled:text-[var(--text-muted)] disabled:hover:bg-transparent";
  const suspendBlocked = !canSuspend ? "Super Admin only" : staff ? "Staff accounts: change the role in Users first" : null;
  return (
    <div ref={ref} className="relative">
      <button
        type="button"
        onClick={() => setOpen(!open)}
        aria-expanded={open}
        aria-haspopup="menu"
        className="inline-flex h-9 items-center gap-2 rounded-full border border-[var(--base-ink-800)] px-4 text-[12px]"
      >
        Actions <CaretDown size={12} />
      </button>
      {open ? (
        <div role="menu" className="absolute right-0 top-[calc(100%+6px)] z-30 w-[244px] rounded-[16px] border border-[var(--border-subtle)] bg-[var(--surface-card)] p-[6px] shadow-[var(--shadow-modal)]">
          <button
            type="button"
            role="menuitem"
            disabled={busy}
            aria-label={investigating ? `Clear the investigation of ${person.name}` : `Mark ${person.name} under investigation`}
            onClick={async () => {
              if (await call(`users/${person.id}/investigation`, { under_investigation: !investigating }, "That didn't go through.")) setOpen(false);
            }}
            className={ITEM}
          >
            {investigating ? "Clear investigation" : "Mark under investigation"}
          </button>
          <button
            type="button"
            role="menuitem"
            disabled={Boolean(suspendBlocked)}
            title={suspendBlocked ?? undefined}
            onClick={() => {
              setOpen(false);
              setReason("");
              setError(null);
              setConfirm(suspended ? "reinstate" : "suspend");
            }}
            className={ITEM}
          >
            <span className="flex flex-col gap-[2px]">
              {suspended ? "Reinstate account" : "Suspend account"}
              {suspendBlocked ? <span className="text-[11px]">{suspendBlocked}</span> : null}
            </span>
          </button>
          {trust ? (
            <>
              <span role="separator" className="mx-3 my-1 block h-px bg-[var(--border-subtle)]" />
              <button
                type="button"
                role="menuitem"
                onClick={() => {
                  setOpen(false);
                  setReason("");
                  setError(null);
                  setScoreText(trust.overridden ? formatScore(trust.override) : "");
                  setOverride("set");
                }}
                className={ITEM}
              >
                {trust.overridden ? "Change Trust Score override" : "Set Trust Score override"}
              </button>
              {trust.overridden ? (
                <button
                  type="button"
                  role="menuitem"
                  onClick={() => {
                    setOpen(false);
                    setReason("");
                    setError(null);
                    setOverride("clear");
                  }}
                  className={ITEM}
                >
                  Clear Trust Score override
                </button>
              ) : null}
            </>
          ) : null}
          {error && !confirm && !override ? (
            <p role="alert" className="px-3 pb-2 text-[11px] text-[var(--accent-danger)]">
              {error}
            </p>
          ) : null}
        </div>
      ) : null}
      <ConfirmDialog
        open={confirm !== null}
        title={confirm === "suspend" ? `Suspend ${person.name}?` : `Reinstate ${person.name}?`}
        confirmLabel={confirm === "suspend" ? "Suspend account" : "Reinstate account"}
        busy={busy}
        disabled={reason.trim().length < 3 || countState(reason, REASON_MAX).over}
        tone={confirm === "suspend" ? "danger" : "primary"}
        error={error}
        onConfirm={async () => {
          if (await call(`people/${person.id}/suspension`, { suspended: confirm === "suspend", reason: reason.trim() }, "That didn't go through."))
            setConfirm(null);
        }}
        onClose={() => setConfirm(null)}
      >
        <p>
          {confirm === "suspend"
            ? "They are signed out and cannot sign in, and their votes stop counting. Their reviews stay as they are."
            : "They can sign in again and their votes count by their trust stage."}
        </p>
        <div className="mt-3">
          <CountedTextarea id="suspension-reason" label="Reason · kept in the activity log" value={reason} onChange={setReason} max={REASON_MAX} min={3} rows={3} />
        </div>
      </ConfirmDialog>
      {trust ? (
        <ConfirmDialog
          open={override !== null}
          title={
            override === "clear"
              ? `Clear ${person.name}'s Trust Score override?`
              : trust.overridden
                ? `Change ${person.name}'s Trust Score override`
                : `Set ${person.name}'s Trust Score override`
          }
          confirmLabel={override === "clear" ? "Clear override" : "Save override"}
          busy={busy}
          disabled={overrideInvalid}
          tone={override === "clear" ? "danger" : "primary"}
          error={error}
          onConfirm={async () => {
            const body = { score: override === "clear" ? null : newScore, reason: reason.trim() };
            if (await call(`people/${person.id}/trust-score`, body, "That didn't go through.")) setOverride(null);
          }}
          onClose={() => setOverride(null)}
        >
          <dl className="grid grid-cols-3 gap-3 rounded-[12px] bg-[var(--surface-app)] p-3 text-[12px]" data-testid="trust-readout">
            <div className="flex flex-col gap-1">
              <dt className="text-[var(--text-secondary)]">System score</dt>
              <dd className="text-[16px] font-medium tabular-nums">{formatScore(trust.computed)}</dd>
            </div>
            <div className="flex flex-col gap-1">
              <dt className="text-[var(--text-secondary)]">Admin override</dt>
              <dd className="text-[16px] font-medium tabular-nums">{trust.overridden ? formatScore(trust.override) : "None"}</dd>
            </div>
            <div className="flex flex-col gap-1">
              <dt className="text-[var(--text-secondary)]">Effective score</dt>
              <dd className="text-[16px] font-medium tabular-nums">{formatScore(trust.effective)}</dd>
            </div>
          </dl>
          {trust.overridden && trust.reason ? (
            <p className="mt-2 text-[12px] text-[var(--text-secondary)] [overflow-wrap:anywhere]">Current reason: {trust.reason}</p>
          ) : null}
          <p className="mt-3">
            {override === "clear"
              ? "The member goes back to the system's score. Vote weight and lenses follow it at once."
              : "The override replaces the system's score everywhere it is used (vote weight, lenses, the Honesty Fund). The trust stage does not change."}
          </p>
          {override === "set" ? (
            <div className="mt-3 flex flex-col gap-1">
              <label htmlFor="trust-score-new" className="text-[12px]">
                New score · 0 to 100
              </label>
              <input
                id="trust-score-new"
                inputMode="decimal"
                value={scoreText}
                onChange={(e) => setScoreText(e.target.value.slice(0, 6))}
                aria-invalid={scoreText.trim() !== "" && newScore === null}
                aria-describedby="trust-score-hint"
                className={`h-9 w-32 rounded-[10px] px-3 text-[14px] tabular-nums ${FIELD_STATES}`}
              />
              <span id="trust-score-hint" className="text-[11px] text-[var(--text-secondary)]">
                {scoreText.trim() !== "" && newScore === null ? "Enter a number from 0 to 100, up to two decimals." : "Up to two decimals, e.g. 72.5."}
              </span>
            </div>
          ) : null}
          <div className="mt-3">
            <CountedTextarea id="trust-score-reason" label="Reason · kept in the activity log" value={reason} onChange={setReason} max={REASON_MAX} min={3} rows={3} />
          </div>
        </ConfirmDialog>
      ) : null}
    </div>
  );
}
