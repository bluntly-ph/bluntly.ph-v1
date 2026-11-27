"use client";

import { useState } from "react";
import { CaretDown, Check } from "@phosphor-icons/react/dist/ssr";

import { AdminModal } from "@/components/admin/AdminModal";
import { MENU, usePopover } from "@/components/console/popover";
import { Callout } from "@/components/console/Callout";

import {
  ADMIN_EXPORT_PERIODS,
  ADMIN_EXPORT_SECTIONS,
  adminExportFiles,
  adminExportHref,
  exportPeriodLabel,
  type AdminExportKey,
} from "./admin-export-model";
import { MENU_ITEM } from "@/components/console/fields";

/**
 * Overlay/Admin/Export (Figma 8237:25470): the console's data as CSV files in
 * one zip, for one of the Analytics page's periods. Names are shortened and
 * email addresses removed by the API, and each export is recorded in the
 * Activity log. Opened from the Activity log and from Analytics, each with its
 * own parts ticked to start.
 */
export function AdminExportButton({ initial, period = "30d" }: { initial: AdminExportKey[]; period?: string }) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button type="button" onClick={() => setOpen(true)} className="flex h-8 items-center rounded-full border border-[var(--text-primary)] px-3 text-[12px] hover:bg-[var(--surface-app)]">
        Export CSV
      </button>
      {open ? <AdminExportDialog initial={initial} initialPeriod={period} onClose={() => setOpen(false)} /> : null}
    </>
  );
}

function AdminExportDialog({ initial, initialPeriod, onClose }: { initial: AdminExportKey[]; initialPeriod: string; onClose: () => void }) {
  const [chosen, setChosen] = useState<AdminExportKey[]>(initial);
  const [period, setPeriod] = useState(ADMIN_EXPORT_PERIODS.some((p) => p.key === initialPeriod) ? initialPeriod : "30d");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const { open: menuOpen, setOpen: setMenuOpen, ref: menuRef } = usePopover();

  async function download() {
    setBusy(true);
    setError(null);
    try {
      const res = await fetch(adminExportHref(chosen, period), { cache: "no-store" });
      if (!res.ok) {
        const p = (await res.json().catch(() => ({}))) as { detail?: unknown };
        setError(typeof p.detail === "string" ? p.detail : "The export couldn’t be made. Try again.");
        return;
      }
      const name = /filename="([^"]+)"/.exec(res.headers.get("content-disposition") ?? "")?.[1] ?? "bluntly-admin-export.zip";
      const url = URL.createObjectURL(await res.blob());
      const a = document.createElement("a");
      a.href = url;
      a.download = name;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
      onClose();
    } catch {
      setError("Couldn’t reach the server.");
    } finally {
      setBusy(false);
    }
  }

  const LABEL = "text-[11px] font-medium uppercase tracking-[0.06em] text-[var(--text-secondary)]";
  return (
    <AdminModal title="Export CSV" width={560} onClose={onClose}>
      <div className="flex flex-col gap-3 px-6 pb-5 pt-4">
        <p className={LABEL} id="admin-export-what">
          What to include
        </p>
        <div role="group" aria-labelledby="admin-export-what" className="flex flex-col gap-3">
          {ADMIN_EXPORT_SECTIONS.map((s) => {
            const on = chosen.includes(s.key);
            return (
              <label key={s.key} className={`flex cursor-pointer items-center gap-3 rounded-[12px] border px-4 py-3 ${on ? "border-[var(--accent-primary)]" : "border-[var(--border-subtle)]"}`}>
                <input
                  type="checkbox"
                  checked={on}
                  onChange={() => setChosen((c) => (c.includes(s.key) ? c.filter((k) => k !== s.key) : [...c, s.key]))}
                  className="size-[18px] shrink-0 accent-[var(--accent-primary)]"
                />
                <span className="flex flex-col gap-1 leading-none">
                  <span className="text-[14px] font-medium">{s.label}</span>
                  <span className="text-[12px] text-[var(--text-secondary)]">{s.what}</span>
                </span>
              </label>
            );
          })}
        </div>
        <p className={`${LABEL} mt-1`}>Period</p>
        <div ref={menuRef} className="relative self-start">
          <button
            type="button"
            aria-haspopup="menu"
            aria-expanded={menuOpen}
            onClick={() => setMenuOpen(!menuOpen)}
            className="flex h-9 items-center gap-2 rounded-full border border-[var(--border-subtle)] px-4 text-[12px]"
          >
            {exportPeriodLabel(period)} <CaretDown size={12} aria-hidden />
          </button>
          {menuOpen ? (
            <ul role="menu" aria-label="Period" className={`${MENU} left-0 right-auto w-[220px] p-2`}>
              {ADMIN_EXPORT_PERIODS.map((p) => (
                <li key={p.key} role="none">
                  <button
                    type="button"
                    role="menuitemradio"
                    aria-checked={p.key === period}
                    onClick={() => {
                      setPeriod(p.key);
                      setMenuOpen(false);
                    }}
                    className={MENU_ITEM}
                  >
                    {p.label}
                    {p.key === period ? <Check size={16} aria-hidden /> : null}
                  </button>
                </li>
              ))}
            </ul>
          ) : null}
        </div>
        <Callout className="mt-1">
          Names are shortened and emails removed. Exports are recorded in the Activity log.
        </Callout>
        {error ? (
          <p role="alert" className="text-[12px] text-[var(--accent-danger)]">
            {error}
          </p>
        ) : null}
      </div>
      <div className="flex items-center gap-3 border-t border-[var(--border-subtle)] px-6 py-4">
        <span className="flex-1 text-[12px] text-[var(--text-secondary)]" aria-live="polite">
          {adminExportFiles(chosen)}
        </span>
        <button type="button" onClick={onClose} className="h-9 rounded-full border border-[var(--text-primary)] px-4 text-[12px]">
          Cancel
        </button>
        <button
          type="button"
          disabled={chosen.length === 0 || busy}
          onClick={() => void download()}
          className="h-9 rounded-full bg-[var(--accent-primary)] px-4 text-[12px] text-white disabled:opacity-50"
        >
          {busy ? "Preparing…" : "Export CSV"}
        </button>
      </div>
    </AdminModal>
  );
}
