"use client";

import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useRef, useState, type ReactNode } from "react";
import {
  ArrowsClockwise,
  ArrowsDownUp,
  ArrowUUpLeft,
  CalendarBlank,
  CheckCircle,
  FileText,
  MagnifyingGlass,
  Receipt,
  SlidersHorizontal,
  WarningCircle,
  XCircle,
} from "@phosphor-icons/react/dist/ssr";

import { ImportReportModal, Peso, RemittanceModal, FORMAT, monthLabel, platformLabel, previewReport } from "@/components/admin/affiliate/AffiliateModals";
import { IMPORT_SORTS, MONTH_FILTERS, MONTH_SORTS, applyImports, applyMonths } from "@/components/admin/list-models";
import { PersonCell } from "@/components/admin/queue/QueueCells";
import { ListControls } from "@/components/console/ListControls";
import { Pagination } from "@/components/console/Pagination";
import { PAGE_SIZES } from "@/components/console/pagination-model";

type Schemas = import("@/lib/api-types").components["schemas"];
type TxPage = Schemas["AffiliateTransactionPageOut"];
type Month = Schemas["AffiliateMonthOut"];
type Import = Schemas["AffiliateImportOut"];
type Preview = Schemas["LifecycleImportResult"];

export type AffiliateTab = "transactions" | "months" | "imports" | "links";
export type Ledger = {
  lifecycle: { label: string; count: number }[];
  settlement: { label: string; count: number }[];
  recognised_amount: string;
  reversed_amount: string;
  unrecovered_amount: string;
};

const STATUS: Record<string, { label: string; Icon: typeof CheckCircle; tone: string }> = {
  completed: { label: "Completed", Icon: CheckCircle, tone: "text-[var(--accent-success)]" },
  pending: { label: "Pending", Icon: ArrowsClockwise, tone: "text-[var(--chart-honesty-fund)]" },
  returned: { label: "Returned", Icon: ArrowUUpLeft, tone: "text-[var(--accent-danger)]" },
  cancelled: { label: "Cancelled", Icon: XCircle, tone: "text-[var(--text-secondary)]" },
};
const SETTLEMENT: Record<string, string> = { not_earned: "Not earned", earned: "Earned", paid: "Paid", reversed: "Reversed" };
const SORTS: [string, string][] = [
  ["newest", "Newest"],
  ["oldest", "Oldest"],
  ["commission_desc", "Commission: high to low"],
  ["commission_asc", "Commission: low to high"],
];
const FACETS: { key: string; title: string; options: [string, string][] }[] = [
  { key: "platform", title: "Marketplace", options: [["shopee", "Shopee"], ["lazada", "Lazada"]] },
  { key: "status", title: "Order status", options: Object.entries(STATUS).map(([k, v]) => [k, v.label]) },
  { key: "settlement", title: "Settlement", options: Object.entries(SETTLEMENT) },
  { key: "attribution", title: "Attribution", options: [["attributed", "Attributed"], ["unattributed", "Unattributed"]] },
  { key: "updated", title: "Updated", options: [["7d", "Last 7 days"], ["30d", "Last 30 days"], ["year", "This year"]] },
];
const n = (v: number) => v.toLocaleString("en-PH");
const day = (iso: string | null | undefined) =>
  iso ? new Date(iso).toLocaleDateString("en-GB", { day: "numeric", month: "short", timeZone: "Asia/Manila" }) : "—";

function Tile({ Icon }: { Icon: typeof FileText }) {
  return (
    <span className="grid size-[30px] shrink-0 place-items-center rounded-[8px] bg-[var(--surface-app)] text-[var(--text-secondary)]">
      <Icon size={16} aria-hidden />
    </span>
  );
}

function Bars({ title, bars }: { title: string; bars: { label: string; count: number }[] }) {
  const max = Math.max(1, ...bars.map((b) => b.count));
  return (
    <div className="flex flex-col gap-[6px]">
      <p className="text-[12px] text-[var(--text-secondary)]">{title}</p>
      {bars.map((b) => (
        <div key={b.label} className="grid grid-cols-[96px_1fr_48px] items-center gap-3 text-[14px]">
          <span>{b.label}</span>
          <span className="h-[5px] rounded-full bg-[var(--surface-app)]">
            <span className="block h-full rounded-full bg-[var(--text-primary)]" style={{ width: `${Math.round((b.count / max) * 100)}%` }} />
          </span>
          <span className="text-right [font-variant-numeric:tabular-nums]">{n(b.count)}</span>
        </div>
      ))}
    </div>
  );
}

/** The console Pagination (Figma component Pagination), driven through `go`. */
function Pager({ page, size, total, go, sized = true }: { page: number; size: number; total: number; go: (c: Record<string, string | null>) => void; sized?: boolean }) {
  return (
    <Pagination
      page={page}
      size={size}
      total={total}
      sizes={sized ? PAGE_SIZES : []}
      onChange={(next) => go({ page: next.page > 1 ? String(next.page) : null, size: sized && next.size !== PAGE_SIZES[0] ? String(next.size) : null })}
    />
  );
}

function Table({ caption, head, children }: { caption: string; head: string[]; children: ReactNode }) {
  return (
    <div className="overflow-x-auto rounded-[16px] border border-[var(--border-subtle)]">
      <table className="w-full min-w-[900px] border-collapse text-left text-[14px]">
        <caption className="sr-only">{caption}</caption>
        <thead className="bg-[var(--surface-app)] text-[12px] text-[var(--text-secondary)]">
          <tr>
            {head.map((h) => (
              <th key={h} scope="col" className="h-10 px-3 font-normal">
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>{children}</tbody>
      </table>
    </div>
  );
}

const Empty = ({ cols, children }: { cols: number; children: ReactNode }) => (
  <tr>
    <td colSpan={cols} className="border-t border-[var(--border-subtle)] px-3 py-10 text-center text-[var(--text-secondary)]">
      {children}
    </td>
  </tr>
);

const TD = "px-3 py-[10px]";

/**
 * Admin Affiliate (Figma Screen/Admin/Affiliate 8015:12542, Months 8015:13183,
 * Imports 8015:13726; proposed Sort / Filter / Search 8019:12729 / 12742 / 12873).
 * Transactions are the marketplace reports' orders with who each sale is
 * attributed to; Months reconcile what was attributed against what the
 * marketplace paid (Record opens the remittance); Imports are the report
 * history. "Needs link" (not in the frame) keeps the approved reviews still
 * waiting for an affiliate link, which only this screen attaches.
 */
export function AffiliateScreen({
  tab,
  ledger,
  tx,
  months,
  imports,
  needsLink,
  page,
  size,
  today,
  children,
}: {
  tab: AffiliateTab;
  ledger: Ledger | null;
  tx: TxPage | null;
  months: Month[] | null;
  imports: Import[] | null;
  needsLink: number | null;
  page: number;
  size: number;
  today: string;
  children?: ReactNode;
}) {
  const router = useRouter();
  const pathname = usePathname() ?? "/admin/affiliate-links";
  const params = useSearchParams();
  const fileInput = useRef<HTMLInputElement>(null);
  const [panel, setPanel] = useState<"sort" | "filter" | "search" | null>(params.get("q") ? "search" : null);
  const [q, setQ] = useState(params.get("q") ?? "");
  const [importing, setImporting] = useState<{ file: File; preview: Preview | null; error: string | null } | null>(null);
  const [recording, setRecording] = useState<Month | null>(null);

  function go(changes: Record<string, string | null>) {
    const next = new URLSearchParams(params.toString());
    for (const [k, v] of Object.entries(changes)) {
      if (v === null || v === "") next.delete(k);
      else next.set(k, v);
    }
    if (!("page" in changes)) next.delete("page");
    router.push(`${pathname}?${next.toString()}`, { scroll: false });
  }

  async function chooseFile(file: File | undefined) {
    if (!file) return;
    setImporting({ file, preview: null, error: null });
    const out = await previewReport(file);
    setImporting((cur) => (cur?.file === file ? { file, preview: out.preview ?? null, error: out.error ?? null } : cur));
  }

  const counts: Record<AffiliateTab, number | null> = {
    transactions: tx ? Object.values(tx.facets?.platform ?? {}).reduce((a, b) => a + b, 0) : null,
    months: months?.length ?? null,
    imports: imports?.length ?? null,
    links: needsLink,
  };
  const tabs: [AffiliateTab, string][] = [
    ["transactions", "Transactions"],
    ["months", "Months"],
    ["imports", "Imports"],
    ...(needsLink ? ([["links", "Needs link"]] as [AffiliateTab, string][]) : []),
  ];
  const sort = params.get("sort") ?? "newest";
  const filters = FACETS.filter((f) => params.get(f.key)).length;
  // Menu/Affiliate/Months/* and Menu/Affiliate/Imports/* + Search (8288:30079–30149).
  const listQuery = Object.fromEntries([...params.entries()].filter(([k, v]) => v && ["tab", "sort", "status", "q", "size"].includes(k)));
  const shownMonths = months ? applyMonths([...months], listQuery) : null;
  const shownImports = imports ? applyImports([...imports], listQuery) : null;

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center gap-2">
        <nav aria-label="Affiliate views" className="flex gap-[2px] rounded-[10px] bg-[var(--surface-app)] p-[3px]">
          {tabs.map(([t, label]) => (
            <Link
              key={t}
              href={t === "transactions" ? pathname : `${pathname}?tab=${t}`}
              aria-current={tab === t ? "page" : undefined}
              className={`flex items-center gap-[6px] rounded-[8px] px-3 py-[5px] leading-none ${tab === t ? "bg-[var(--surface-card)] shadow-[var(--shadow-segment)]" : "text-[var(--text-secondary)] hover:text-[var(--text-primary)]"}`}
            >
              <span className="text-[14px] font-medium">{label}</span>
              {counts[t] !== null ? <span className="text-[12px] text-[var(--text-secondary)]">{n(counts[t] ?? 0)}</span> : null}
            </Link>
          ))}
        </nav>
        <span className="flex-1" />
        {tab === "months" ? (
          <ListControls basePath={pathname} params={listQuery} sorts={MONTH_SORTS} defaultSort="newest" filters={MONTH_FILTERS} />
        ) : tab === "imports" ? (
          <ListControls basePath={pathname} params={listQuery} sorts={IMPORT_SORTS} defaultSort="newest" search={{ placeholder: "File name", label: "Search imports" }} />
        ) : null}
        {tab === "transactions"
          ? ([
              ["sort", ArrowsDownUp, "Sort"],
              ["filter", SlidersHorizontal, filters ? `Filter (${filters} on)` : "Filter"],
              ["search", MagnifyingGlass, "Search transactions"],
            ] as const).map(([key, Icon, label]) => (
              <button
                key={key}
                type="button"
                aria-label={label}
                aria-expanded={panel === key}
                onClick={() => setPanel((p) => (p === key ? null : key))}
                className={`relative grid size-8 place-items-center rounded-full ${panel === key ? "bg-[var(--surface-app)]" : "hover:bg-[var(--surface-app)]"}`}
              >
                <Icon size={18} />
                {key === "filter" && filters ? <span className="absolute right-1 top-1 size-[6px] rounded-full bg-[var(--accent-primary)]" aria-hidden /> : null}
              </button>
            ))
          : null}
        <button type="button" onClick={() => fileInput.current?.click()} className="h-8 rounded-full border border-[var(--text-primary)] px-3 text-[12px]">
          Import report
        </button>
        <input
          ref={fileInput}
          type="file"
          accept=".csv,text/csv"
          aria-label="Marketplace report (CSV)"
          className="sr-only"
          tabIndex={-1}
          onChange={(e) => {
            void chooseFile(e.target.files?.[0]);
            e.target.value = "";
          }}
        />
      </div>

      {tab === "transactions" && panel === "sort" ? (
        <div className="flex flex-wrap gap-2" role="group" aria-label="Sort">
          {SORTS.map(([k, label]) => (
            <button key={k} type="button" aria-pressed={sort === k} onClick={() => go({ sort: k === "newest" ? null : k })} className={`h-8 rounded-full border px-3 text-[12px] ${sort === k ? "border-[var(--accent-primary)] text-[var(--accent-primary)]" : "border-[var(--border-subtle)]"}`}>
              {label}
            </button>
          ))}
        </div>
      ) : tab === "transactions" && panel === "filter" ? (
        <div className="flex flex-col gap-3 rounded-[16px] border border-[var(--border-subtle)] p-4" role="group" aria-label="Filter">
          {FACETS.map((f) => (
            <div key={f.key} className="flex flex-col gap-2">
              <p className="text-[12px] text-[var(--chart-honesty-fund)]">{f.title}</p>
              <div className="flex flex-wrap gap-2">
                {f.options.map(([value, label]) => {
                  const on = params.get(f.key) === value;
                  const count = tx?.facets?.[f.key]?.[value] ?? 0;
                  return (
                    <button key={value} type="button" aria-pressed={on} onClick={() => go({ [f.key]: on ? null : value })} className={`flex h-8 items-center gap-[6px] rounded-full border px-3 text-[14px] ${on ? "border-[var(--accent-primary)] text-[var(--accent-primary)]" : "border-[var(--border-subtle)]"}`}>
                      {label}
                      <span className="text-[12px] text-[var(--text-secondary)]">{n(count)}</span>
                    </button>
                  );
                })}
              </div>
            </div>
          ))}
          <button type="button" onClick={() => go(Object.fromEntries(FACETS.map((f) => [f.key, null])))} className="self-start text-[14px] text-[var(--chart-honesty-fund)]">
            Clear all
          </button>
        </div>
      ) : tab === "transactions" && panel === "search" ? (
        <form
          role="search"
          onSubmit={(e) => {
            e.preventDefault();
            go({ q: q.trim() || null });
          }}
          className="flex items-center gap-2"
        >
          <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Order ID, product or seller" aria-label="Search transactions" className="h-8 w-72 rounded-full border border-[var(--border-subtle)] px-3 text-[12px]" />
          <button type="submit" className="h-8 rounded-full border border-[var(--text-primary)] px-3 text-[12px]">
            Search
          </button>
        </form>
      ) : null}

      {tab === "transactions" ? (
        <>
          {ledger ? (
            <section aria-label="Ledger" className="grid gap-6 rounded-[16px] border border-[var(--border-subtle)] p-4 md:grid-cols-3">
              <div className="flex flex-col gap-[6px]">
                <p className="text-[12px] text-[var(--text-secondary)]">Ledger</p>
                {(
                  [
                    ["Recognised", ledger.recognised_amount, "Commission the reports credited."],
                    ["Reversed", ledger.reversed_amount, "Returns taken back."],
                    ["Absorbed", ledger.unrecovered_amount, "Returned after payout: Bluntly bears it, no reviewer is put into debt."],
                  ] as const
                ).map(([label, value, hint]) => (
                  <div key={label} title={hint} className="flex items-center justify-between text-[14px]">
                    <span>{label}</span>
                    <Peso value={value} />
                  </div>
                ))}
              </div>
              <Bars title="Order status" bars={ledger.lifecycle} />
              <Bars title="Settlement" bars={ledger.settlement} />
            </section>
          ) : null}
          <Table caption="Affiliate transactions" head={["Order", "Reviewer", "Order status", "Settlement", "Commission", "Updated"]}>
            {tx === null ? (
              <Empty cols={6}>Transactions could not be loaded.</Empty>
            ) : tx.rows.length === 0 ? (
              <Empty cols={6}>{["q", "platform", "status", "settlement", "attribution", "updated"].some((k) => params.get(k)) ? "No transaction matches." : "No marketplace report has been imported yet. Import report adds its orders here."}</Empty>
            ) : (
              tx.rows.map((r) => {
                const st = STATUS[r.status] ?? STATUS.pending;
                const name = r.reviewer ? (r.reviewer.display_name ?? r.reviewer.username ?? "Member") : null;
                const reversed = r.settlement === "reversed";
                return (
                  <tr key={r.id} data-testid="transaction-row" className="border-t border-[var(--border-subtle)] hover:bg-[var(--surface-app)]">
                    <td className={TD}>
                      <span className="flex items-center gap-[10px]">
                        <Tile Icon={Receipt} />
                        <span className="flex min-w-0 flex-col gap-1 leading-4 [&>:first-child]:leading-5">
                          <span className="max-w-[260px] truncate">{r.product_name ?? r.review_title ?? "Unnamed order"}</span>
                          <span className="max-w-[260px] truncate text-[12px] text-[var(--text-secondary)]">
                            Order {r.order_ref ?? "—"} · {platformLabel(r.platform)}
                          </span>
                        </span>
                      </span>
                    </td>
                    <td className={TD}>
                      {r.reviewer && name ? (
                        <PersonCell name={name} stage={r.reviewer.trust_stage} levelName={r.reviewer.trust_level_name} href={`/admin/people/${r.reviewer.id}`} />
                      ) : (
                        <span className="text-[var(--text-secondary)]">Unattributed</span>
                      )}
                    </td>
                    <td className={TD}>
                      <span className="flex items-center gap-2">
                        <st.Icon size={16} weight={r.status === "completed" ? "fill" : "regular"} className={st.tone} aria-hidden />
                        {st.label}
                      </span>
                    </td>
                    <td className={TD}>{SETTLEMENT[r.settlement] ?? r.settlement}</td>
                    <td className={TD}>
                      <Peso value={r.commission === null || r.commission === undefined ? null : reversed ? -Number(r.commission) : r.commission} signed />
                    </td>
                    <td className={`${TD} text-[var(--text-secondary)]`} suppressHydrationWarning>
                      {day(r.updated_at ?? r.recorded_at)}
                    </td>
                  </tr>
                );
              })
            )}
          </Table>
          <Pager page={page} size={size} total={tx?.total ?? 0} go={go} />
        </>
      ) : tab === "months" ? (
        <>
          <Table caption="Commission per marketplace month" head={["Month", "Attributed", "Received", "Shortfall", "Commissions", "Status", "Action"]}>
            {shownMonths === null ? (
              <Empty cols={7}>Months could not be loaded.</Empty>
            ) : shownMonths.length === 0 ? (
              <Empty cols={7}>{months?.length ? "No month matches this filter." : "No commission has been imported yet."}</Empty>
            ) : (
              shownMonths.slice((page - 1) * size, page * size).map((m) => {
                const short = m.remitted !== null && m.remitted !== undefined ? Number(m.net) - Number(m.remitted) : 0;
                const cleared = m.status === "remitted";
                return (
                  <tr key={`${m.platform}-${m.cycle_month}`} data-testid="month-row" className="group border-t border-[var(--border-subtle)] hover:bg-[var(--surface-app)]">
                    <td className={TD}>
                      <span className="flex items-center gap-[10px]">
                        <Tile Icon={CalendarBlank} />
                        <span className="flex flex-col gap-1 leading-4 [&>:first-child]:leading-5">
                          <span>{monthLabel(m.cycle_month)}</span>
                          <span className="text-[12px] text-[var(--text-secondary)]">{platformLabel(m.platform)}</span>
                        </span>
                      </span>
                    </td>
                    <td className={TD}>
                      <Peso value={m.net} signed />
                    </td>
                    <td className={TD}>
                      <Peso value={m.remitted} />
                    </td>
                    <td className={TD}>
                      {short > 0.004 ? (
                        <span className="flex items-center gap-2">
                          <WarningCircle size={14} weight="fill" className="text-[var(--accent-danger)]" aria-hidden />
                          <Peso value={short} />
                        </span>
                      ) : (
                        <span className="text-[var(--text-secondary)]">—</span>
                      )}
                    </td>
                    <td className={TD}>{n(m.commissions)}</td>
                    <td className={TD}>
                      <span className="flex items-center gap-2">
                        {cleared ? (
                          <CheckCircle size={16} weight="fill" className="text-[var(--accent-success)]" aria-hidden />
                        ) : (
                          <ArrowsClockwise size={16} className="text-[var(--chart-honesty-fund)]" aria-hidden />
                        )}
                        {cleared ? "Cleared" : "Clearing"}
                      </span>
                    </td>
                    <td className={TD}>
                      {cleared ? null : (
                        <button type="button" onClick={() => setRecording(m)} className="h-7 rounded-full border border-[var(--border-subtle)] bg-[var(--surface-card)] px-3 text-[12px] opacity-0 focus:opacity-100 group-hover:opacity-100 max-md:opacity-100">
                          Record
                        </button>
                      )}
                    </td>
                  </tr>
                );
              })
            )}
          </Table>
          <Pager page={page} size={size} total={shownMonths?.length ?? 0} go={go} />
        </>
      ) : tab === "imports" ? (
        <>
          <Table caption="Report imports" head={["File", "Recognised", "Reversed", "Unattributed", "Date"]}>
            {shownImports === null ? (
              <Empty cols={5}>Imports could not be loaded.</Empty>
            ) : shownImports.length === 0 ? (
              <Empty cols={5}>{imports?.length ? "No import matches this search." : "No report has been imported yet."}</Empty>
            ) : (
              shownImports.slice((page - 1) * size, page * size).map((i) => (
                <tr key={i.id} data-testid="import-row" className="border-t border-[var(--border-subtle)] hover:bg-[var(--surface-app)]">
                  <td className={TD}>
                    <span className="flex items-center gap-[10px]">
                      <Tile Icon={FileText} />
                      <span className="flex min-w-0 flex-col gap-1 leading-4 [&>:first-child]:leading-5">
                        <span className="max-w-[320px] truncate">{i.filename ?? "Unnamed file"}</span>
                        <span className="text-[12px] text-[var(--text-secondary)]">
                          {FORMAT[i.format ?? ""]?.platform ?? (i.kind === "commission" ? "Commission CSV" : "Report")} · {n(i.total_rows)} rows
                        </span>
                      </span>
                    </span>
                  </td>
                  <td className={TD}>
                    <Peso value={i.recognised_amount} />
                  </td>
                  <td className={TD}>
                    <Peso value={i.reversed_amount} />
                  </td>
                  <td className={TD}>{i.unattributed ? n(i.unattributed) : <span className="text-[var(--text-secondary)]">—</span>}</td>
                  <td className={`${TD} text-[var(--text-secondary)]`} suppressHydrationWarning>
                    {day(i.imported_at)}
                  </td>
                </tr>
              ))
            )}
          </Table>
          <Pager page={page} size={size} total={shownImports?.length ?? 0} go={go} />
        </>
      ) : (
        children
      )}

      {importing ? (
        <ImportReportModal file={importing.file} preview={importing.preview} previewError={importing.error} onClose={() => setImporting(null)} />
      ) : null}
      {recording ? <RemittanceModal month={recording} today={today} onClose={() => setRecording(null)} /> : null}
    </div>
  );
}
