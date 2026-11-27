"use client";

import { useEffect, useState } from "react";
import { Lightning, LinkSimple, Timer, UserPlus, UsersThree } from "@phosphor-icons/react";

import { AdminModal } from "@/components/admin/AdminModal";
import { PlacesCard } from "@/components/admin/queue/InvestigationTabs";

/**
 * The Votes and Voters tabs of the review investigation (Figma
 * Overlay/Review/Investigate/Votes 8110:17539, /Voters 8117:17753), read from
 * GET /admin/reviews/{id}/investigation. Read-only: nothing here removes a
 * vote. "Where votes came from" (8237:26485) reads the hourly first-vote place
 * counts, which carry no voter, so a flagged vote is never placed.
 */

export type Investigation = import("@/lib/api-types").components["schemas"]["InvestigationOut"];
type Voter = Investigation["voters"][number];
/** What the Voters tab and All voters need: a review's or an answer's voters. */
export type VoterData = Pick<Investigation, "voters" | "flagged" | "history_size">;

export function useInvestigation(reviewId: string): { data: Investigation | null; failed: boolean } {
  const [state, setState] = useState<{ id: string; data: Investigation | null; failed: boolean }>({ id: "", data: null, failed: false });
  useEffect(() => {
    let live = true;
    fetch(`/api/bff/api/v1/admin/reviews/${reviewId}/investigation`)
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(String(r.status)))))
      .then((data: Investigation) => live && setState({ id: reviewId, data, failed: false }))
      .catch(() => live && setState({ id: reviewId, data: null, failed: true }));
    return () => {
      live = false;
    };
  }, [reviewId]);
  return state.id === reviewId ? state : { data: null, failed: false };
}

export function after(seconds: number): string {
  if (seconds < 60) return "under 1 min";
  const m = Math.round(seconds / 60);
  if (m < 60) return `${m} min`;
  const h = Math.round(m / 60);
  if (h < 48) return `${h} h`;
  return `${Math.round(h / 24)} d`;
}

const FLAG = "var(--accent-primary)";
const UP = "var(--base-gray-400)";
const DOWN = "var(--accent-danger)";

function Pending({ failed }: { failed: boolean }) {
  return (
    <p role={failed ? "alert" : "status"} className="p-6 text-[14px] text-[var(--text-secondary)]">
      {failed ? "The votes could not be loaded. This is not an empty list: nothing is known right now." : "Loading the votes…"}
    </p>
  );
}

/** Up-votes above the axis, down-votes below, on a log time scale from publishing. */
export function Timeline({ voters }: { voters: Voter[] }) {
  const W = 900;
  const H = 150;
  const AXIS = 80;
  const lo = Math.log10(30);
  const last = Math.max(...voters.map((v) => v.seconds_after), 2 * 86400);
  const hi = Math.log10(last);
  const x = (s: number) => 40 + ((Math.log10(Math.max(s, 30)) - lo) / (hi - lo)) * (W - 60);
  const ticks: [number, string][] = [[60, "1 min"], [600, "10 min"], [3600, "1 h"], [21600, "6 h"], [172800, "2 days"], [604800, "1 week"], [2592000, "30 days"]];
  const shown = ticks.filter(([s]) => s <= last);
  // A stable, small vertical spread so dots at the same moment don't sit on one another.
  const jitter = (i: number) => ((i * 37) % 11) * 4;
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="h-auto w-full" role="img" aria-label="When each vote was cast, from the moment the review was published">
      <text x="0" y={AXIS - 30} className="fill-[var(--text-secondary)] text-[12px]">Up</text>
      <text x="0" y={AXIS + 34} className="fill-[var(--text-secondary)] text-[12px]">Down</text>
      <line x1="40" x2={W - 20} y1={AXIS} y2={AXIS} stroke="var(--base-ink-800)" strokeWidth="1" />
      {shown.map(([s, label]) => (
        <g key={label}>
          <line x1={x(s)} x2={x(s)} y1={AXIS - 4} y2={AXIS + 4} stroke="var(--base-ink-800)" />
          <text x={x(s)} y={H - 4} textAnchor="middle" className="fill-[var(--text-secondary)] text-[11px]">{label}</text>
        </g>
      ))}
      {voters.map((v, i) => (
        <circle
          key={v.voter_id}
          cx={x(v.seconds_after)}
          cy={v.vote === "up" ? AXIS - 14 - jitter(i) : AXIS + 14 + jitter(i) / 2}
          r={v.flagged ? 5 : 4}
          fill={v.flagged ? FLAG : v.vote === "up" ? UP : DOWN}
        >
          <title>{`${v.name}: ${v.vote === "up" ? "helpful" : "not helpful"}, ${after(v.seconds_after)} after publishing${v.flagged ? " (flagged)" : ""}`}</title>
        </circle>
      ))}
    </svg>
  );
}

export function VotesPanel({ data, failed }: { data: Investigation | null; failed: boolean }) {
  if (!data) return <Pending failed={failed} />;
  const flaggedFirst = data.voters.filter((v) => v.flagged && v.seconds_after <= 600);
  const all = data.gate_all;
  const rest = data.gate_without_flagged;
  const delta = rest.wilson_lower_bound - all.wilson_lower_bound;
  const share = data.flagged > 0 ? data.flagged_stage2_plus / data.flagged : 0;
  return (
    <div className="flex flex-col gap-4 p-6" data-testid="investigate-votes">
      <section className="rounded-[16px] border border-[var(--border-subtle)] p-4">
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <h3 className="text-[14px] font-medium">Vote timeline</h3>
          <p className="text-[12px] text-[var(--text-secondary)]">
            {data.votes_total} {data.votes_total === 1 ? "vote" : "votes"} · {data.first_10_min} in the first 10 minutes
            {data.typical_first_10_min !== null && data.typical_first_10_min !== undefined ? ` · typical is ${data.typical_first_10_min}` : ""}
          </p>
        </div>
        {flaggedFirst.length > 0 ? (
          <p className="mt-1 text-[12px] text-[var(--accent-primary)]">
            {flaggedFirst.slice(0, 3).map((v) => v.name).join(", ")}
            {flaggedFirst.length > 3 ? ` + ${flaggedFirst.length - 3} more` : ""} · flagged, in the first 10 minutes
          </p>
        ) : null}
        {data.votes_total === 0 ? (
          <p className="py-6 text-[13px] text-[var(--text-secondary)]">No votes yet.</p>
        ) : (
          <Timeline voters={data.voters} />
        )}
      </section>

      <section className="grid gap-4 rounded-[16px] border border-[var(--border-subtle)] p-4 md:grid-cols-[auto_1fr]">
        <div className="flex items-center gap-4">
          <span className="relative grid size-[112px] place-items-center">
            <svg viewBox="0 0 36 36" className="absolute inset-0 -rotate-90" aria-hidden>
              <circle cx="18" cy="18" r="15.5" fill="none" stroke="var(--surface-app)" strokeWidth="4" />
              {data.flagged > 0 ? (
                <>
                  <circle cx="18" cy="18" r="15.5" fill="none" stroke={FLAG} strokeWidth="4" strokeDasharray={`${share * 97.4} 97.4`} />
                  <circle cx="18" cy="18" r="15.5" fill="none" stroke={UP} strokeWidth="4" strokeDasharray={`${(1 - share) * 97.4} 97.4`} strokeDashoffset={-share * 97.4} />
                </>
              ) : null}
            </svg>
            <span className="relative text-center leading-tight">
              <span className={`block text-[24px] font-semibold ${data.flagged > 0 ? "text-[var(--accent-danger)]" : ""}`}>{data.flagged}</span>
              <span className="text-[11px] text-[var(--text-secondary)]">flagged</span>
            </span>
          </span>
          <ul className="flex flex-col gap-1 text-[12px]">
            <li className="flex items-center gap-2"><span aria-hidden className="size-2 rounded-full" style={{ background: FLAG }} />Stage 2+ (counts for the gate)<span className="ml-auto pl-3 font-medium">{data.flagged_stage2_plus}</span></li>
            <li className="flex items-center gap-2"><span aria-hidden className="size-2 rounded-full" style={{ background: UP }} />Stage 0–1<span className="ml-auto pl-3 font-medium">{data.flagged - data.flagged_stage2_plus}</span></li>
          </ul>
        </div>
        <div className="flex flex-col justify-center gap-2 border-t border-[var(--border-subtle)] pt-3 md:border-l md:border-t-0 md:pl-6 md:pt-0">
          <h3 className="text-[14px] font-medium">The earnings gate</h3>
          <div className="flex flex-wrap gap-6">
            <div>
              <p className="text-[12px] text-[var(--text-secondary)]">With every vote</p>
              <p className="text-[20px] font-semibold text-[var(--text-secondary)]" data-testid="wilson-all">{all.wilson_lower_bound.toFixed(2)}</p>
            </div>
            <div>
              <p className="text-[12px] text-[var(--text-secondary)]">Without flagged</p>
              <p className="text-[20px] font-semibold" data-testid="wilson-without">
                {rest.wilson_lower_bound.toFixed(2)}
                {data.flagged > 0 && delta !== 0 ? (
                  <span className="ml-2 rounded-full bg-[var(--status-high-bg)] px-2 py-[2px] text-[11px] font-medium text-[var(--accent-danger)]">
                    {delta > 0 ? "+" : "−"}{Math.abs(delta).toFixed(2)}
                  </span>
                ) : null}
              </p>
            </div>
          </div>
          <p className="text-[12px] text-[var(--text-secondary)]">
            The gate is {all.threshold.toFixed(2)} with {all.min_stage2_voters} Stage 2+ voters.{" "}
            {data.flagged === 0
              ? "No vote is flagged."
              : all.passes === rest.passes
                ? `It ${all.passes ? "passes" : "does not pass"} either way.`
                : all.passes
                  ? "It passes only because of the flagged votes."
                  : "It passes without the flagged votes."}{" "}
            Flagged: same network as another voter here, or up-voted at least 80% of this author&apos;s reviews.
          </p>
        </div>
      </section>
      <PlacesCard places={data.places ?? []} otherPlaces={data.places_other ?? 0} otherCount={data.places_other_count ?? 0} />
    </div>
  );
}

const SIGNAL_ICON = { same_network: LinkSimple, voting_circle: UsersThree, new_account: UserPlus, always_quick: Timer } as const;

function Strip({ history }: { history: (string | null)[] }) {
  return (
    <span className="flex gap-[3px]" aria-hidden>
      {history.map((h, i) => (
        <span
          key={i}
          className={`h-5 w-[5px] rounded-full ${h === "up" ? "bg-[var(--accent-success)]" : h === "down" ? "bg-[var(--accent-danger)]" : "bg-[var(--base-gray-200)]"}`}
        />
      ))}
    </span>
  );
}

/** 1 → "1.0", 1.5 → "1.5", 0.25 → "0.25": never rounded into a different weight. */
export const weightText = (w: number) => (Number.isInteger(Math.round(w * 1000) / 100) ? w.toFixed(1) : w.toFixed(2));

/** The short chip text per signal kind (Overlay/Review/Voters/All); the full label is the tooltip. */
const SIGNAL_SHORT: Record<string, string> = {
  same_network: "Same network",
  voting_circle: "Same circle",
  new_account: "New account",
  always_quick: "Always quick",
};

/**
 * Overlay/Review/Voters/All (Figma 8237:25697): every voter on the review, with
 * the weight their vote carries, when they voted after publishing, and the
 * signals behind a flag. Read-only, like the tabs it opens from.
 */
export function AllVotersDialog({ data, onClose }: { data: VoterData; onClose: () => void }) {
  const n = data.voters.length;
  return (
    <AdminModal title={`All voters (${n})`} width={760} onClose={onClose}>
      <div className="px-6 pb-4 pt-4">
        <div className="overflow-x-auto rounded-[16px] border border-[var(--border-subtle)]">
          <table className="w-full min-w-[640px] text-left text-[13px]" data-testid="all-voters">
            <thead className="bg-[var(--surface-app)] text-[12px] text-[var(--text-secondary)]">
              <tr>
                <th scope="col" className="h-10 px-3 font-normal">Voter</th>
                <th scope="col" className="px-3 font-normal">Weight</th>
                <th scope="col" className="px-3 font-normal">Voted</th>
                <th scope="col" className="px-3 font-normal">Signals</th>
                <th scope="col" className="px-3 font-normal"><span className="sr-only">Flagged</span></th>
              </tr>
            </thead>
            <tbody>
              {data.voters.map((v) => (
                <tr key={v.voter_id} data-testid="all-voter-row" className="border-t border-[var(--border-subtle)]">
                  <td className="px-3 py-2">
                    <span className="flex items-center gap-2">
                      <span aria-hidden className="grid size-7 shrink-0 place-items-center rounded-full bg-[var(--base-gray-200)] text-[12px] font-semibold text-[var(--text-secondary)]">
                        {(v.name.trim()[0] ?? "?").toUpperCase()}
                      </span>
                      <span className="flex min-w-0 flex-col">
                        <span className="truncate font-medium">{v.name}</span>
                        <span className="text-[12px] text-[var(--text-secondary)]">{v.level_name ?? `Stage ${v.stage}`}</span>
                      </span>
                    </span>
                  </td>
                  <td className="px-3 [font-variant-numeric:tabular-nums]">{v.weight != null ? weightText(v.weight) : "—"}</td>
                  <td className="px-3 text-[var(--text-secondary)]">
                    {v.vote === "up" ? "Helpful" : "Not helpful"} · {after(v.seconds_after)} after post
                  </td>
                  <td className="px-3 py-2">
                    {v.signals.length === 0 ? (
                      <span className="text-[12px] text-[var(--text-secondary)]">None</span>
                    ) : (
                      <span className="flex flex-wrap gap-1">
                        {v.signals.map((sig) => (
                          <span key={sig.label} title={sig.label} className="rounded-full bg-[var(--status-high-bg)] px-2 py-[3px] text-[11px] text-[var(--status-high-fg)]">
                            {SIGNAL_SHORT[sig.kind] ?? sig.label}
                          </span>
                        ))}
                      </span>
                    )}
                  </td>
                  <td className="px-3 text-right">
                    {v.flagged ? (
                      <span className="rounded-full bg-[var(--status-critical-bg)] px-2 py-[3px] text-[11px] text-[var(--status-critical-fg)]">Flagged</span>
                    ) : null}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="mt-3 text-[12px] text-[var(--text-secondary)]">
          {n} {n === 1 ? "voter" : "voters"} · {data.flagged} flagged. Weight is what the vote counts for in the score; a suspended account&apos;s vote counts 0.
        </p>
      </div>
      <div className="border-t border-[var(--border-subtle)] px-6 py-4">
        <button type="button" onClick={onClose} className="h-9 rounded-full bg-[var(--accent-primary)] px-5 text-[12px] text-white">
          Done
        </button>
      </div>
    </AdminModal>
  );
}

export function VotersPanel({
  data,
  failed,
  author,
  noun = "reviews",
}: {
  data: VoterData | null;
  failed: boolean;
  author: string;
  /** "reviews" or "answers": what the history strip covers. */
  noun?: string;
}) {
  const [all, setAll] = useState(false);
  if (!data) return <Pending failed={failed} />;
  const rows = data.voters.slice(0, 8);
  return (
    <div className="flex flex-col gap-3 p-6" data-testid="investigate-voters">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="text-[16px] font-medium">How each voter votes on {author}{noun === "answers" ? "’s answers" : ""}</h3>
        <span className="flex items-center gap-3 text-[12px] text-[var(--text-secondary)]">
          <span className="flex items-center gap-1"><span className="h-3 w-[5px] rounded-full bg-[var(--accent-success)]" />Helpful</span>
          <span className="flex items-center gap-1"><span className="h-3 w-[5px] rounded-full bg-[var(--accent-danger)]" />Not helpful</span>
          <span className="flex items-center gap-1"><span className="h-3 w-[5px] rounded-full bg-[var(--base-gray-200)]" />Didn&apos;t vote</span>
        </span>
      </div>
      {data.voters.length === 0 ? (
        <p className="py-6 text-[13px] text-[var(--text-secondary)]">No one has voted on this {noun === "answers" ? "answer" : "review"} yet.</p>
      ) : (
        <div className="overflow-x-auto rounded-[16px] border border-[var(--border-subtle)]">
          <table className="w-full min-w-[820px] text-left text-[13px]">
            <thead className="bg-[var(--surface-app)] text-[12px] text-[var(--text-secondary)]">
              <tr>
                <th scope="col" className="h-10 px-3 font-normal">Voter</th>
                <th scope="col" className="px-3 font-normal">This {noun === "answers" ? "answer" : "review"}</th>
                <th scope="col" className="px-3 font-normal">Last {data.history_size} {noun} by {author}</th>
                <th scope="col" className="px-3 font-normal">Agreement</th>
                <th scope="col" className="px-3 font-normal">Shared signals</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((v) => (
                <tr key={v.voter_id} data-testid="voter-row" data-flagged={v.flagged} className={`border-t border-[var(--border-subtle)] ${v.flagged ? "bg-[var(--status-high-bg)]" : ""}`}>
                  <td className="px-3 py-2">
                    <span className="block font-medium">{v.name}</span>
                    <span className="text-[12px] text-[var(--text-secondary)]">{v.level_name ?? `Stage ${v.stage}`}</span>
                  </td>
                  <td className="px-3 text-[var(--text-secondary)]">
                    {v.vote === "up" ? "Helpful" : "Not helpful"} · {after(v.seconds_after)}
                  </td>
                  <td className="px-3">
                    <Strip history={v.history} />
                    <span className="sr-only">
                      Helpful on {v.agreement} of {data.history_size} {noun} by {author}
                    </span>
                  </td>
                  <td className={`px-3 [font-variant-numeric:tabular-nums] ${v.flagged ? "font-medium text-[var(--accent-danger)]" : ""}`}>
                    {v.agreement} of {data.history_size}
                  </td>
                  <td className="px-3 py-2">
                    {v.signals.length === 0 ? (
                      <span className="text-[12px] text-[var(--text-secondary)]">No shared signals</span>
                    ) : (
                      <span className="flex flex-wrap gap-1">
                        {v.signals.map((s) => {
                          const Icon = SIGNAL_ICON[s.kind as keyof typeof SIGNAL_ICON] ?? Lightning;
                          return (
                            <span key={s.label} className="inline-flex items-center gap-1 rounded-full border border-[var(--accent-danger)] px-2 py-[2px] text-[11px] text-[var(--accent-danger)]">
                              <Icon size={12} aria-hidden /> {s.label}
                            </span>
                          );
                        })}
                      </span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <div className="flex items-center justify-between border-t border-[var(--border-subtle)] px-3 py-2 text-[12px] text-[var(--text-secondary)]">
            <span>
              Showing {rows.length} of {data.voters.length} {data.voters.length === 1 ? "voter" : "voters"} · {data.flagged} flagged
            </span>
            <button type="button" onClick={() => setAll(true)} className="text-[var(--accent-trust)] hover:underline">
              See all voters
            </button>
          </div>
        </div>
      )}
      {all ? <AllVotersDialog data={data} onClose={() => setAll(false)} /> : null}
    </div>
  );
}
