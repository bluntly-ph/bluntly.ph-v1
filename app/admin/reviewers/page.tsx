import type { Metadata } from "next";
import Link from "next/link";
import {
  ArrowsDownUp,
  Check,
  CheckCircle,
  MagnifyingGlass,
  Prohibit,
  SlidersHorizontal,
  WarningCircle,
} from "@phosphor-icons/react/dist/ssr";

import { TrustScoreCell } from "@/components/admin/people/TrustScore";
import { PersonCell } from "@/components/admin/queue/QueueCells";
import { Pagination } from "@/components/console/Pagination";
import { clampPage, pageSize } from "@/components/console/pagination-model";
import { getPeople, type PeopleSort, type PeopleStatus } from "@/lib/moderation";
import { TOP_SEARCH_STATES } from "@/components/ui/search-styles";
import { MENU_ITEM } from "@/components/console/fields";

export const metadata: Metadata = {
  title: "People — bluntly admin",
};

const VIEWS: { key: PeopleStatus; label: string }[] = [
  { key: "all", label: "All" },
  { key: "active", label: "Active" },
  { key: "investigating", label: "Under investigation" },
  { key: "suspended", label: "Suspended" },
];
const SORTS: [PeopleSort, string][] = [
  ["published", "Most published"],
  ["newest", "Newest"],
  ["oldest", "Oldest"],
];
const STAGES = ["Newcomer", "Contributor", "Verified Buyer", "Established", "Trusted", "Community Expert"];
const MENU = "absolute right-0 top-[calc(100%+6px)] z-30 rounded-[16px] border border-[var(--border-subtle)] bg-[var(--surface-card)] shadow-[var(--shadow-modal)]";
const ICON = "grid size-8 cursor-pointer list-none place-items-center rounded-full hover:bg-[var(--surface-app)] group-open:bg-[var(--surface-app)] [&::-webkit-details-marker]:hidden";

/**
 * People (Figma Screen/Admin/People 7998:11693; meeting 2026-10-02, 12:50).
 *
 * Members only: administrators and claimed sellers are left out, as the
 * meeting asked ("dapat walang admin dito… wala dapat seller din"); role
 * changes stay under the Super Admin's Users tab. Three standings, which the
 * meeting defined by voting power: Active (full), Under investigation (votes
 * count half) and Suspended (no voting power). A row opens the member's
 * investigation.
 *
 * Paged with the console Pagination (10 a page by default, as drawn): the
 * owner found the whole member list on one page (2026-10-03) — production's
 * members fit inside the old 25-row page, so no pager ever showed. Status,
 * search, sort and stage stay in the URL as the page changes; changing any of
 * them starts again at page 1.
 */
export default async function PeoplePage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const sp = await searchParams;
  const one = (v: string | string[] | undefined) => (Array.isArray(v) ? v[0] : v) ?? "";
  const status = (VIEWS.some((v) => v.key === one(sp.status)) ? one(sp.status) : "all") as PeopleStatus;
  const q = one(sp.q).slice(0, 120);
  const size = pageSize(one(sp.size));
  const requested = Math.max(1, Number.parseInt(one(sp.page), 10) || 1);
  const sort = (SORTS.some(([k]) => k === one(sp.sort)) ? one(sp.sort) : "published") as PeopleSort;
  const stageRaw = Number.parseInt(one(sp.stage), 10);
  const stage = stageRaw >= 0 && stageRaw <= 5 ? stageRaw : null;
  let page = await getPeople({ status, q, limit: size, offset: (requested - 1) * size, sort, stage });
  // A page past the end (the list shrank since the link was made) shows the last one.
  const current = page ? clampPage(requested, page.total, size) : 1;
  if (page && current !== requested) {
    page = await getPeople({ status, q, limit: size, offset: (current - 1) * size, sort, stage });
  }

  // Everything but the page: the pager keeps these, and changing one of them
  // (below) starts again at page 1.
  type Changes = { status?: PeopleStatus; sort?: PeopleSort; stage?: number | null; q?: string };
  const query = (changes: Changes = {}) => {
    const s = changes.status ?? status;
    const text = changes.q ?? q;
    const so = changes.sort ?? sort;
    const st = "stage" in changes ? changes.stage : stage;
    return {
      status: s !== "all" ? s : undefined,
      q: text || undefined,
      sort: so !== "published" ? so : undefined,
      stage: st !== null && st !== undefined ? String(st) : undefined,
      size: size !== pageSize(undefined) ? String(size) : undefined,
    };
  };
  const href = (changes: Changes) => {
    const params = new URLSearchParams();
    for (const [k, v] of Object.entries(query(changes))) if (v) params.set(k, v);
    const qs = params.toString();
    return qs ? `/admin/reviewers?${qs}` : "/admin/reviewers";
  };

  if (!page) {
    return (
      <p role="alert" className="text-[14px] text-[var(--text-secondary)]">
        People could not be loaded. Nothing has changed; try again in a moment.
      </p>
    );
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center gap-2">
        <nav aria-label="Standing" className="flex flex-wrap gap-[2px] rounded-[10px] bg-[var(--surface-app)] p-[3px]">
          {VIEWS.map((v) => (
            <Link
              key={v.key}
              href={href({ status: v.key })}
              aria-current={status === v.key ? "page" : undefined}
              className={`flex items-center gap-[6px] rounded-[8px] px-3 py-[5px] leading-none ${
                status === v.key
                  ? "bg-[var(--surface-card)] shadow-[var(--shadow-segment)]"
                  : "text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
              }`}
            >
              <span className="text-[14px] font-medium">{v.label}</span>
              <span className="text-[12px] text-[var(--text-secondary)]">
                {(page.counts?.[v.key] ?? 0).toLocaleString("en-PH")}
              </span>
            </Link>
          ))}
        </nav>
        <span className="flex-1" />
        <details className="group relative">
          <summary aria-label="Sort" className={ICON}>
            <ArrowsDownUp size={18} />
          </summary>
          <div role="menu" aria-label="Sort" className={`${MENU} w-[220px] p-[6px]`}>
            {SORTS.map(([k, label]) => (
              <Link
                key={k}
                role="menuitemradio"
                aria-checked={sort === k}
                href={href({ sort: k })}
                className={MENU_ITEM}
              >
                {label}
                {sort === k ? <Check size={16} aria-hidden /> : null}
              </Link>
            ))}
          </div>
        </details>
        <details className="group relative">
          <summary aria-label={stage !== null ? "Filter (1 on)" : "Filter"} className={`${ICON} relative`}>
            <SlidersHorizontal size={18} />
            {stage !== null ? <span className="absolute right-1 top-1 size-[6px] rounded-full bg-[var(--accent-primary)]" aria-hidden /> : null}
          </summary>
          <div role="group" aria-label="Filter" className={`${MENU} flex w-[340px] flex-col gap-3 p-4`}>
            <p className="text-[12px] text-[var(--chart-honesty-fund)]">Stage</p>
            <div className="flex flex-wrap gap-2">
              {STAGES.map((label, i) => (
                <Link
                  key={label}
                  href={href({ stage: stage === i ? null : i })}
                  aria-pressed={stage === i}
                  className={`flex h-8 items-center gap-[6px] rounded-full border px-3 text-[14px] ${stage === i ? "border-[var(--accent-primary)] text-[var(--accent-primary)]" : "border-[var(--border-subtle)]"}`}
                >
                  {label}
                  <span className="text-[12px] text-[var(--text-secondary)]">{(page?.stages?.[String(i)] ?? 0).toLocaleString("en-PH")}</span>
                </Link>
              ))}
            </div>
            <Link href={href({ stage: null })} className="self-start border-t border-[var(--border-subtle)] pt-3 text-[14px] text-[var(--chart-honesty-fund)]">
              Clear all
            </Link>
          </div>
        </details>
        <details className="group relative" open={q ? true : undefined}>
          <summary aria-label={q ? "Search (on)" : "Search"} className={`${ICON} relative`}>
            <MagnifyingGlass size={18} />
            {q ? <span className="absolute right-1 top-1 size-[6px] rounded-full bg-[var(--accent-primary)]" aria-hidden /> : null}
          </summary>
          <form action="/admin/reviewers" method="get" role="search" className={`${MENU} flex w-[320px] items-center gap-2 p-2`}>
            {status !== "all" ? <input type="hidden" name="status" value={status} /> : null}
            {sort !== "published" ? <input type="hidden" name="sort" value={sort} /> : null}
            {stage !== null ? <input type="hidden" name="stage" value={stage} /> : null}
            {size !== pageSize(undefined) ? <input type="hidden" name="size" value={size} /> : null}
            <label htmlFor="people-q" className="sr-only">Search people</label>
            <input
              id="people-q"
              name="q"
              defaultValue={q}
              placeholder="Name, @username or USR reference"
              className={`h-9 min-w-0 flex-1 rounded-[10px] px-3 text-[12px] caret-[var(--accent-primary)] outline-none placeholder:text-[var(--text-secondary)] ${TOP_SEARCH_STATES}`}
            />
            <button type="submit" className="h-9 rounded-full border border-[var(--text-primary)] px-3 text-[12px]">
              Search
            </button>
            {q ? (
              <Link href={href({ q: "" })} className="text-[12px] text-[var(--text-secondary)] underline-offset-4 hover:underline">
                Clear
              </Link>
            ) : null}
          </form>
        </details>
      </div>

      <div className="overflow-x-auto rounded-[16px] border border-[var(--border-subtle)]">
        <table className="w-full min-w-[1000px] border-collapse text-left text-[14px]">
          <caption className="sr-only">Members</caption>
          <thead className="bg-[var(--surface-app)] text-[12px] text-[var(--text-secondary)]">
            <tr>
              {/* Figma Screen/Admin/People (7998:11693) plus the owner's Trust
                  Score column (2026-10-05), between Role and Published. */}
              {["Person", "Account", "Role", "Trust Score", "Published", "Status", "Joined", "Action"].map((h) => (
                <th key={h} scope="col" className="h-10 px-3 font-normal">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {page.rows.length === 0 ? (
              <tr>
                <td colSpan={8} className="border-t border-[var(--border-subtle)] px-3 py-10 text-center text-[var(--text-secondary)]">
                  {q ? "No member matches that search." : "No members with this standing."}
                </td>
              </tr>
            ) : (
              page.rows.map((p) => {
                const name = p.display_name ?? p.username ?? "Member";
                return (
                  <tr
                    key={p.id}
                    className={`group border-t border-[var(--border-subtle)] hover:bg-[var(--surface-app)] ${p.is_suspended ? "text-[var(--text-secondary)]" : ""}`}
                  >
                    <td className="px-3 py-[10px]">
                      <PersonCell name={name} stage={p.trust_stage} levelName={p.trust_level_name} href={`/admin/people/${p.id}`} avatarUrl={p.avatar_url ?? null} />
                    </td>
                    <td className="px-3">
                      <span className="flex flex-col gap-1 leading-4 [&>:first-child]:leading-5">
                        <span>{p.username ? `@${p.username}` : "—"}</span>
                        <span className="text-[12px] text-[var(--text-secondary)]">{p.user_ref ?? ""}</span>
                      </span>
                    </td>
                    <td className="px-3">Reviewer</td>
                    <td className="px-3">
                      {/* The backend's EFFECTIVE score (override if set, else
                          computed): the frontend never derives one. */}
                      <TrustScoreCell score={p.reputation_score} computed={p.computed_score ?? null} overridden={Boolean(p.is_score_overridden)} />
                    </td>
                    <td className="px-3">{p.published_reviews}</td>
                    <td className="px-3">
                      <span className="inline-flex items-center gap-1.5">
                        {p.is_suspended ? (
                          <><Prohibit size={14} className="text-[var(--text-secondary)]" /> Suspended</>
                        ) : p.is_under_investigation ? (
                          <><WarningCircle size={14} weight="fill" className="text-[var(--accent-primary)]" /> Investigating</>
                        ) : (
                          <><CheckCircle size={14} weight="fill" className="text-[var(--accent-success)]" /> Active</>
                        )}
                      </span>
                    </td>
                    <td className="px-3 text-[var(--text-secondary)]">
                      {new Date(p.joined).toLocaleDateString("en-PH", { month: "short", year: "numeric" })}
                    </td>
                    <td className="px-3">
                      <Link
                        href={`/admin/people/${p.id}`}
                        className="rounded-full border border-[var(--border-subtle)] bg-[var(--surface-card)] px-3 py-1 text-[12px] opacity-0 hover:border-[var(--text-secondary)] focus:opacity-100 group-hover:opacity-100 max-md:opacity-100"
                      >
                        Open
                      </Link>
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>

      <Pagination page={current} size={size} total={page.total} basePath="/admin/reviewers" query={query()} label="People pages" />
    </div>
  );
}
