"use client";

import Link from "next/link";

import { outcomeLabel } from "@/components/admin/activity/activity-outcome";
import { useEffect, useRef, useState } from "react";
import {
  ArrowRight,
  Bell,
  CheckCircle,
  DownloadSimple,
  LinkSimple,
  WarningCircle,
  Wallet,
  XCircle,
  Gear,
} from "@phosphor-icons/react/dist/ssr";

import type { ActivityRow } from "@/lib/moderation";

/**
 * The top bar's activity button and its popover, built to
 * "Overlay/Admin/Activity" (7881:10289, read 2026-10-02).
 *
 * Rows are the moderation audit log (GET /admin/activity), newest first.
 * `receipt_view` is left out, as on the Overview's feed: it records an
 * administrator opening someone's proof of purchase, and advertising that as
 * routine activity is not the console's business.
 *
 * "Mark all seen" is a per-browser convenience (the time it was pressed, in
 * localStorage). Nothing about it is shared or authoritative, and the popover
 * renders the same with storage unavailable, only without unread dots.
 */

type Category = "moderation" | "money" | "system";

const MONEY = new Set([
  "affiliate_link_attach", "affiliate_link_revoke", "csv_import", "payout",
  "honesty_fund_distribution", "remittance_record", "cashout_request", "qa_test_credit",
  "listing_attach",
]);
const MODERATION = new Set([
  "report", "approve", "reject", "remove", "penalize", "suspend", "restore", "override",
  "escalate", "publish", "unpublish", "best_answer_pick", "seller_appeal",
  "substantiation_request", "appeal_decision", "investigation_set", "investigation_clear",
  "special_routing", "photo_replace", "alias_add", "support_request", "author_delete",
  "track_flip", "cold_start_substitution", "store_product", "product_import",
]);

function categoryOf(action: string): Category {
  if (MONEY.has(action)) return "money";
  if (MODERATION.has(action)) return "moderation";
  return "system";
}

const LABEL: Record<string, string> = {
  report: "Filed a report",
  approve: "Approved a review",
  reject: "Rejected a review",
  remove: "Removed content",
  publish: "Published a review",
  unpublish: "Took down a review",
  restore: "Restored a review",
  escalate: "Escalated a review",
  penalize: "Penalized an account",
  suspend: "Suspended an account",
  override: "Overrode a decision",
  affiliate_link_attach: "Generated an affiliate link",
  affiliate_link_revoke: "Revoked an affiliate link",
  csv_import: "Imported commissions",
  payout: "Recorded a payout",
  honesty_fund_distribution: "Distributed the Honesty Fund",
  remittance_record: "Recorded a remittance",
  cashout_request: "Requested a payout",
  role_grant: "Granted a role",
  role_revoke: "Revoked a role",
  best_answer_pick: "Picked a best answer",
  seller_appeal: "Seller appealed a review",
  appeal_decision: "Decided an appeal",
  investigation_set: "Opened an investigation",
  investigation_clear: "Closed an investigation",
  special_routing: "Routed an \"It depends\" review",
  support_request: "Support request",
  store_product: "Decided a product link",
  store_release: "Gave up a store",
  data_export: "Exported data",
  product_import: "Imported products",
};

function labelFor(action: string, outcome?: string | null): string {
  return outcomeLabel(outcome) ?? LABEL[action] ?? action.replaceAll("_", " ").replace(/^./, (c) => c.toUpperCase());
}

function IconFor({ action }: { action: string }) {
  const size = 16;
  if (action === "approve" || action === "publish" || action === "restore")
    return <CheckCircle size={size} className="text-[var(--accent-success)]" />;
  if (action === "reject" || action === "remove" || action === "unpublish" || action === "suspend")
    return <XCircle size={size} className="text-[var(--accent-danger)]" />;
  if (action.startsWith("affiliate_link") || action === "listing_attach")
    return <LinkSimple size={size} className="text-[var(--accent-trust)]" />;
  if (action === "csv_import") return <DownloadSimple size={size} className="text-[var(--accent-primary)]" />;
  if (categoryOf(action) === "money") return <Wallet size={size} className="text-[var(--accent-primary)]" />;
  if (categoryOf(action) === "system") return <Gear size={size} className="text-[var(--text-secondary)]" />;
  return <WarningCircle size={size} className="text-[var(--accent-primary)]" />;
}

/** "2m", "1h", "3d": the overlay's short ages. */
function shortAge(iso: string, now: number): string {
  const s = Math.max(0, Math.round((now - new Date(iso).getTime()) / 1000));
  if (s < 60) return `${s}s`;
  if (s < 3600) return `${Math.round(s / 60)}m`;
  if (s < 86400) return `${Math.round(s / 3600)}h`;
  return `${Math.round(s / 86400)}d`;
}

const SEEN_KEY = "bluntly.admin.activity.seen";
const TABS: { key: "all" | Category; label: string }[] = [
  { key: "all", label: "All" },
  { key: "moderation", label: "Moderation" },
  { key: "money", label: "Money" },
  { key: "system", label: "System" },
];

export function AdminActivityMenu({ rows, fetchedAt }: { rows: ActivityRow[] | null; fetchedAt: number }) {
  const [open, setOpen] = useState(false);
  const [tab, setTab] = useState<"all" | Category>("all");
  const [seenAt, setSeenAt] = useState<number | null>(null);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    try {
      const v = window.localStorage.getItem(SEEN_KEY);
      // Read once after mount: storage is not available during the server render.
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setSeenAt(v ? Number(v) : 0);
    } catch {
      setSeenAt(null);
    }
    function onClick(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    }
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") setOpen(false);
    }
    window.addEventListener("mousedown", onClick);
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("mousedown", onClick);
      window.removeEventListener("keydown", onKey);
    };
  }, []);

  const feed = (rows ?? []).filter((r) => r.action !== "receipt_view");
  const unread = (r: ActivityRow) => seenAt !== null && new Date(r.at).getTime() > seenAt;
  const anyUnread = feed.some(unread);
  const shown = feed.filter((r) => tab === "all" || categoryOf(r.action) === tab).slice(0, 6);

  function markSeen() {
    const now = Date.now();
    try {
      window.localStorage.setItem(SEEN_KEY, String(now));
    } catch {
      /* storage blocked: the dots simply stay */
    }
    setSeenAt(now);
  }

  return (
    <div ref={ref} className="relative">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        aria-haspopup="dialog"
        aria-label={anyUnread ? "Recent activity, unread items" : "Recent activity"}
        className="relative grid size-[34px] place-items-center rounded-full border border-[var(--border-subtle)] bg-[var(--surface-card)] hover:bg-[var(--surface-app)] focus-visible:outline focus-visible:outline-2 focus-visible:outline-[var(--accent-primary)]"
      >
        <Bell size={18} />
        {anyUnread ? (
          <span className="absolute right-[7px] top-[7px] size-[6px] rounded-full bg-[var(--accent-primary)]" aria-hidden />
        ) : null}
      </button>

      {open ? (
        <div
          role="dialog"
          aria-label="Recent activity"
          className="absolute right-0 top-[calc(100%+8px)] z-40 flex w-[360px] max-w-[calc(100vw-32px)] flex-col gap-1 rounded-[16px] border border-[var(--border-subtle)] bg-[var(--surface-card)] pb-2 pt-[14px] shadow-[var(--shadow-modal)]"
        >
          <div className="flex items-center gap-2 px-4 pb-[6px] leading-none">
            <p className="flex-1 text-[14px] font-semibold">Recent activity</p>
            <button
              type="button"
              onClick={markSeen}
              className="text-[12px] font-medium text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
            >
              Mark all seen
            </button>
          </div>
          <div role="tablist" className="flex gap-1 px-3 pb-[6px]">
            {TABS.map((t) => (
              <button
                key={t.key}
                type="button"
                role="tab"
                aria-selected={tab === t.key}
                onClick={() => setTab(t.key)}
                className={`rounded-full px-[10px] py-1 text-[12px] font-medium leading-none ${
                  tab === t.key ? "bg-[var(--surface-app)] text-[var(--text-primary)]" : "text-[var(--text-secondary)]"
                }`}
              >
                {t.label}
              </button>
            ))}
          </div>

          {rows === null ? (
            <p className="px-4 py-3 text-[12px] text-[var(--text-secondary)]">The activity log could not be loaded.</p>
          ) : shown.length === 0 ? (
            <p className="px-4 py-3 text-[12px] text-[var(--text-secondary)]">Nothing recorded here yet.</p>
          ) : (
            <ul>
              {shown.map((r) => {
                const body = (
                  <>
                    <span className="rounded-full bg-[var(--surface-app)] p-[6px]">
                      <IconFor action={r.action} />
                    </span>
                    <span className="flex min-w-0 flex-1 flex-col gap-px leading-none">
                      <span className="truncate text-[12px] font-medium">{labelFor(r.action, r.outcome)}</span>
                      <span className="truncate text-[10px] text-[var(--text-secondary)]" title={r.target_label ?? undefined}>
                        {[r.actor ?? "System", r.target_label ?? r.target_type?.replaceAll("_", " ")].filter(Boolean).join(" · ")}
                      </span>
                    </span>
                    <span className="flex items-center gap-[6px] text-[10px] leading-none text-[var(--text-secondary)]">
                      {shortAge(r.at, fetchedAt)}
                      {unread(r) ? <span className="size-[6px] rounded-full bg-[var(--accent-primary)]" aria-label="unread" /> : null}
                    </span>
                  </>
                );
                // MQA-016: an entry with a target opens it; opening marks the list seen.
                return (
                  <li key={r.id}>
                    {r.href ? (
                      <Link
                        href={r.href}
                        onClick={() => {
                          markSeen();
                          setOpen(false);
                        }}
                        className="flex items-start gap-[10px] px-4 py-2 hover:bg-[var(--surface-app)] focus-visible:outline focus-visible:outline-2 focus-visible:outline-[var(--accent-primary)]"
                      >
                        {body}
                      </Link>
                    ) : (
                      <div className="flex items-start gap-[10px] px-4 py-2">{body}</div>
                    )}
                  </li>
                );
              })}
            </ul>
          )}

          <Link
            href="/admin/activity"
            onClick={() => setOpen(false)}
            className="flex items-center gap-1 border-t border-[var(--border-subtle)] px-4 pb-1 pt-2 text-[12px] font-medium leading-none hover:text-[var(--accent-primary)]"
          >
            <span className="flex-1">Open activity log</span>
            <ArrowRight size={14} />
          </Link>
        </div>
      ) : null}
    </div>
  );
}
