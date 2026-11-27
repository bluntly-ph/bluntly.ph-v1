"use client";

import Link from "next/link";
import { useState } from "react";
import { CheckCircle, Circle, Clock } from "@phosphor-icons/react/dist/ssr";

import { AdminModal } from "@/components/admin/AdminModal";
import { PersonCell } from "@/components/admin/queue/QueueCells";
import { Chip } from "@/components/console/Chip";
import { ListControls } from "@/components/console/ListControls";
import { Pagination } from "@/components/console/Pagination";
import { StarRow } from "@/components/sellers/SellerIdentity";

import {
  APPEAL_DEFAULT_SORT,
  APPEAL_SORTS,
  APPEAL_TABS,
  STATUS,
  appealFilters,
  appealSummary,
  applyAppeals,
  inAppealTab,
  isOpen,
  reviewerOf,
  type AppealTab,
  type StoreAppeal,
} from "./appeals-model";
import { agoShort } from "./overview-model";

/**
 * Screen/Seller/Appeals (Figma 8196:21910, In progress 8201:23146, Decided
 * 8201:23417) and Overlay/Store/Appeal (8197:21606): the flags this store
 * raised, from GET /sellers/{id}/appeals (owner only; the reviewer's proof is
 * never sent to the store). Read-only: an administrator decides.
 */
export function SellerAppeals({
  storeId,
  appeals,
  now,
  initialTab,
  query = {},
}: {
  storeId: string;
  appeals: StoreAppeal[];
  now: number;
  initialTab?: AppealTab;
  /** Sort / Filter / Search from the URL (Figma Menu/Seller/Appeals/*). */
  query?: Record<string, string>;
}) {
  const [tab, setTab] = useState<AppealTab>(initialTab ?? "progress");
  const [page, setPage] = useState({ page: 1, size: 10 });
  const [open, setOpen] = useState<StoreAppeal | null>(null);
  const counts = { progress: 0, decided: 0, all: appeals.length };
  for (const a of appeals) counts[isOpen(a) ? "progress" : "decided"] += 1;
  const inTab = appeals.filter((a) => inAppealTab(a, tab));
  const shown = applyAppeals(inTab, query);
  const filtering = Boolean(query.status || query.rating || query.q);
  const rows = shown.slice((page.page - 1) * page.size, page.page * page.size);
  const s = appealSummary(appeals);

  return (
    <div className="flex flex-col gap-4">
      <h1 className="text-[24px] font-semibold leading-none">Appeals</h1>
      <div className="flex flex-wrap items-center gap-2">
      <nav aria-label="Appeal views" className="flex w-fit flex-wrap gap-[2px] rounded-[10px] bg-[var(--surface-app)] p-[3px]">
        {APPEAL_TABS.map((t) => (
          <button
            key={t.key}
            type="button"
            aria-current={tab === t.key ? "page" : undefined}
            onClick={() => {
              setTab(t.key);
              setPage((p) => ({ ...p, page: 1 }));
            }}
            className={`flex items-center gap-[6px] rounded-[8px] px-3 py-[5px] leading-none ${
              tab === t.key ? "bg-[var(--surface-card)] shadow-[var(--shadow-segment)]" : "text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
            }`}
          >
            <span className="text-[14px] font-medium">{t.label}</span>
            <span className="text-[12px] text-[var(--text-secondary)]">{counts[t.key]}</span>
          </button>
        ))}
      </nav>
        <span className="flex-1" />
        <ListControls
          basePath={`/seller/${storeId}/appeals`}
          params={{ ...query, ...(tab === "progress" ? {} : { tab }) }}
          sorts={APPEAL_SORTS}
          defaultSort={APPEAL_DEFAULT_SORT}
          filters={appealFilters(inTab)}
          search={{ placeholder: "Reviewer, review or your reason", label: "Search appeals" }}
        />
      </div>

      <section aria-label="Your flags at a glance" className="grid gap-3 sm:grid-cols-3">
        <Card label="In progress" value={String(s.open)} note={`${s.waitingOnReviewer} waiting on the reviewer`} />
        <Card label="Upheld" value={`${s.upheld} of ${s.decided}`} note="Removed after an admin check" />
        <Card
          label="Median time to decision"
          value={s.medianDays == null ? "—" : s.medianDays < 1 ? "Under a day" : `${Math.round(s.medianDays)} day${Math.round(s.medianDays) === 1 ? "" : "s"}`}
          note="From your flag to the decision"
        />
      </section>

      <div className="overflow-x-auto rounded-[16px] border border-[var(--border-subtle)]">
        <table className="w-full min-w-[900px] border-collapse text-left text-[14px]">
          <caption className="sr-only">Your flags</caption>
          <thead className="bg-[var(--surface-app)] text-[12px] text-[var(--text-secondary)]">
            <tr>
              {["Review", "Your reason", "Status", "Flagged", "Action"].map((h) => (
                <th key={h} scope="col" className="h-10 px-3 font-normal">
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 ? (
              <tr>
                <td colSpan={5} className="border-t border-[var(--border-subtle)] px-3 py-10 text-center text-[var(--text-secondary)]">
                  {appeals.length === 0
                    ? "You haven't flagged a review. Flag one from Reviews if you believe it is fake."
                    : filtering
                      ? "No flag matches these filters."
                      : tab === "progress"
                      ? "Nothing in progress."
                      : "Nothing decided yet."}
                </td>
              </tr>
            ) : (
              rows.map((a) => {
                const st = STATUS[a.status] ?? { label: a.status, tone: "neutral" as const };
                return (
                  <tr key={a.id} data-testid="seller-appeal-row" className="group border-t border-[var(--border-subtle)] align-top hover:bg-[var(--surface-app)]">
                    <td className="px-3 py-[10px]">
                      <span className="flex flex-col gap-1 leading-none">
                        <span>{reviewerOf(a)}</span>
                        <span className="text-[12px] text-[var(--text-secondary)]">
                          “{a.review_title || "Untitled review"}” · {a.review_rating ?? "—"}★
                        </span>
                      </span>
                    </td>
                    <td className="max-w-[360px] px-3 py-[10px] text-[var(--text-secondary)]">
                      <span className="line-clamp-2">{a.reason}</span>
                    </td>
                    <td className="px-3 py-[10px]">
                      <Chip tone={st.tone}>{st.label}</Chip>
                    </td>
                    <td className="whitespace-nowrap px-3 py-[10px] text-[var(--text-secondary)]" suppressHydrationWarning>
                      {agoShort(a.created_at, now)}
                    </td>
                    <td className="px-3 py-[6px]">
                      <button
                        type="button"
                        onClick={() => setOpen(a)}
                        className="h-8 rounded-full border border-[var(--border-subtle)] bg-[var(--surface-card)] px-3 text-[12px] hover:border-[var(--text-secondary)]"
                      >
                        View
                      </button>
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>
      <Pagination page={page.page} size={page.size} total={shown.length} onChange={setPage} label="Appeal pages" />
      {open ? <AppealModal storeId={storeId} appeal={open} onClose={() => setOpen(null)} now={now} /> : null}
    </div>
  );
}

function Card({ label, value, note }: { label: string; value: string; note: string }) {
  return (
    <div className="flex flex-col gap-2 rounded-[16px] border border-[var(--border-subtle)] p-5">
      <span className="text-[12px] text-[var(--text-secondary)]">{label}</span>
      <span className="text-[24px] font-semibold leading-none [font-variant-numeric:tabular-nums]">{value}</span>
      <span className="text-[12px] text-[var(--text-secondary)]">{note}</span>
    </div>
  );
}

function AppealModal({ storeId, appeal, onClose, now }: { storeId: string; appeal: StoreAppeal; onClose: () => void; now: number }) {
  const who = reviewerOf(appeal);
  const first = who.split(" ")[0];
  const decided = !isOpen(appeal);
  const asked = appeal.substantiation_requested_at;
  const steps: { label: string; note: string; state: "done" | "current" | "todo" }[] = [
    { label: "You flagged it", note: agoShort(appeal.created_at, now), state: "done" },
    asked
      ? { label: `An admin asked ${first} for proof of purchase`, note: agoShort(asked, now), state: "done" }
      : { label: "An admin checks your flag", note: decided ? "Done" : "Waiting for an admin", state: decided ? "done" : "current" },
    ...(asked && !decided
      ? [{ label: appeal.substantiated_at ? `${first} replied` : `Waiting for ${first}'s reply`, note: "Then an admin decides", state: "current" as const }]
      : []),
    decided
      ? {
          label: appeal.status === "upheld" ? "Upheld: the review was removed" : "Dismissed: the review stays up",
          note: appeal.decision_note || (appeal.decided_at ? agoShort(appeal.decided_at, now) : ""),
          state: "done",
        }
      : { label: "Decision", note: "You'll be notified either way", state: "todo" },
  ];
  return (
    <AdminModal title={`Your flag on ${who}’s review`} width={560} onClose={onClose}>
      <div className="flex flex-col gap-4 overflow-y-auto px-6 pb-5 pt-4">
        <ol aria-label="Flag progress" className="flex flex-col gap-4">
          {steps.map((s) => (
            <li key={s.label} className="flex items-start gap-3" aria-current={s.state === "current" ? "step" : undefined}>
              {s.state === "done" ? (
                <CheckCircle size={20} weight="fill" className="shrink-0 text-[var(--status-baseline-fg)]" aria-hidden />
              ) : s.state === "current" ? (
                <Clock size={20} weight="fill" className="shrink-0 text-[var(--accent-primary)]" aria-hidden />
              ) : (
                <Circle size={20} className="shrink-0 text-[var(--text-secondary)]" aria-hidden />
              )}
              <span className="flex flex-col gap-1">
                <span className={`text-[14px] ${s.state === "todo" ? "text-[var(--text-secondary)]" : ""}`}>{s.label}</span>
                {s.note ? <span className="text-[12px] text-[var(--text-secondary)]">{s.note}</span> : null}
              </span>
            </li>
          ))}
        </ol>
        <div className="flex flex-col gap-2 rounded-[16px] border border-[var(--border-subtle)] p-4">
          <div className="flex items-center gap-3">
            <PersonCell name={who} stage={appeal.reviewer?.trust_stage ?? null} />
            <span className="flex-1" />
            <StarRow value={appeal.review_rating ?? null} size={14} />
          </div>
          <p className="text-[14px] font-medium">{appeal.review_title || "Untitled review"}</p>
          {appeal.review_comment ? <p className="text-[14px] text-[var(--text-secondary)]">{appeal.review_comment}</p> : null}
        </div>
        <div>
          <p className="pb-1 text-[12px] font-medium uppercase tracking-[0.04em] text-[var(--text-secondary)]">Your reason</p>
          <p className="text-[14px] leading-[21px]">{appeal.reason}</p>
        </div>
      </div>
      <div className="flex items-center gap-3 border-t border-[var(--border-subtle)] px-6 py-4">
        {appeal.status !== "upheld" ? (
          <Link href={`/sellers/${storeId}#seller-review-${appeal.seller_review_id}`} className="h-9 rounded-full border border-[var(--text-primary)] px-4 text-[12px] leading-9">
            Open review
          </Link>
        ) : null}
        <span className="flex-1" />
        <button type="button" onClick={onClose} className="h-9 rounded-full bg-[var(--accent-primary)] px-5 text-[12px] text-white">
          Done
        </button>
      </div>
    </AdminModal>
  );
}
