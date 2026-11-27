import Link from "next/link";
import { CheckCircle, MinusCircle, WarningCircle } from "@phosphor-icons/react/dist/ssr";

import {
  REPORT_REASON_LABELS,
  originLabel,
  relativeAge,
  reviewIntegrityChecks,
} from "@/components/admin/review-queue-model";
import type { ReportItem } from "@/lib/moderation";

/**
 * Why was this reported? (dev/QA sync 2026-09-29, ENG-0929-B.)
 *
 * "Open the reported item" took an administrator to the review and left them
 * to work out the reason by hand. The team asked for the report's details
 * side by side with the reported item, as the Reviews tab already does. This
 * is that column: the server's explanation (written from stored fields only,
 * never generated), the evidence it rests on, the report's own facts, and the
 * reported content, before anyone decides.
 *
 * MQA-003: for a reported review, the integrity checks its Review Queue card
 * runs - vote spike, voting ring, copied text, reused photo, reverse image
 * search, web plagiarism, an edit after its link - so a report can be weighed
 * against what the System measured without opening the queue.
 */
export function ReportDetailPanel({ item, now }: { item: ReportItem; now: number }) {
  const why = item.explanation;
  const target = item.target;
  const reason = item.report.reason ? (REPORT_REASON_LABELS[item.report.reason] ?? item.report.reason) : null;
  return (
    <section
      id="report-detail"
      aria-label="Why this was reported"
      data-testid="report-detail"
      className="flex flex-col gap-3 rounded-[var(--radius-md)] bg-[var(--surface-card)] p-4 shadow-[var(--shadow-card)]"
    >
      <div>
        <h2 className="text-[14px] font-semibold text-[var(--text-primary)]">Why this was reported</h2>
        <p className="mt-1 flex flex-wrap gap-1.5 text-[11px] text-[var(--text-secondary)]">
          <span className="rounded-[var(--radius-pill)] bg-[var(--line-hairline-10)] px-2 py-0.5">
            {originLabel([item.origin ?? "user_reported"])}
          </span>
          {why?.signal_label ? (
            <span className="rounded-[var(--radius-pill)] bg-[var(--line-hairline-10)] px-2 py-0.5">
              {why.signal_label}
            </span>
          ) : reason ? (
            <span className="rounded-[var(--radius-pill)] bg-[var(--line-hairline-10)] px-2 py-0.5">{reason}</span>
          ) : null}
        </p>
        <p className="mt-2 text-[13px] leading-[20px] text-[var(--text-primary)]" data-testid="report-summary">
          {why?.summary ?? "No explanation is available for this report."}
        </p>
      </div>

      {why && why.evidence.length > 0 ? (
        <div>
          <h3 className="text-[12px] font-semibold text-[var(--text-primary)]">Evidence</h3>
          <dl className="mt-1 grid grid-cols-[auto_minmax(0,1fr)] gap-x-3 gap-y-1 text-[12px]">
            {why.evidence.map((e) => (
              <div key={e.label} className="contents">
                <dt className="text-[var(--text-secondary)]">{e.label}</dt>
                <dd className="min-w-0 break-words text-[var(--text-primary)]">
                  {e.link ? (
                    <Link href={e.link} className="underline hover:text-[var(--accent-primary)]">
                      {e.value}
                    </Link>
                  ) : (
                    e.value
                  )}
                </dd>
              </div>
            ))}
          </dl>
        </div>
      ) : null}

      {item.review_signals ? <IntegrityChecks item={item} /> : null}

      <div>
        <h3 className="text-[12px] font-semibold text-[var(--text-primary)]">The report</h3>
        <dl className="mt-1 grid grid-cols-[auto_minmax(0,1fr)] gap-x-3 gap-y-1 text-[12px]">
          <dt className="text-[var(--text-secondary)]">Filed</dt>
          <dd className="text-[var(--text-primary)]">
            <time dateTime={item.report.created_at}>{relativeAge(item.report.created_at, now)}</time>
          </dd>
          <dt className="text-[var(--text-secondary)]">Reports on this item</dt>
          <dd className="text-[var(--text-primary)]">{item.target_report_count}</dd>
          {/* The automatic priority threshold, not a moderator's Escalate (MQA-005:
              the two read alike, so this one says it is the queue's priority). */}
          <dt className="text-[var(--text-secondary)]">Queue priority</dt>
          <dd className="text-[var(--text-primary)]">
            {item.escalated
              ? item.urgent_reason
                ? "Top: urgent reason"
                : item.report_surge
                  ? "Top: report surge"
                  : "Top: weighted reports"
              : `Normal (weighted ${(item.target_weighted_reports ?? 0).toFixed(2)} of 1.00 to reach the top)`}
          </dd>
          {item.report.evidence_url ? (
            <>
              <dt className="text-[var(--text-secondary)]">Reporter&apos;s link</dt>
              <dd className="min-w-0 break-all text-[var(--text-primary)]">
                {/* Any web address the reporter gave (API only; nothing uploads it). It
                    opens in a new tab and is never loaded inline: an image from an
                    unknown host would tell that host who is looking. */}
                {/^https?:\/\//i.test(item.report.evidence_url) ? (
                  <>
                    <a href={item.report.evidence_url} target="_blank" rel="nofollow noopener noreferrer" className="underline hover:text-[var(--accent-primary)]">
                      {item.report.evidence_url}
                    </a>
                    <span className="block text-[11px] text-[var(--text-secondary)]">External site, opens in a new tab</span>
                  </>
                ) : (
                  // The API accepts http(s) only; a row from before that rule is shown, never linked.
                  <span>{item.report.evidence_url}</span>
                )}
              </dd>
            </>
          ) : null}
          <dt className="text-[var(--text-secondary)]">Status</dt>
          <dd className="text-[var(--text-primary)]">
            {item.report.resolution ? RESOLUTION_WORDS[item.report.resolution] : "Open"}
          </dd>
        </dl>
      </div>

      {target ? (
        <div>
          <h3 className="text-[12px] font-semibold text-[var(--text-primary)]">Reported content</h3>
          <div className="mt-1 rounded-[var(--radius-sm)] bg-[var(--surface-app)] p-3 text-[12px]">
            <p className="font-semibold text-[var(--text-primary)]">{target.title ?? "Untitled"}</p>
            <p className="mt-0.5 text-[var(--text-secondary)]">
              {[
                target.product_name,
                target.author_username ? `@${target.author_username}` : null,
                target.star_rating != null ? `${target.star_rating}★` : null,
                target.verdict ? (VERDICT_WORDS[target.verdict] ?? target.verdict) : null,
                target.state ? (STATE_WORDS[target.state] ?? target.state) : null,
              ]
                .filter(Boolean)
                .join(" · ")}
            </p>
            {target.excerpt ? (
              <p className="mt-2 whitespace-pre-line break-words text-[var(--text-primary)]">{target.excerpt}</p>
            ) : null}
            {target.link ? (
              <Link
                href={target.link}
                className="mt-2 inline-block text-[12px] underline hover:text-[var(--accent-primary)]"
              >
                Open the reported item
              </Link>
            ) : null}
          </div>
        </div>
      ) : null}
    </section>
  );
}

function IntegrityChecks({ item }: { item: ReportItem }) {
  const checks = reviewIntegrityChecks(item.review_signals);
  const flagged = checks.filter((c) => c.state === "flagged").length;
  return (
    <div data-testid="report-integrity">
      <h3 className="text-[12px] font-semibold text-[var(--text-primary)]">
        Integrity checks{" "}
        <span className={`font-normal ${flagged ? "text-[var(--accent-danger)]" : "text-[var(--text-secondary)]"}`}>
          · {flagged ? `${flagged} flagged` : "nothing flagged"}
        </span>
      </h3>
      <ul className="mt-1 flex flex-col gap-1.5 text-[12px]">
        {checks.map((c) => (
          <li key={c.key} data-state={c.state} className="flex items-start gap-1.5">
            {c.state === "flagged" ? (
              <WarningCircle size={14} weight="fill" aria-hidden className="mt-px shrink-0 text-[var(--accent-danger)]" />
            ) : c.state === "clear" ? (
              <CheckCircle size={14} weight="fill" aria-hidden className="mt-px shrink-0 text-[var(--accent-trust)]" />
            ) : (
              <MinusCircle size={14} aria-hidden className="mt-px shrink-0 text-[var(--text-muted)]" />
            )}
            <span className="min-w-0 [overflow-wrap:anywhere]">
              <span className={c.state === "flagged" ? "font-semibold text-[var(--accent-danger)]" : "text-[var(--text-primary)]"}>
                {c.label}
              </span>
              <span className="sr-only">{c.state === "flagged" ? " (flagged)" : c.state === "clear" ? " (passed)" : " (did not run)"}</span>
              <span className="text-[var(--text-secondary)]"> · {c.detail}</span>
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}

const RESOLUTION_WORDS: Record<string, string> = {
  dismissed: "Dismissed: the content stands",
  content_removed: "Content taken down",
  content_restored: "Content restored",
  escalated: "Escalated to a Super Admin",
};

const VERDICT_WORDS: Record<string, string> = {
  yes_absolutely: "Yes, absolutely",
  it_depends: "It depends",
  hard_pass: "Hard pass",
};

const STATE_WORDS: Record<string, string> = {
  published: "Published",
  taken_down: "Taken down",
  removed: "Removed",
  member: "Member account",
};
