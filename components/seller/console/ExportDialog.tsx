"use client";

import { useEffect, useState } from "react";
import { CaretDown, Check } from "@phosphor-icons/react/dist/ssr";

import { AdminModal } from "@/components/admin/AdminModal";
import { MENU, usePopover } from "@/components/console/popover";
import { Callout } from "@/components/console/Callout";

import { EXPORT_FILES, INSIGHT_PERIODS, exportHref, exportSummary, periodLabel, type ExportKey } from "./insights-model";
import { MENU_ITEM } from "@/components/console/fields";

/**
 * Overlay/Store/Export (Figma 8213:23286): the store's own data as CSV files in
 * one zip. The counts come from the API for the chosen period; the download is
 * the owner-only export endpoint through the BFF, so the token never reaches
 * the browser. Buyer names are shortened and no contact details or order IDs
 * are in any file (the API's promise, written on the overlay).
 */
export function ExportButton({ storeId, period }: { storeId: string; period: string }) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="h-9 rounded-full border border-[var(--text-primary)] px-4 text-[12px] hover:bg-[var(--surface-app)]"
      >
        Download CSV
      </button>
      {open ? <ExportDialog storeId={storeId} initialPeriod={period} onClose={() => setOpen(false)} /> : null}
    </>
  );
}

type Sizes = Record<ExportKey, number>;

function useSizes(storeId: string, period: string) {
  const [state, setState] = useState<{ period: string; sizes: Sizes | null; failed: boolean } | null>(null);
  useEffect(() => {
    let cancelled = false;
    fetch(`/api/bff/api/v1/sellers/${encodeURIComponent(storeId)}/export/sizes?period=${encodeURIComponent(period)}`, { cache: "no-store" })
      .then((r) => (r.ok ? (r.json() as Promise<Sizes>) : Promise.reject(new Error("sizes"))))
      .then((sizes) => !cancelled && setState({ period, sizes, failed: false }))
      .catch(() => !cancelled && setState({ period, sizes: null, failed: true }));
    return () => {
      cancelled = true;
    };
  }, [storeId, period]);
  return state?.period === period ? state : null;
}

export function ExportDialog({ storeId, initialPeriod, onClose }: { storeId: string; initialPeriod: string; onClose: () => void }) {
  const [chosen, setChosen] = useState<ExportKey[]>(["reviews", "products"]);
  const [period, setPeriod] = useState(initialPeriod);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const loaded = useSizes(storeId, period);
  const sizes = loaded?.sizes ?? null;
  const { open: menuOpen, setOpen: setMenuOpen, ref: menuRef } = usePopover();

  function toggle(key: ExportKey) {
    setChosen((c) => (c.includes(key) ? c.filter((k) => k !== key) : [...c, key]));
  }

  async function download() {
    setBusy(true);
    setError(null);
    try {
      const res = await fetch(exportHref(storeId, chosen, period), { cache: "no-store" });
      if (!res.ok) {
        const p = (await res.json().catch(() => ({}))) as { detail?: unknown };
        setError(typeof p.detail === "string" ? p.detail : "The file couldn’t be made. Try again.");
        return;
      }
      const name = /filename="([^"]+)"/.exec(res.headers.get("content-disposition") ?? "")?.[1] ?? "bluntly-store.zip";
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
    <AdminModal title="Download CSV" width={560} onClose={onClose}>
      <div className="flex flex-col gap-3 px-6 pb-5 pt-4">
        <p className={LABEL} id="export-what">
          What to include
        </p>
        <div role="group" aria-labelledby="export-what" className="flex flex-col gap-3">
          {EXPORT_FILES.map((f) => {
            const on = chosen.includes(f.key);
            const n = sizes?.[f.key];
            const count = n == null ? "…" : f.unit === "products" ? `${n} product${n === 1 ? "" : "s"}` : `${n} row${n === 1 ? "" : "s"}`;
            return (
              <label
                key={f.key}
                className={`flex cursor-pointer items-center gap-3 rounded-[12px] border px-4 py-3 ${on ? "border-[var(--accent-primary)]" : "border-[var(--border-subtle)]"}`}
              >
                <input type="checkbox" checked={on} onChange={() => toggle(f.key)} className="size-[18px] shrink-0 accent-[var(--accent-primary)]" />
                <span className="flex flex-col gap-1 leading-none">
                  <span className="text-[14px] font-medium">{f.label}</span>
                  <span className="text-[12px] text-[var(--text-secondary)]">
                    {loaded?.failed ? f.what : `${count} · ${f.what}`}
                  </span>
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
            {periodLabel(period)} <CaretDown size={12} aria-hidden />
          </button>
          {menuOpen ? (
            <ul role="menu" aria-label="Period" className={`${MENU} left-0 right-auto w-[220px] p-2`}>
              {INSIGHT_PERIODS.map((p) => (
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
          Buyer names are shortened. No contact details or order IDs are included.
        </Callout>
        <p className="text-[12px] text-[var(--text-secondary)]">Product analytics are each product’s current figures; the period applies to the other files.</p>
        {error ? (
          <p role="alert" className="text-[12px] text-[var(--accent-danger)]">
            {error}
          </p>
        ) : null}
      </div>
      <div className="flex items-center gap-3 border-t border-[var(--border-subtle)] px-6 py-4">
        <span className="flex-1 text-[12px] text-[var(--text-secondary)]" aria-live="polite">
          {exportSummary(chosen, sizes)}
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
          {busy ? "Preparing…" : "Download CSV"}
        </button>
      </div>
    </AdminModal>
  );
}
