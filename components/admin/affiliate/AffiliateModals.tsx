"use client";

import { useRouter } from "next/navigation";
import { useState, type ReactNode } from "react";
import { ArrowSquareOut, FileText, WarningCircle } from "@phosphor-icons/react/dist/ssr";

import { AdminModal } from "@/components/admin/AdminModal";

type Schemas = import("@/lib/api-types").components["schemas"];
type Preview = Schemas["LifecycleImportResult"];
type Month = Schemas["AffiliateMonthOut"];

/** ₱ with the centavos muted, as the frames set money. */
export function Peso({ value, signed = false }: { value: string | number | null | undefined; signed?: boolean }) {
  if (value === null || value === undefined) return <span className="text-[var(--text-secondary)]">—</span>;
  const n = Number(value);
  const [whole, cents] = Math.abs(n).toLocaleString("en-PH", { minimumFractionDigits: 2, maximumFractionDigits: 2 }).split(".");
  return (
    <span className="[font-variant-numeric:tabular-nums]">
      {signed && n < 0 ? "-" : ""}₱{whole}
      <span className="text-[var(--text-secondary)]">.{cents}</span>
    </span>
  );
}

export const FORMAT: Record<string, { platform: string; label: string }> = {
  shopee_commission_report: { platform: "Shopee", label: "Shopee export" },
  lazada_conversion_report: { platform: "Lazada", label: "Lazada export" },
};

const PLATFORM: Record<string, string> = { shopee: "Shopee", lazada: "Lazada", amazon: "Amazon", other: "Other" };
export const platformLabel = (p: string | null | undefined) => (p ? (PLATFORM[p] ?? p) : "—");
export const monthLabel = (iso: string) =>
  new Date(`${iso.slice(0, 7)}-01T00:00:00Z`).toLocaleDateString("en-PH", { month: "long", year: "numeric", timeZone: "UTC" });

function Line({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex items-baseline gap-4 border-b border-[var(--border-subtle)] py-[9px] last:border-b-0">
      <span className="w-[140px] shrink-0 text-[14px] text-[var(--text-secondary)]">{label}</span>
      <span className="flex min-w-0 flex-wrap items-baseline gap-2 text-[14px]">{children}</span>
    </div>
  );
}

const Note = ({ children }: { children: ReactNode }) => <span className="text-[12px] text-[var(--text-secondary)]">{children}</span>;

function Check({ n, children }: { n: number; children: ReactNode }) {
  return (
    <>
      {n > 0 ? <WarningCircle size={14} weight="fill" className="self-center text-[var(--accent-danger)]" aria-hidden /> : null}
      <span>{n.toLocaleString("en-PH")}</span>
      <Note>{children}</Note>
    </>
  );
}

async function detail(res: Response, fallback: string): Promise<string> {
  const p = (await res.json().catch(() => ({}))) as { detail?: unknown };
  return typeof p.detail === "string" ? p.detail : fallback;
}

/** Dry-run a report (POST /admin/affiliate/preview writes nothing). */
export async function previewReport(file: File): Promise<{ preview?: Preview; error?: string }> {
  try {
    const body = new FormData();
    body.append("file", file, file.name);
    const res = await fetch("/api/bff/api/v1/admin/affiliate/preview", { method: "POST", body });
    if (!res.ok) return { error: await detail(res, "The file couldn't be read.") };
    return { preview: (await res.json()) as Preview };
  } catch {
    return { error: "Couldn't reach the server." };
  }
}

/**
 * Overlay/Affiliate/Import (Figma 8017:12742). The chosen file has been
 * dry-run (previewReport); the modal states what it will do, and Apply import
 * runs the same file for real. Re-importing an order is a no-op on the
 * marketplace's own transaction identity.
 */
export function ImportReportModal({
  file,
  preview,
  previewError,
  onClose,
}: {
  file: File;
  preview: Preview | null;
  previewError: string | null;
  onClose: () => void;
}) {
  const router = useRouter();
  const [applyError, setApplyError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const error = applyError ?? previewError;

  async function apply() {
    setBusy(true);
    setApplyError(null);
    try {
      const body = new FormData();
      body.append("file", file, file.name);
      const res = await fetch("/api/bff/api/v1/admin/affiliate/import", { method: "POST", body });
      if (!res.ok) return setApplyError(await detail(res, "The file couldn't be imported."));
      onClose();
      router.refresh();
    } catch {
      setApplyError("Couldn't reach the server.");
    } finally {
      setBusy(false);
    }
  }

  const fmt = preview ? FORMAT[preview.format] : undefined;
  return (
    <AdminModal title="Import report" width={560} onClose={onClose}>
      <div className="flex flex-col gap-4 overflow-y-auto px-6 pb-5 pt-4">
        <div className="flex items-center gap-3 rounded-[16px] border border-[var(--border-subtle)] p-2 pr-4">
          <span className="grid size-[50px] shrink-0 place-items-center rounded-[10px] bg-[var(--surface-app)]">
            <FileText size={20} aria-hidden />
          </span>
          <span className="flex min-w-0 flex-1 flex-col gap-1 leading-none">
            <span className="truncate text-[16px]">{file.name}</span>
            <span className="text-[12px] text-[var(--text-secondary)]" data-testid="import-detected">
              {preview ? `${fmt ? `${fmt.label} · detected` : "Not a Shopee or Lazada report"} · ${preview.total_rows.toLocaleString("en-PH")} rows` : error ? "Couldn't be read" : "Reading…"}
            </span>
          </span>
          <ArrowSquareOut size={16} className="text-[var(--text-secondary)]" aria-hidden />
        </div>
        {preview && fmt ? (
          <>
            <div>
              <p className="pb-1 text-[12px] text-[var(--text-secondary)]">What this file will do</p>
              <Line label="Recognised">
                <Peso value={preview.recognised_amount} />
                <Note>{preview.recognised.toLocaleString("en-PH")} orders</Note>
              </Line>
              <Line label="Reversed">
                <Peso value={preview.reversed_amount} />
                <Note>{preview.reversed.toLocaleString("en-PH")} returns</Note>
              </Line>
              <Line label="Absorbed">
                <Peso value={preview.unrecovered_amount} />
                <Note>already paid out</Note>
              </Line>
              <Line label="Rows">
                <span>{preview.total_rows.toLocaleString("en-PH")}</span>
                <Note>{preview.unchanged.toLocaleString("en-PH")} unchanged</Note>
              </Line>
            </div>
            <div>
              <p className="pb-1 text-[12px] text-[var(--text-secondary)]">To check</p>
              <Line label="Unattributed">
                <Check n={preview.unattributed}>sales with no review, paid to nobody</Check>
              </Line>
              <Line label="Refused">
                <Check n={preview.refused}>status changes the ledger refuses</Check>
              </Line>
              <Line label="Unidentified">
                <Check n={preview.unidentified}>rows with no order ID, skipped</Check>
              </Line>
            </div>
          </>
        ) : null}
        {error ? (
          <p role="alert" className="text-[12px] text-[var(--accent-danger)]">
            {error}
          </p>
        ) : null}
      </div>
      <div className="flex items-center gap-3 border-t border-[var(--border-subtle)] px-6 py-4">
        <p className="flex-1 text-[12px] text-[var(--text-secondary)]">Nothing changes until you apply. Re-importing an order never credits it twice.</p>
        <button type="button" onClick={onClose} className="h-9 rounded-full border border-[var(--text-primary)] px-4 text-[12px]">
          Cancel
        </button>
        <button
          type="button"
          disabled={!preview || !fmt || busy}
          onClick={() => void apply()}
          className="h-9 rounded-full bg-[var(--accent-primary)] px-4 text-[12px] text-white disabled:opacity-50"
        >
          {busy ? "Applying…" : "Apply import"}
        </button>
      </div>
    </AdminModal>
  );
}

/**
 * Overlay/Affiliate/Remittance (Figma 8017:12816): the marketplace paid Bluntly
 * for one month. Recording it clears that month's commissions for withdrawal
 * (POST /admin/remittances); once per marketplace and month.
 */
export function RemittanceModal({ month, today, onClose }: { month: Month; today: string; onClose: () => void }) {
  const router = useRouter();
  const [amount, setAmount] = useState(Number(month.net).toFixed(2));
  const [received, setReceived] = useState(today);
  const [reference, setReference] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const valid = /^\d+(\.\d{1,2})?$/.test(amount.trim()) && /^\d{4}-\d{2}-\d{2}$/.test(received);
  const shortfall = valid ? Number(month.net) - Number(amount) : 0;

  async function record() {
    setBusy(true);
    setError(null);
    try {
      const res = await fetch("/api/bff/api/v1/admin/remittances", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          platform: month.platform,
          cycle_month: month.cycle_month,
          amount_received: amount.trim(),
          received_on: received,
          reference: reference.trim() || null,
        }),
      });
      if (!res.ok) return setError(await detail(res, "Couldn't record the remittance."));
      onClose();
      router.refresh();
    } catch {
      setError("Couldn't reach the server.");
    } finally {
      setBusy(false);
    }
  }

  const FIELD = "h-[52px] w-full rounded-[12px] border border-[var(--border-subtle)] bg-[var(--surface-card)] px-4 text-[16px]";
  return (
    <AdminModal title="Record remittance" width={560} onClose={onClose}>
      <div className="flex flex-col gap-4 overflow-y-auto px-6 pb-5 pt-4">
        <div>
          <Line label="Marketplace">{platformLabel(month.platform)}</Line>
          <Line label="Month">{monthLabel(month.cycle_month)}</Line>
          <Line label="Attributed">
            <Peso value={month.net} />
            <Note>{month.commissions.toLocaleString("en-PH")} commission{month.commissions === 1 ? "" : "s"}</Note>
          </Line>
        </div>
        <div className="grid grid-cols-2 gap-3">
          <label className="flex flex-col gap-2 text-[12px] text-[var(--text-secondary)]">
            Amount received
            <input inputMode="decimal" value={amount} onChange={(e) => setAmount(e.target.value)} className={FIELD} />
          </label>
          <label className="flex flex-col gap-2 text-[12px] text-[var(--text-secondary)]">
            Received on
            <input type="date" value={received} max={today} onChange={(e) => setReceived(e.target.value)} className={FIELD} />
          </label>
        </div>
        <label className="flex flex-col gap-2 text-[12px] text-[var(--text-secondary)]">
          Reference
          <input value={reference} maxLength={120} onChange={(e) => setReference(e.target.value)} placeholder="Optional, e.g. bank transfer ref" className={FIELD} />
        </label>
        <Line label="Shortfall">
          {shortfall > 0.004 ? (
            <>
              <WarningCircle size={14} weight="fill" className="self-center text-[var(--accent-danger)]" aria-hidden />
              <Peso value={shortfall} />
              <Note>received less than attributed</Note>
            </>
          ) : (
            <Note>{shortfall < -0.004 ? "received more than attributed" : "none"}</Note>
          )}
        </Line>
        {error ? (
          <p role="alert" className="text-[12px] text-[var(--accent-danger)]">
            {error}
          </p>
        ) : null}
      </div>
      <div className="flex items-center gap-3 border-t border-[var(--border-subtle)] px-6 py-4">
        <p className="flex-1 text-[12px] text-[var(--text-secondary)]">
          Clears {month.commissions.toLocaleString("en-PH")} commission{month.commissions === 1 ? "" : "s"} for withdrawal. Recorded once per month.
        </p>
        <button type="button" onClick={onClose} className="h-9 rounded-full border border-[var(--text-primary)] px-4 text-[12px]">
          Cancel
        </button>
        <button type="button" disabled={!valid || busy} onClick={() => void record()} className="h-9 rounded-full bg-[var(--accent-primary)] px-4 text-[12px] text-white disabled:opacity-50">
          {busy ? "Recording…" : "Record remittance"}
        </button>
      </div>
    </AdminModal>
  );
}
