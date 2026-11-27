import Image from "next/image";
import Link from "next/link";
import { DotOutline } from "@phosphor-icons/react/dist/ssr";

import type { Person } from "@/lib/people";

/** A stable hue from the handle, for the lettered avatar (as review cards do). */
function hue(handle: string): number {
  let h = 0;
  for (const ch of handle) h = (h * 31 + ch.charCodeAt(0)) % 360;
  return h;
}

/**
 * One member on the People tab of /search (owner, 2026-09-28): who they are
 * and how much they have written, opening their public profile.
 */
export function PersonResultRow({ person }: { person: Person }) {
  const name = person.display_name?.trim() || person.username;
  return (
    <li className="border-b border-[var(--line-hairline-10)]" data-testid="person-result">
      <Link
        href={`/u/${encodeURIComponent(person.username)}`}
        className="flex items-center gap-4 px-4 py-4 text-[var(--text-primary)] no-underline transition-colors hover:bg-[var(--line-hairline-10)] focus-visible:outline focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-[var(--accent-primary)] md:px-2"
      >
        {person.avatar_url ? (
          <Image
            src={person.avatar_url}
            alt=""
            width={48}
            height={48}
            className="h-12 w-12 shrink-0 rounded-full object-cover"
          />
        ) : (
          <span
            aria-hidden="true"
            className="grid h-12 w-12 shrink-0 place-items-center rounded-full text-[18px] font-semibold uppercase text-white"
            style={{ background: `hsl(${hue(person.username)} 55% 55%)` }}
          >
            {name.slice(0, 1)}
          </span>
        )}
        <span className="min-w-0 flex-1">
          <h2 className="truncate text-[14px] font-bold leading-[21px]">{name}</h2>
          <span className="flex flex-wrap items-center gap-[3px] text-[12px] font-light leading-[18px] text-[var(--text-secondary)]">
            @{person.username}
            <DotOutline size={12} aria-hidden="true" className="shrink-0 text-[var(--base-gray-400)]" />
            {person.review_count} {person.review_count === 1 ? "review" : "reviews"}
            {person.trust_level_name ? (
              <>
                <DotOutline size={12} aria-hidden="true" className="shrink-0 text-[var(--base-gray-400)]" />
                {person.trust_level_name}
              </>
            ) : null}
            {person.is_claimed_seller ? (
              <>
                <DotOutline size={12} aria-hidden="true" className="shrink-0 text-[var(--base-gray-400)]" />
                Store owner
              </>
            ) : null}
          </span>
        </span>
      </Link>
    </li>
  );
}
