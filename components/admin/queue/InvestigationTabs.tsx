"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { CheckCircle, Info, ShieldCheck, WarningCircle } from "@phosphor-icons/react";

import { ImageViewer } from "@/components/console/ImageViewer";

/**
 * The Author and Originality tabs of an investigation, shared by reviews and
 * answers (Figma Overlay/Review/Investigate/Author 8112:17871, /Originality
 * 8112:17611; Overlay/Answer/Investigate/Author 8129:19219, /Originality
 * 8129:19014), and "Where votes came from" for reviews (8237:26485).
 *
 * Everything is read from GET /admin/{reviews|answers}/{id}/investigation/…;
 * a part the platform does not record is said to be missing, never drawn
 * with invented figures:
 *  - photos are not compared (no image fingerprint is stored);
 *  - marketplace Q&A and the web are not searched for copied text;
 *  - the receipt checks (product matches, bought before posting, editing
 *    traces) are not run by anything;
 *  - answers record no place for a vote, and have no gate or reward.
 */

type Schemas = import("@/lib/api-types").components["schemas"];
export type AuthorData = Schemas["AuthorInvestigationOut"];
export type OriginalityData = Schemas["OriginalityOut"];
type Kind = "reviews" | "answers";

const CARD = "rounded-[16px] border border-[var(--border-subtle)] p-4";
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const month = (key: string) => MONTHS[Number(key.slice(5, 7)) - 1] ?? key;
const pct = (v: number) => `${Math.round(v * 100)}%`;

function useJson<T>(url: string): { data: T | null; failed: boolean } {
  const [state, setState] = useState<{ url: string; data: T | null; failed: boolean }>({ url: "", data: null, failed: false });
  useEffect(() => {
    let live = true;
    fetch(url, { cache: "no-store" })
      .then((r) => (r.ok ? (r.json() as Promise<T>) : Promise.reject(new Error(String(r.status)))))
      .then((data) => live && setState({ url, data, failed: false }))
      .catch(() => live && setState({ url, data: null, failed: true }));
    return () => {
      live = false;
    };
  }, [url]);
  return state.url === url ? state : { data: null, failed: false };
}

function Pending({ failed, what }: { failed: boolean; what: string }) {
  return (
    <p role={failed ? "alert" : "status"} className="p-6 text-[14px] text-[var(--text-secondary)]">
      {failed ? `${what} could not be loaded. This is not an empty result: nothing is known right now.` : `Loading ${what.toLowerCase()}…`}
    </p>
  );
}

const STATUS_TONE: Record<string, string> = {
  upheld: "text-[var(--accent-danger)]",
  open: "text-[var(--accent-primary)]",
  escalated: "text-[var(--accent-primary)]",
  dismissed: "text-[var(--text-secondary)]",
  restored: "text-[var(--text-secondary)]",
};

export function AuthorPanel({ kind, id }: { kind: Kind; id: string }) {
  const { data: a, failed } = useJson<AuthorData>(`/api/bff/api/v1/admin/${kind}/${id}/investigation/author`);
  if (!a) return <Pending failed={failed} what="The author" />;
  const noun = kind === "reviews" ? "reviews" : "answers";
  const maxMonth = Math.max(1, ...a.per_month.map(([, n]) => n));
  const upheld = a.reports.filter((r) => r.status === "upheld").length;
  return (
    <div className="grid gap-4 p-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]" data-testid="investigate-author">
      <div className="flex flex-col gap-4">
        <section className={`${CARD} flex flex-wrap items-center gap-4`}>
          <span className="grid size-14 shrink-0 place-items-center rounded-full bg-[var(--surface-app)] text-[20px] font-semibold" aria-hidden>
            {a.person.name.slice(0, 1).toUpperCase()}
          </span>
          <span className="flex min-w-0 flex-1 flex-col gap-1">
            <span className="truncate text-[16px] font-semibold">{a.person.name}</span>
            <span className="text-[12px] text-[var(--text-secondary)]">{a.person.level_name ?? `Stage ${a.person.stage}`}</span>
          </span>
          <span className="inline-flex items-center gap-1 text-[16px] font-medium" title="Trust score, 0 to 100">
            <ShieldCheck size={18} weight="fill" className="text-[var(--accent-trust)]" aria-hidden />
            {Math.round(a.trust_score)} <span className="text-[12px] font-normal text-[var(--text-secondary)]">trust</span>
          </span>
          <Link href={`/admin/people/${a.person.id}`} className="h-8 rounded-full border border-[var(--text-primary)] px-3 py-[7px] text-[12px] leading-none">
            Open person
          </Link>
          <dl className="grid w-full grid-cols-4 gap-3 border-t border-[var(--border-subtle)] pt-3">
            {(
              [
                ["Joined", new Date(a.joined).toLocaleDateString("en-GB", { month: "short", year: "numeric", timeZone: "Asia/Manila" })],
                ["Reviews", String(a.reviews)],
                ["Answers", String(a.answers)],
                ["Earned", a.earned != null ? `₱${Number(a.earned).toLocaleString("en-PH", { maximumFractionDigits: 0 })}` : "—"],
              ] as const
            ).map(([k, v]) => (
              <div key={k}>
                <dt className="text-[12px] text-[var(--text-secondary)]">{k}</dt>
                <dd className="text-[14px] font-medium" suppressHydrationWarning>
                  {v}
                </dd>
              </div>
            ))}
          </dl>
        </section>

        <section className={CARD} aria-label="Where their helpful votes come from">
          <h3 className="text-[14px] font-medium">Where their helpful votes come from</h3>
          <p className="mt-1 text-[12px] text-[var(--text-secondary)]">
            All {a.items} {noun} · {a.helpful_votes.toLocaleString("en-PH")} helpful votes
          </p>
          {a.helpful_votes === 0 ? (
            <p className="mt-3 text-[13px] text-[var(--text-secondary)]">No helpful votes yet.</p>
          ) : (
            <ul className="mt-3 flex flex-col gap-2">
              {[...a.sources.map((s) => [s.person.name, s.share] as const), [`Everyone else (${a.others_people} ${a.others_people === 1 ? "person" : "people"})`, a.others_share] as const].map(([name, share], i) => (
                <li key={`${name}-${i}`} className="flex flex-col gap-1">
                  <span className="flex justify-between text-[13px]">
                    <span>{name}</span>
                    <span className="[font-variant-numeric:tabular-nums]">{pct(share)}</span>
                  </span>
                  <span className="h-[5px] rounded-full bg-[var(--surface-app)]" aria-hidden>
                    <span className={`block h-full rounded-full ${i < a.sources.length ? "bg-[var(--accent-primary)]" : "bg-[var(--base-gray-400)]"}`} style={{ width: pct(share) }} />
                  </span>
                </li>
              ))}
            </ul>
          )}
          {a.sources.length > 0 && a.helpful_votes > 0 ? (
            <p className={`mt-3 text-[12px] ${a.top_share >= 0.3 ? "text-[var(--accent-danger)]" : "text-[var(--text-secondary)]"}`}>
              {pct(a.top_share)} from {a.sources.length === 1 ? "one account" : `just ${a.sources.length} accounts`}.
            </p>
          ) : null}
        </section>

        <section className={CARD} aria-label={`${kind === "reviews" ? "Reviews" : "Answers"} per month`}>
          <h3 className="text-[14px] font-medium">{kind === "reviews" ? "Reviews" : "Answers"} per month</h3>
          <div className="mt-3 flex h-24 items-end gap-1" role="img" aria-label={`${noun} published each month, last 12 months`}>
            {a.per_month.map(([key, n]) => (
              <span key={key} className="flex h-full flex-1 flex-col items-center justify-end gap-1" title={`${month(key)}: ${n}`}>
                <span className="w-full rounded-t-[4px] bg-[var(--accent-primary)]" style={{ height: `${(n / maxMonth) * 100}%`, minHeight: n ? 3 : 0 }} />
              </span>
            ))}
          </div>
          <div className="mt-1 flex justify-between text-[11px] text-[var(--text-secondary)]">
            <span>{a.per_month.length ? month(a.per_month[0][0]) : ""}</span>
            <span>{a.per_month.length ? month(a.per_month[a.per_month.length - 1][0]) : ""}</span>
          </div>
        </section>
      </div>

      <div className="flex flex-col gap-4">
        <section className={CARD} aria-label="Helpful score on their latest">
          <div className="flex items-baseline justify-between gap-2">
            <h3 className="text-[14px] font-medium">Helpful score on their last {a.scores.length} {noun}</h3>
            {a.gate != null ? (
              <span className="text-[12px] text-[var(--text-secondary)]">
                {a.passing} of {a.items} pass
              </span>
            ) : null}
          </div>
          <ScoreStrip scores={a.scores} gate={a.gate ?? null} />
          <p className="mt-2 text-[12px] text-[var(--text-secondary)]">
            {a.gate != null ? `The earnings gate is ${a.gate.toFixed(2)}.` : "Answers have no gate: the score only orders them under a question."}
          </p>
        </section>

        <section className={CARD} aria-label="Report history">
          <div className="flex items-baseline justify-between gap-2">
            <h3 className="text-[14px] font-medium">Report history</h3>
            <span className="text-[12px] text-[var(--text-secondary)]">
              {a.reports.length} {a.reports.length === 1 ? "report" : "reports"} · {upheld} upheld
            </span>
          </div>
          {a.reports.length === 0 ? (
            <p className="mt-3 text-[13px] text-[var(--text-secondary)]">No reports against them or their content.</p>
          ) : (
            <ul className="mt-2 flex flex-col">
              {a.reports.slice(0, 6).map((r, i) => (
                <li key={i} className="flex items-center justify-between gap-3 border-t border-[var(--border-subtle)] py-2 text-[13px] first:border-t-0">
                  <span suppressHydrationWarning>
                    {new Date(r.at).toLocaleDateString("en-GB", { day: "numeric", month: "short", timeZone: "Asia/Manila" })} · {r.reason ? r.reason.replaceAll("_", " ") : "No reason given"}
                  </span>
                  <span className={`capitalize ${STATUS_TONE[r.status] ?? ""}`}>{r.status}</span>
                </li>
              ))}
            </ul>
          )}
        </section>

        <section className={CARD} aria-label="Voting circle">
          <h3 className="text-[14px] font-medium">Voting circle</h3>
          <p className="mt-1 text-[12px] text-[var(--text-secondary)]">People who up-voted at least 80% of their {noun} (5 or more).</p>
          {a.circle.length === 0 ? (
            <p className="mt-3 text-[13px] text-[var(--text-secondary)]">No one.</p>
          ) : (
            <ul className="mt-2 flex flex-col">
              {a.circle.map((c) => (
                <li key={c.person.id} className="flex items-center gap-3 border-t border-[var(--border-subtle)] py-2 first:border-t-0">
                  <span aria-hidden className="grid size-7 place-items-center rounded-full bg-[var(--base-gray-200)] text-[12px] font-semibold text-[var(--text-secondary)]">
                    {c.person.name.slice(0, 1).toUpperCase()}
                  </span>
                  <span className="flex min-w-0 flex-1 flex-col">
                    <span className="truncate text-[13px] font-medium">{c.person.name}</span>
                    <span className="text-[12px] text-[var(--text-secondary)]">{c.person.level_name ?? `Stage ${c.person.stage}`}</span>
                  </span>
                  <span className="text-right text-[12px] text-[var(--accent-danger)]">
                    {c.covered} of {a.items} {noun}, {c.back} back
                  </span>
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>
    </div>
  );
}

function ScoreStrip({ scores, gate }: { scores: AuthorData["scores"]; gate: number | null }) {
  const W = 420;
  const H = 110;
  const lo = 0.3;
  const hi = 1;
  const y = (v: number) => 8 + ((hi - Math.max(lo, Math.min(hi, v))) / (hi - lo)) * (H - 24);
  const x = (i: number) => 16 + (i * (W - 32)) / Math.max(1, scores.length - 1);
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="mt-3 h-auto w-full" role="img" aria-label="Helpful score of each, oldest first">
      {gate != null ? (
        <g>
          <line x1={8} x2={W - 8} y1={y(gate)} y2={y(gate)} stroke="var(--accent-danger)" strokeDasharray="4 4" />
          <text x={W - 8} y={y(gate) - 4} textAnchor="end" fontSize={11} fill="var(--accent-danger)">
            gate {gate.toFixed(2)}
          </text>
        </g>
      ) : null}
      {scores.map((s, i) =>
        s.score != null ? (
          <circle key={s.id} cx={x(i)} cy={y(s.score)} r={s.current ? 6 : 4} fill={s.current ? "var(--accent-primary)" : "var(--base-gray-400)"}>
            <title>{`${s.score.toFixed(2)}${s.current ? " (this one)" : ""}`}</title>
          </circle>
        ) : null,
      )}
      <text x={8} y={H - 2} fontSize={11} fill="var(--text-secondary)">
        older
      </text>
      <text x={W - 8} y={H - 2} textAnchor="end" fontSize={11} fill="var(--text-secondary)">
        this one
      </text>
    </svg>
  );
}

export function OriginalityPanel({ kind, id }: { kind: Kind; id: string }) {
  const { data: o, failed } = useJson<OriginalityData>(`/api/bff/api/v1/admin/${kind}/${id}/investigation/originality`);
  const [receipt, setReceipt] = useState<{ src: string | null; error: string | null } | null>(null);
  if (!o) return <Pending failed={failed} what="The originality check" />;
  const b = o.best;
  async function openReceipt() {
    setReceipt({ src: null, error: null });
    const res = await fetch(`/api/bff/api/v1/reviews/${id}/receipt`, { cache: "no-store" }).catch(() => null);
    const url = res?.ok ? ((await res.json()) as { url?: string }).url : null;
    setReceipt(url ? { src: url, error: null } : { src: null, error: "The receipt couldn’t be opened. It may no longer be stored." });
  }
  return (
    <div className="flex flex-col gap-4 p-6" data-testid="investigate-originality">
      <section className={CARD} aria-label="Text">
        <h3 className="text-[14px] font-medium">Text</h3>
        <p className="mt-1 text-[12px] text-[var(--text-secondary)]">
          Compared with {o.compared} earlier Bluntly {o.compared === 1 ? "text" : "texts"} nearby (the same {kind === "reviews" ? "product and author" : "question and responder"}). Marketplace Q&amp;A and the web are not searched.
        </p>
        {!o.meaningful ? (
          <p className="mt-3 text-[13px] text-[var(--text-secondary)]">Too short to compare.</p>
        ) : !b ? (
          <p className="mt-3 flex items-center gap-2 text-[13px]">
            <CheckCircle size={16} weight="fill" className="text-[var(--accent-success)]" aria-hidden /> Nothing earlier to compare with.
          </p>
        ) : (
          <div className="mt-3 flex flex-col gap-2">
            <p className="flex items-center gap-2 text-[14px]">
              {b.flagged ? (
                <WarningCircle size={16} weight="fill" className="text-[var(--accent-danger)]" aria-hidden />
              ) : (
                <CheckCircle size={16} weight="fill" className="text-[var(--accent-success)]" aria-hidden />
              )}
              <span className="font-medium">{b.flagged ? "Matches earlier text" : "Text mostly original"}</span>
              <span className="text-[var(--text-secondary)]">· closest {pct(b.score)}</span>
            </p>
            <span className="h-[6px] rounded-full bg-[var(--surface-app)]" aria-hidden>
              <span className={`block h-full rounded-full ${b.flagged ? "bg-[var(--accent-danger)]" : "bg-[var(--base-gray-400)]"}`} style={{ width: pct(b.score) }} />
            </span>
            <p className="text-[13px] text-[var(--text-secondary)]">
              Closest:{" "}
              {b.href ? (
                <Link href={b.href} target="_blank" className="text-[var(--accent-trust)] hover:underline">
                  {b.label}
                </Link>
              ) : (
                b.label
              )}
              . {b.reason}
            </p>
          </div>
        )}
      </section>

      <section className={CARD} aria-label="Photos">
        <h3 className="text-[14px] font-medium">Photos</h3>
        <p className="mt-2 flex items-start gap-2 text-[13px] text-[var(--text-secondary)]">
          <Info size={16} className="mt-px shrink-0" aria-hidden />
          {kind === "answers"
            ? "Answers hold text only."
            : `${o.has_photo ? "This review has a photo. " : "This review has no photo. "}Bluntly does not compare photos, so nothing here says whether one was used before.`}
        </p>
      </section>

      {kind === "reviews" ? (
        <section className={CARD} aria-label="Proof of purchase">
          <h3 className="text-[14px] font-medium">Proof of purchase</h3>
          {o.has_receipt ? (
            <div className="mt-2 flex flex-wrap items-center gap-3">
              <span className="text-[13px]">A receipt was submitted. Opening it is recorded in the Activity log.</span>
              <button type="button" onClick={() => void openReceipt()} className="h-8 rounded-full border border-[var(--text-primary)] px-3 text-[12px]">
                View full image
              </button>
            </div>
          ) : (
            <p className="mt-2 text-[13px] text-[var(--text-secondary)]">No receipt was submitted.</p>
          )}
          <p className="mt-2 text-[12px] text-[var(--text-secondary)]">Receipts are read by a moderator; nothing checks the product, date or editing automatically.</p>
          {receipt ? (
            <ImageViewer
              title="Proof of purchase"
              src={receipt.src}
              alt="The reviewer's proof of purchase"
              meta="Private · this view is recorded in the Activity log"
              error={receipt.error}
              onClose={() => setReceipt(null)}
            />
          ) : null}
        </section>
      ) : null}
    </div>
  );
}

/** "Where votes came from" (reviews): first-time votes by place, Count or Rate. */
export function PlacesCard({ places, otherPlaces, otherCount }: { places: { place: string; votes: number }[]; otherPlaces: number; otherCount: number }) {
  const [mode, setMode] = useState<"count" | "rate">("count");
  const rows = [...places.map((p) => [p.place, p.votes] as const), ...(otherPlaces ? [[`Other ${otherPlaces} ${otherPlaces === 1 ? "place" : "places"}`, otherCount] as const] : [])];
  const total = rows.reduce((s, [, n]) => s + n, 0);
  const max = Math.max(1, ...rows.map(([, n]) => n));
  return (
    <section className="rounded-[16px] border border-[var(--border-subtle)] p-4" aria-label="Where votes came from" data-testid="vote-places">
      <div className="flex items-center justify-between gap-2">
        <h3 className="text-[14px] font-medium">Where votes came from</h3>
        <div role="tablist" aria-label="Show as" className="flex gap-[2px] rounded-[10px] bg-[var(--surface-app)] p-[3px]">
          {(
            [
              ["count", "Count"],
              ["rate", "Rate"],
            ] as const
          ).map(([k, label]) => (
            <button
              key={k}
              type="button"
              role="tab"
              aria-selected={mode === k}
              onClick={() => setMode(k)}
              className={`rounded-[8px] px-3 py-[4px] text-[13px] ${mode === k ? "bg-[var(--surface-card)] shadow-[var(--shadow-segment)]" : "text-[var(--text-secondary)]"}`}
            >
              {label}
            </button>
          ))}
        </div>
      </div>
      {total === 0 ? (
        <p className="mt-3 text-[13px] text-[var(--text-secondary)]">No place was recorded for this review&apos;s votes (places are kept per hour for first-time votes, with no voter).</p>
      ) : (
        <>
          <ul className="mt-3 flex flex-col gap-2">
            {rows.map(([place, n], i) => (
              <li key={place} className="grid grid-cols-[minmax(0,10rem)_1fr_3rem] items-center gap-3 text-[13px]">
                <span className="truncate">{place}</span>
                <span className="h-[6px] rounded-full bg-[var(--surface-app)]" aria-hidden>
                  <span className={`block h-full rounded-full ${i === 0 ? "bg-[var(--accent-primary)]" : "bg-[var(--base-gray-400)]"}`} style={{ width: `${(n / max) * 100}%` }} />
                </span>
                <span className="text-right [font-variant-numeric:tabular-nums]">{mode === "count" ? n : pct(n / total)}</span>
              </li>
            ))}
          </ul>
          <p className="mt-3 text-[12px] text-[var(--text-secondary)]">First-time votes per place, as the network edge reported it. Places carry no voter, so flagged votes cannot be placed.</p>
        </>
      )}
    </section>
  );
}
