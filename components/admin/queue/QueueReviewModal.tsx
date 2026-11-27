"use client";

import Image from "next/image";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import {
  CaretLeft,
  CaretRight,
  CheckCircle,
  Package,
  ShieldCheck,
  Star,
  WarningCircle,
  X,
} from "@phosphor-icons/react/dist/ssr";

import { ImageViewer } from "@/components/console/ImageViewer";
import { EarningCell, TierCell, earningPath, levelLabel, starTone } from "@/components/admin/queue/QueueCells";
import { QueueDecisionBar } from "@/components/admin/queue/QueueDecisionBar";
import { AuthorPanel, OriginalityPanel } from "@/components/admin/queue/InvestigationTabs";
import { VotersPanel, VotesPanel, useInvestigation } from "@/components/admin/queue/ReviewInvestigation";
import { TierReasons } from "@/components/admin/TierBadge";
import {
  accountAgeLabel,
  engagementFor,
  factorLines,
  originLabel,
  queueAgeLabel,
  relativeAge,
  reviewIdLabel,
  slaStat,
} from "@/components/admin/review-queue-model";
import type { QueueItem, ReportItem } from "@/lib/moderation";

/**
 * The queue's investigation, moved into a modal (meeting 2026-10-02: "the
 * details, the investigation part, is a modal so both can have the space they
 * deserve"), built to Overlay/Queue/Review 8042:13037.
 *
 * Left, the review as written and who wrote it; right, what needs a look. A
 * "problem" is a check that FIRED on this card (collusion, vote spike, copied
 * text, open reports, an edit after the link); a check that ran and did not
 * fire is listed as passed. Nothing is inferred beyond what the card carries:
 * the frame's per-vote timeline needs vote timestamps this card does not
 * serve, so the voting ring is stated in the counts the check actually uses.
 */
export function QueueReviewModal({
  item,
  index,
  total,
  offset,
  reports,
  now,
  onClose,
  onStep,
}: {
  item: QueueItem;
  index: number;
  total: number;
  offset: number;
  reports: ReportItem[];
  now: number;
  onClose: () => void;
  onStep: (delta: number) => void;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  // Overlay/Review/Investigate (8109–8117): Summary is the card below; Votes and
  // Voters read GET /admin/reviews/{id}/investigation once per review; Originality
  // and Author read their own endpoints when opened.
  const [tab, setTab] = useState<"summary" | "votes" | "voters" | "originality" | "author">("summary");
  const [photoOpen, setPhotoOpen] = useState(false);
  const investigation = useInvestigation(item.review.id);

  useEffect(() => {
    const dialog = ref.current;
    if (dialog && !dialog.open) dialog.showModal();
    function onKey(e: KeyboardEvent) {
      const t = e.target as HTMLElement | null;
      if (document.querySelectorAll("dialog[open]").length > 1) return; // a confirm is up
      if (t && (t.tagName === "INPUT" || t.tagName === "TEXTAREA" || t.tagName === "SELECT")) return;
      if (e.key === "j" || e.key === "J") onStep(1);
      if (e.key === "k" || e.key === "K") onStep(-1);
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onStep]);

  const r = item.review;
  // A signed link can expire while the queue is open: the photo then falls back
  // (header: the frame's placeholder; body: no photo button) instead of a broken image.
  const [thumbFailed, setThumbFailed] = useState(false);
  const [photoFailed, setPhotoFailed] = useState(false);
  const s = item.signals;
  const v = item.voting;
  const engagement = engagementFor(item, reports);
  const reportCount = engagement.reports.available ? Number(engagement.reports.value) : 0;
  const edited = Boolean(item.edited_since_monetized);
  const sla = slaStat(item, now);
  const author = item.author?.display_name ?? "Former member";
  const platform = item.suggested_platform ?? item.product.platforms[0]?.platform ?? null;

  const problems: { key: string; title: string; body: React.ReactNode; link?: { href: string; label: string } }[] = [];
  if (s.collusion) {
    problems.push({
      key: "ring",
      title: "Voting ring",
      body: v
        ? `${v.reciprocal_upvoters} of ${v.upvoters} up-voters are up-voted back by ${author}. The check fires at ${v.min_upvoters}+ up-voters above ${Math.round(v.threshold * 100)}% reciprocal.`
        : "The voting pattern matches the collusion check.",
      link: item.author ? { href: `/admin/people/${item.author.id}?tab=interactions`, label: "See voters" } : undefined,
    });
  }
  if (s.velocity) {
    problems.push({
      key: "spike",
      title: "Vote spike",
      body: v
        ? `${v.max_upvotes_in_velocity_window} up-votes within one hour; the check fires above ${v.velocity_threshold}.`
        : "Up-votes arrived faster than this check allows.",
    });
  }
  if (s.duplicate_content) {
    problems.push({
      key: "copy",
      title: "Copied text",
      body: "The body matches text already published on Bluntly. The System filed a report with the match.",
      link: { href: "/admin/review-queue?tab=report", label: "Open reports" },
    });
  }
  if (reportCount > 0) {
    problems.push({
      key: "reports",
      title: `${reportCount} open ${reportCount === 1 ? "report" : "reports"}`,
      body: `From ${originLabel(item.priority.origins).toLowerCase()}.`,
      link: { href: "/admin/review-queue?tab=report", label: "Open reports" },
    });
  }
  if (edited) {
    problems.push({
      key: "edited",
      title: "Edited after its link",
      body: "Changed since its affiliate link was attached. Re-read it before it keeps earning.",
    });
  }

  const passed = [
    !s.collusion && v && v.upvoters > 0 ? "Votes look independent" : null,
    !s.velocity ? "No vote spike" : null,
    !s.duplicate_content ? "Text is original" : null,
    reportCount === 0 && engagement.reports.available ? "No reports on this review" : null,
    !edited ? "Not edited after a link" : null,
  ].filter(Boolean) as string[];

  const factors = factorLines(item);

  return (
    <dialog
      ref={ref}
      onCancel={(e) => {
        e.preventDefault();
        onClose();
      }}
      aria-label={`Review: ${r.title}`}
      className="m-auto flex h-[min(714px,calc(100dvh-32px))] w-[1200px] max-w-[calc(100vw-32px)] flex-col overflow-hidden rounded-[24px] bg-[var(--surface-card)] p-0 text-[var(--text-primary)] shadow-[var(--shadow-modal)] backdrop:bg-black/30 [&:not([open])]:hidden"
    >
      {/* Header */}
      <div className="flex shrink-0 flex-wrap items-center gap-4 border-b border-[var(--border-subtle)] px-6 py-5 sm:px-8">
        <span className="relative grid size-9 shrink-0 place-items-center overflow-hidden rounded-[8px] bg-[var(--surface-app)]">
          {r.photo_url && !thumbFailed ? (
            <Image src={r.photo_url} alt="" fill sizes="36px" className="object-cover" onError={() => setThumbFailed(true)} />
          ) : (
            <Package size={18} className="text-[var(--text-muted)]" aria-hidden />
          )}
        </span>
        <div className="min-w-0 flex-1">
          <h2 className="truncate text-[20px] font-semibold leading-tight">{r.title}</h2>
          <p className="mt-0.5 truncate text-[12px] text-[var(--text-secondary)]">
            Review of {item.product.canonical_name ?? "an unlisted product"}
            {platform ? ` · ${platform.charAt(0).toUpperCase()}${platform.slice(1)}` : ""} · posted{" "}
            {relativeAge(r.created_at, now)} · in queue {queueAgeLabel(item, now)}
            <span className="sr-only"> · {reviewIdLabel(r)}</span>
          </p>
        </div>
        <div className="flex items-center gap-5 text-[14px]">
          <TierCell tier={item.triage?.tier} />
          <EarningCell path={earningPath(r)} />
          <span className="flex items-center gap-1 text-[12px] text-[var(--text-secondary)]">
            <button
              type="button"
              onClick={() => onStep(-1)}
              disabled={index === 0}
              aria-label="Previous review"
              className="grid size-7 place-items-center rounded-full border border-[var(--base-ink-800)] disabled:opacity-30"
            >
              <CaretLeft size={14} />
            </button>
            {offset + index + 1} of {total}
            <button
              type="button"
              onClick={() => onStep(1)}
              disabled={offset + index + 1 >= total}
              aria-label="Next review"
              className="grid size-7 place-items-center rounded-full border border-[var(--base-ink-800)] disabled:opacity-30"
            >
              <CaretRight size={14} />
            </button>
          </span>
          <button type="button" onClick={onClose} aria-label="Close" className="grid size-8 place-items-center rounded-full hover:bg-[var(--surface-app)]">
            <X size={18} />
          </button>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex shrink-0 flex-wrap items-center gap-3 border-b border-[var(--border-subtle)] px-6 py-3 sm:px-8">
        <div role="tablist" aria-label="Investigate" className="flex gap-[2px] rounded-[10px] bg-[var(--surface-app)] p-[3px]">
          {(
            [
              ["summary", "Summary", null],
              ["votes", "Votes", investigation.data ? String(investigation.data.votes_total) : null],
              ["voters", "Voters", investigation.data ? `${investigation.data.flagged} flagged` : null],
              ["originality", "Originality", null],
              ["author", "Author", null],
            ] as const
          ).map(([key, label, count]) => (
            <button
              key={key}
              type="button"
              role="tab"
              id={`investigate-tab-${key}`}
              aria-selected={tab === key}
              aria-controls="investigate-panel"
              onClick={() => setTab(key)}
              className={`flex items-center gap-[6px] rounded-[8px] px-3 py-[5px] leading-none ${
                tab === key ? "bg-[var(--surface-card)] shadow-[var(--shadow-segment)]" : "text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
              }`}
            >
              <span className="text-[14px] font-medium">{label}</span>
              {count !== null ? <span className="text-[12px] text-[var(--text-secondary)]">{count}</span> : null}
            </button>
          ))}
        </div>
        <span className="flex-1" />
        {problems.length > 0 ? (
          <span className="inline-flex items-center gap-1 rounded-full bg-[var(--status-high-bg)] px-3 py-1 text-[12px] font-medium text-[var(--accent-danger)]">
            <WarningCircle size={14} weight="fill" aria-hidden />
            {problems.length} {problems.length === 1 ? "signal needs" : "signals need"} a look
          </span>
        ) : null}
      </div>

      {tab === "votes" ? (
        <div id="investigate-panel" role="tabpanel" aria-labelledby="investigate-tab-votes" className="min-h-0 flex-1 overflow-y-auto">
          <VotesPanel data={investigation.data} failed={investigation.failed} />
        </div>
      ) : tab === "voters" ? (
        <div id="investigate-panel" role="tabpanel" aria-labelledby="investigate-tab-voters" className="min-h-0 flex-1 overflow-y-auto">
          <VotersPanel data={investigation.data} failed={investigation.failed} author={author} />
        </div>
      ) : tab === "originality" ? (
        <div id="investigate-panel" role="tabpanel" aria-labelledby="investigate-tab-originality" className="min-h-0 flex-1 overflow-y-auto">
          <OriginalityPanel kind="reviews" id={item.review.id} />
        </div>
      ) : tab === "author" ? (
        <div id="investigate-panel" role="tabpanel" aria-labelledby="investigate-tab-author" className="min-h-0 flex-1 overflow-y-auto">
          {item.author ? <AuthorPanel kind="reviews" id={item.review.id} /> : <p className="p-6 text-[14px] text-[var(--text-secondary)]">The author&apos;s account no longer exists.</p>}
        </div>
      ) : (
      <div id="investigate-panel" role="tabpanel" aria-labelledby="investigate-tab-summary" className="grid min-h-0 flex-1 overflow-y-auto md:grid-cols-[minmax(0,480px)_minmax(0,1fr)]">
        {/* Left: the review and its author */}
        <div className="flex flex-col gap-5 border-[var(--border-subtle)] p-6 md:border-r">
          <section className="rounded-[16px] border border-[var(--border-subtle)] p-4">
            <div className="flex items-center gap-3 border-b border-[var(--border-subtle)] pb-3">
              <span className="grid size-10 shrink-0 place-items-center rounded-full bg-[var(--surface-app)] text-[16px] font-medium">
                {author.slice(0, 1).toUpperCase()}
              </span>
              <span className="min-w-0 flex-1 leading-tight">
                {item.author ? (
                  <Link href={`/admin/people/${item.author.id}`} className="block truncate text-[14px] font-medium hover:text-[var(--accent-primary)]">
                    {author}
                  </Link>
                ) : (
                  <span className="block truncate text-[14px] font-medium">{author}</span>
                )}
                <span className="block truncate text-[12px] text-[var(--text-secondary)]">
                  {levelLabel(item.author?.trust_stage)} · joined {accountAgeLabel(s.author_account_age_days)} ·{" "}
                  {s.author_review_count} {s.author_review_count === 1 ? "review" : "reviews"}
                </span>
              </span>
              {item.author ? (
                <span className="inline-flex items-center gap-1 text-[16px] font-medium" title="Trust score, 0 to 100">
                  <ShieldCheck size={18} weight="fill" className="text-[var(--accent-trust)]" />
                  {Math.round(Number(item.author.reputation_score))}
                </span>
              ) : null}
            </div>

            <div className="flex items-center justify-between pt-3">
              <span className="flex gap-0.5" aria-label={`${r.star_rating} of 5 stars`}>
                {[1, 2, 3, 4, 5].map((n) => (
                  <Star
                    key={n}
                    size={18}
                    weight="fill"
                    className={n <= Math.round(r.star_rating) ? starTone(r.star_rating) : "text-[var(--base-gray-200)]"}
                  />
                ))}
              </span>
              <span className="text-[12px] text-[var(--text-secondary)]">Posted {relativeAge(r.created_at, now)}</span>
            </div>
            <p className="mt-3 whitespace-pre-line text-[14px] leading-relaxed">{r.discussion}</p>
            {r.photo_url && !photoFailed ? (
              <button
                type="button"
                onClick={() => setPhotoOpen(true)}
                aria-label="Open the reviewer's photo"
                className="relative mt-3 block size-24 overflow-hidden rounded-[8px] bg-[var(--surface-app)] focus-visible:outline focus-visible:outline-2 focus-visible:outline-[var(--accent-primary)]"
              >
                <Image src={r.photo_url} alt="The reviewer's photo" fill sizes="96px" className="object-cover" onError={() => setPhotoFailed(true)} />
              </button>
            ) : null}
            {photoOpen && r.photo_url ? (
              <ImageViewer
                title="The reviewer's photo"
                src={r.photo_url}
                alt={`The reviewer's photo for ${r.title ?? "this review"}`}
                meta={`Image · review posted ${relativeAge(r.created_at, now)}`}
                downloadHref={r.photo_url}
                onClose={() => setPhotoOpen(false)}
              />
            ) : null}

            {/* MQA-044: three equal columns, two rows. Six in this ~400px card
                left each label ~58px, and the unwrapped "comments" ran into
                "reports" - the count that matters most for a take-down. */}
            <dl className="mt-4 grid grid-cols-3 gap-x-4 gap-y-3 border-t border-[var(--border-subtle)] pt-3" data-testid="engagement-figures">
              {[
                { label: "Up-votes", value: String(engagement.upvotes) },
                { label: "Down-votes", value: String(engagement.downvotes) },
                { label: "Comments", stat: engagement.comments },
                { label: "Reports", stat: engagement.reports },
                { label: "Views", stat: engagement.views },
                { label: "Shares", stat: engagement.shares },
              ].map((cell) => {
                const value = "value" in cell ? cell.value : cell.stat.available ? cell.stat.value : "—";
                const why = "stat" in cell && cell.stat && !cell.stat.available ? cell.stat.reason : undefined;
                return (
                  <div key={cell.label} title={why} className="flex min-w-0 flex-col-reverse gap-1 leading-none">
                    <dt className="text-[12px] text-[var(--text-secondary)] [overflow-wrap:anywhere]">{cell.label}</dt>
                    <dd className={`text-[16px] font-medium ${cell.label === "Reports" && value !== "0" && value !== "—" ? "text-[var(--accent-danger)]" : ""}`}>{value}</dd>
                  </div>
                );
              })}
            </dl>
          </section>

          {passed.length > 0 ? (
            <ul className="flex flex-col gap-3 text-[14px]">
              {passed.map((p) => (
                <li key={p} className="flex items-center gap-2">
                  <CheckCircle size={18} weight="fill" className="text-[var(--accent-success)]" />
                  {p}
                </li>
              ))}
              <li className="flex items-center gap-2 text-[var(--text-secondary)]">
                <span className="w-[18px]" />
                Public Wilson score <span data-testid="queue-wilson">{Number(r.wilson_score).toFixed(2)}</span>
              </li>
            </ul>
          ) : null}
        </div>

        {/* Right: what to look at */}
        <div className="flex flex-col p-6">
          <div className="border-b border-[var(--border-subtle)] pb-4">
            <p className="flex items-center gap-2 text-[20px] font-semibold leading-tight">
              {problems.length > 0 ? (
                <WarningCircle size={20} weight="fill" className="text-[var(--accent-danger)]" />
              ) : (
                <CheckCircle size={20} weight="fill" className="text-[var(--accent-success)]" />
              )}
              {problems.length === 0
                ? "Nothing fired on this review"
                : `${problems.length} ${problems.length === 1 ? "problem" : "problems"} to look at`}
            </p>
            <p className="mt-1 text-[14px] text-[var(--text-secondary)]">
              {problems.length > 0 ? `${problems.map((p) => p.title).join(", ")}. ` : ""}
              {passed.length} {passed.length === 1 ? "check" : "checks"} passed.
              {sla.available ? ` ${sla.value}.` : ""}
            </p>
          </div>

          {investigation.data && investigation.data.flagged > 0 ? (
            <section data-testid="without-flagged" className="border-b border-[var(--border-subtle)] py-4">
              <h3 className="text-[14px] font-medium">
                If you leave out the {investigation.data.flagged} flagged {investigation.data.flagged === 1 ? "vote" : "votes"}
              </h3>
              <dl className="mt-2 grid grid-cols-3 gap-2">
                {[
                  ["Gate Wilson", `${investigation.data.gate_all.wilson_lower_bound.toFixed(2)} → ${investigation.data.gate_without_flagged.wilson_lower_bound.toFixed(2)}`],
                  ["Gate", investigation.data.gate_without_flagged.passes ? "Still passes" : investigation.data.gate_all.passes ? "Stops passing" : "Does not pass"],
                  ["Votes left", String(investigation.data.gate_without_flagged.voters)],
                ].map(([k, v]) => (
                  <div key={k} className="rounded-[12px] bg-[var(--surface-app)] px-3 py-2">
                    <dt className="text-[12px] text-[var(--text-secondary)]">{k}</dt>
                    <dd className={`text-[16px] font-semibold ${v === "Stops passing" ? "text-[var(--accent-danger)]" : ""}`}>{v}</dd>
                  </div>
                ))}
              </dl>
              <button type="button" onClick={() => setTab("voters")} className="mt-2 text-[12px] text-[var(--accent-trust)] hover:underline">
                See who is flagged and why
              </button>
            </section>
          ) : null}

          {problems.map((p) => (
            <section key={p.key} className="border-b border-[var(--border-subtle)] py-4">
              <div className="flex items-center gap-2">
                <WarningCircle size={16} weight="fill" className="text-[var(--accent-danger)]" />
                <h3 className="flex-1 text-[14px] font-medium">{p.title}</h3>
                {p.link ? (
                  <Link href={p.link.href} className="text-[14px] text-[var(--accent-trust)] hover:underline">
                    {p.link.label}
                  </Link>
                ) : null}
              </div>
              <p className="mt-1 text-[14px] text-[var(--text-secondary)]">{p.body}</p>
            </section>
          ))}

          <section className="border-b border-[var(--border-subtle)] py-4">
            <h3 className="text-[14px] font-medium">Why it is {item.triage ? item.triage.tier : "here"}</h3>
            {item.triage ? <TierReasons triage={item.triage} /> : null}
            {factors.length > 0 ? (
              <ul className="mt-2 flex flex-col gap-1">
                {factors.map((f) => (
                  <li key={f.code} className="text-[12px] text-[var(--text-secondary)]">
                    +{f.contribution} · {f.explanation}
                  </li>
                ))}
              </ul>
            ) : (
              <p className="mt-1 text-[12px] text-[var(--text-secondary)]">
                No priority factor fired; it is ordered by how long it has waited.
              </p>
            )}
          </section>

          <p className="flex flex-wrap items-center gap-2 py-4 text-[14px]">
            <span className="text-[12px] text-[var(--text-secondary)]">History</span>
            <span className="flex-1">
              {s.author_review_count} {s.author_review_count === 1 ? "review" : "reviews"}
              {item.author ? `, ${item.author.verified_review_count} verified` : ""} · account{" "}
              {accountAgeLabel(s.author_account_age_days).replace(" ago", " old")}
            </span>
            {item.author ? (
              <Link href={`/admin/people/${item.author.id}`} className="text-[var(--accent-trust)] hover:underline">
                Open person
              </Link>
            ) : null}
          </p>
        </div>
      </div>
      )}

      <QueueDecisionBar item={item} onDecided={onClose} />
    </dialog>
  );
}
