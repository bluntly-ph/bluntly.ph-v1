"use client";

import { useRouter } from "next/navigation";
import { useRef, useState } from "react";
import { DownloadSimple, FileText, UploadSimple } from "@phosphor-icons/react/dist/ssr";

import { AdminModal } from "@/components/admin/AdminModal";
import { Chip } from "@/components/console/Chip";
import {
  OUTCOME,
  type ImportResult,
  attachLines,
  canAttach,
  importLabel,
  rowNote,
  summaryChips,
} from "@/components/admin/products/product-import-model";

/**
 * Import products (owner request, 2026-10-03; no frame — built in the console's
 * import language, Overlay/Affiliate/Import 8017:12742): choose a CSV, read
 * what it would do (POST /admin/products/import, nothing written), decide the
 * matches, then import.
 *
 * Every row shows its outcome: New, Matches a product (by its listing link or
 * its name — never added twice; Attach adds the row's listing and names to that
 * product, Skip leaves it), Repeated in file, Conflict (listing and name point
 * at different products — never written) or an error with its reason. Importing
 * writes everything or nothing and says what happened. The file format:
 * docs/PRODUCT_CSV_IMPORT.md; the template comes from the API, generated from
 * the same columns the server reads.
 */

const TEMPLATE_URL = "/api/bff/api/v1/admin/products/import/template";

async function detail(res: Response, fallback: string): Promise<string> {
  const p = (await res.json().catch(() => ({}))) as { detail?: unknown };
  return typeof p.detail === "string" ? p.detail : fallback;
}

export function ProductImportModal({ onClose }: { onClose: () => void }) {
  const router = useRouter();
  const input = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [result, setResult] = useState<ImportResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [attach, setAttach] = useState<Set<number>>(new Set());

  async function send(chosen: File, apply: boolean) {
    setBusy(true);
    setError(null);
    try {
      const body = new FormData();
      body.append("file", chosen, chosen.name);
      body.append("apply", apply ? "true" : "false");
      if (apply && result) body.append("attach", attachLines(result.rows, attach).join(","));
      const res = await fetch("/api/bff/api/v1/admin/products/import", { method: "POST", body });
      if (!res.ok) {
        setResult(null);
        setError(await detail(res, "That file couldn't be read."));
        return;
      }
      const next = (await res.json()) as ImportResult;
      setResult(next);
      if (next.failure) setError(next.failure);
      if (next.applied) router.refresh();
    } catch {
      setError("Couldn't reach the server.");
    } finally {
      setBusy(false);
    }
  }

  function choose(e: React.ChangeEvent<HTMLInputElement>) {
    const f = e.target.files?.[0];
    e.target.value = "";
    if (!f) return;
    setFile(f);
    setResult(null);
    setAttach(new Set());
    void send(f, false);
  }

  function toggle(line: number, on: boolean) {
    setAttach((prev) => {
      const next = new Set(prev);
      if (on) next.add(line);
      else next.delete(line);
      return next;
    });
  }

  const applied = result?.applied ?? false;
  const newCount = result?.counts.new ?? 0;
  const attachable = result ? result.rows.filter(canAttach) : [];
  const attachCount = result ? attachLines(result.rows, attach).length : 0;

  return (
    <AdminModal title="Import products" width={760} onClose={onClose}>
      <div className="flex min-h-0 flex-col gap-4 overflow-y-auto px-6 pb-5 pt-4">
        <div className="flex items-center gap-3 rounded-[16px] border border-[var(--border-subtle)] p-2 pr-4">
          <span className="grid size-[50px] shrink-0 place-items-center rounded-[10px] bg-[var(--surface-app)]">
            <FileText size={20} aria-hidden />
          </span>
          <span className="flex min-w-0 flex-1 flex-col gap-1 leading-none">
            <span className="truncate text-[16px]">{file ? file.name : "No file chosen"}</span>
            <span className="text-[12px] text-[var(--text-secondary)]" data-testid="import-status">
              {busy
                ? applied || !result
                  ? "Reading…"
                  : "Importing…"
                : result
                  ? `${result.rows.length.toLocaleString("en-PH")} products in the file`
                  : "A CSV with brand, line and category columns (UTF-8)"}
            </span>
          </span>
          <button
            type="button"
            onClick={() => input.current?.click()}
            disabled={busy}
            className="flex h-9 shrink-0 items-center gap-1.5 rounded-full border border-[var(--text-primary)] px-4 text-[12px] disabled:opacity-50"
          >
            <UploadSimple size={14} aria-hidden /> {file ? "Choose another" : "Choose file"}
          </button>
          <input ref={input} type="file" accept=".csv,text/csv" aria-label="Product CSV file" className="hidden" onChange={choose} />
        </div>

        {!result && !error ? (
          <div className="flex flex-col gap-2 text-[12px] leading-5 text-[var(--text-secondary)]">
            <p>
              Columns: <strong className="font-medium text-[var(--text-primary)]">brand, line, category</strong> (required), variant,
              type, aliases (separate with “|”), source_url (the marketplace listing), specs (“Label: Value | Label: Value”).
              Headers in any order or case; other columns are ignored. Up to 500 products. Photos are added afterwards with Edit.
            </p>
            <a href={TEMPLATE_URL} download="bluntly-products-template.csv" className="flex w-fit items-center gap-1 text-[var(--chart-honesty-fund)]">
              <DownloadSimple size={14} aria-hidden /> Download the template
            </a>
          </div>
        ) : null}

        {result ? (
          <>
            <div className="flex flex-wrap items-center gap-2" data-testid="import-counts">
              {summaryChips(result).map((c) => (
                <Chip key={c.label} tone={c.tone}>
                  {c.label}
                </Chip>
              ))}
              {!applied && attachable.length ? (
                <button
                  type="button"
                  className="ml-auto text-[12px] text-[var(--chart-honesty-fund)]"
                  onClick={() => setAttach(attachCount === attachable.length ? new Set() : new Set(attachable.map((r) => r.line)))}
                >
                  {attachCount === attachable.length ? "Skip every match" : `Attach every match (${attachable.length})`}
                </button>
              ) : null}
            </div>
            {result.ignored_columns.length ? (
              <p className="text-[12px] text-[var(--text-secondary)]" data-testid="import-ignored">
                Not read (not a product column): {result.ignored_columns.join(", ")}.
              </p>
            ) : null}
            <div className="max-h-[340px] overflow-auto rounded-[16px] border border-[var(--border-subtle)]">
              <table className="w-full border-collapse text-left text-[14px]">
                <caption className="sr-only">Products in the file</caption>
                <thead className="sticky top-0 bg-[var(--surface-app)] text-[12px] text-[var(--text-secondary)]">
                  <tr>
                    {["Row", "Product", "Outcome", "Decision"].map((h) => (
                      <th key={h} scope="col" className="h-10 px-3 font-normal">
                        {h}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {result.rows.map((r) => {
                    const note = rowNote(r);
                    const bad = r.outcome === "error" || r.outcome === "conflict" || r.outcome === "failed";
                    return (
                      <tr key={r.line} className="border-t border-[var(--border-subtle)] align-top" data-testid="import-row">
                        <td className="px-3 py-[10px] text-[var(--text-secondary)] [font-variant-numeric:tabular-nums]">{r.line}</td>
                        <td className="px-3 py-[10px]">
                          <span className="flex flex-col gap-1">
                            <span>{r.name ?? "—"}</span>
                            {note ? (
                              <span className={`text-[12px] ${bad ? "text-[var(--status-critical-fg)]" : "text-[var(--text-secondary)]"}`}>{note}</span>
                            ) : null}
                            {canAttach(r) && !applied ? (
                              <span className="text-[12px] text-[var(--text-secondary)]">Attach adds: {r.attach_adds.join(", ")}</span>
                            ) : null}
                          </span>
                        </td>
                        <td className="px-3 py-[10px]">
                          <Chip tone={OUTCOME[r.outcome].tone}>{OUTCOME[r.outcome].label}</Chip>
                        </td>
                        <td className="px-3 py-[10px] text-[12px]">
                          {canAttach(r) && !applied ? (
                            <label className="flex items-center gap-2">
                              <input
                                type="checkbox"
                                checked={attach.has(r.line)}
                                onChange={(e) => toggle(r.line, e.target.checked)}
                                aria-label={`Attach row ${r.line} to ${r.existing_name ?? "the matching product"}`}
                                className="size-4 accent-[var(--accent-primary)]"
                              />
                              {attach.has(r.line) ? "Attach" : "Skip"}
                            </label>
                          ) : r.outcome === "new" ? (
                            "Add"
                          ) : r.outcome === "created" || r.outcome === "attached" ? (
                            "Done"
                          ) : (
                            <span className="text-[var(--text-secondary)]">Skip</span>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
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
        <p className="flex-1 text-[12px] text-[var(--text-secondary)]">
          {applied
            ? "Done. Open a new product with Edit to add its photo. This import is in the Activity log."
            : "Nothing changes until you import, and then everything or nothing. A product already in the catalogue is never added twice."}
        </p>
        <button type="button" onClick={onClose} className="h-9 rounded-full border border-[var(--text-primary)] px-4 text-[12px]">
          {applied ? "Done" : "Cancel"}
        </button>
        {!applied ? (
          <button
            type="button"
            disabled={!file || !result || (newCount === 0 && attachCount === 0) || busy}
            onClick={() => file && void send(file, true)}
            className="h-9 rounded-full bg-[var(--accent-primary)] px-4 text-[12px] text-white disabled:opacity-50"
          >
            {busy && result ? "Importing…" : importLabel(newCount, attachCount)}
          </button>
        ) : null}
      </div>
    </AdminModal>
  );
}
