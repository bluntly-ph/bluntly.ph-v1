import Link from "next/link";
import { MagnifyingGlass, PencilSimpleLine } from "@phosphor-icons/react/dist/ssr";

import { SearchAutocomplete } from "@/components/search/SearchAutocomplete";
import { Logo } from "@/components/ui/Logo";
import { Bar, Circle, Pill } from "@/components/ui/Skeleton";
import { AccountSwitchNotice } from "@/components/site/AccountSwitchNotice";
import { ProfileNavPanel } from "@/components/site/ProfileNavPanel";
import { SessionAccountSwitchNotice, SessionProfileNav } from "@/components/site/SessionAccount";
import { SEARCH_FIELD_STATES } from "@/components/ui/search-styles";

export type HeaderUser = {
  username: string | null;
  avatarUrl: string | null;
  /** Decides whether the menu offers Moderate; the route still guards itself. */
  role?: string | null;
} | null;

/**
 * The public site header — orange wordmark, search, and either the signed-in
 * avatar or a log-in affordance. Mobile is the frame (wordmark + search icon +
 * avatar); at `lg` it widens into a real top bar with an inline search field and
 * a "Write a review" call to action.
 *
 * `showSearch={false}` drops the phone's search icon. The search page passes it:
 * its frames draw the wordmark and avatar only, because the page itself is the
 * search.
 *
 * `account="session"` is for static pages (components/site/StaticPageShell):
 * the server does not know the reader there, so the account corner finds out
 * in the browser (components/site/SessionAccount) and `user` is ignored.
 */
export function SiteHeader({
  user,
  showSearch = true,
  account = "server",
}: {
  user: HeaderUser;
  showSearch?: boolean;
  account?: "server" | "session";
}) {
  return (
    // The phone bar is Figma "NavBar" Type=Landing (6884:817): 72px including a
    // 1px rule at 10% ink, the 78x24 wordmark 24px in, a 28px search glyph, and
    // the 40px avatar 24px from the right edge. Tablet and desktop keep their
    // full-width rule on the header itself.
    <header className="sticky top-0 z-30 bg-[color-mix(in_srgb,var(--surface-app)_85%,transparent)] backdrop-blur-md md:border-b md:border-[var(--border-subtle)]">
      <div className="mx-auto flex h-[72px] w-full max-w-[72rem] items-center gap-4 border-b border-[var(--line-hairline-10)] px-6 md:border-b-0 md:px-10">
        {/* `flex`: an inline link sits the 24px mark on a taller line box, 4px
            above the frame's y. */}
        <Link href="/" aria-label="bluntly home" className="flex text-[var(--accent-primary)]">
          <Logo height={24} label="bluntly" />
        </Link>

        {/* Desktop inline search */}
        <div className="ml-4 hidden w-full max-w-[32rem] flex-1 md:block">
          <SearchAutocomplete
            // Figma SearchField/Inline (7761:7998): Default #d1d1d1 edge, Focused 1.5px brand.
            inputClassName={`h-10 w-full rounded-[var(--radius-pill)] pl-11 pr-4 text-[14px] text-[var(--text-primary)] outline-none placeholder:text-[var(--base-gray-400)] ${SEARCH_FIELD_STATES}`}
          />
        </div>

        {/* 14px between the search glyph's 40px target and the avatar puts the
            glyph at x278 and the avatar at x326, as drawn. */}
        <div className="ml-auto flex items-center gap-3.5 md:gap-3">
          {showSearch ? (
            <Link
              href="/search"
              aria-label="Search"
              className="grid h-10 w-10 place-items-center rounded-full text-[var(--text-primary)] hover:bg-[var(--line-hairline-10)] md:hidden"
            >
              <MagnifyingGlass size={28} />
            </Link>
          ) : null}

          {/* First in the row: for a reader who is already sold, browsing is
              the thing they came to do. `/` stays the landing page. */}
          <Link
            href="/feed"
            className="hidden min-h-[44px] items-center text-[13px] font-medium text-[var(--text-secondary)] hover:text-[var(--text-primary)] md:inline-flex"
          >
            Feed
          </Link>

          <Link
            href="/categories"
            className="hidden min-h-[44px] items-center text-[13px] font-medium text-[var(--text-secondary)] hover:text-[var(--text-primary)] md:inline-flex"
          >
            Categories
          </Link>

          <Link
            href="/questions"
            className="hidden min-h-[44px] items-center text-[13px] font-medium text-[var(--text-secondary)] hover:text-[var(--text-primary)] md:inline-flex"
          >
            Q&amp;A
          </Link>

          <Link
            href="/requests"
            className="hidden min-h-[44px] items-center text-[13px] font-medium text-[var(--text-secondary)] hover:text-[var(--text-primary)] md:inline-flex"
          >
            Requests
          </Link>

          <Link
            href="/reviews/new"
            className="hidden items-center gap-2 rounded-[var(--radius-pill)] bg-[var(--accent-primary)] px-4 py-2 text-[13px] font-semibold text-white hover:bg-[var(--accent-primary-strong)] md:inline-flex"
          >
            <PencilSimpleLine size={16} weight="bold" />
            Write a review
          </Link>

          {account === "session" ? <SessionProfileNav /> : <ProfileNavPanel user={user} />}
        </div>
      </div>
      {/* QA-061: speaks up when another tab of this browser signs in as someone else. */}
      {account === "session" ? (
        <SessionAccountSwitchNotice />
      ) : (
        <AccountSwitchNotice username={user?.username} />
      )}
    </header>
  );
}

export default SiteHeader;

/**
 * The header while a page loads: the same 72px bar and the real wordmark, with
 * placeholders where the search field, the links, "Write a review" and the
 * avatar go. A loading state does not know who is signed in, and the real
 * header with no user would flash "Log in" at someone who is; without any bar
 * the page would jump 72px when it arrives.
 */
export function SiteHeaderSkeleton({ showSearch = true }: { showSearch?: boolean }) {
  return (
    <header aria-hidden="true" className="sticky top-0 z-30 bg-[color-mix(in_srgb,var(--surface-app)_85%,transparent)] backdrop-blur-md md:border-b md:border-[var(--border-subtle)]">
      <div className="mx-auto flex h-[72px] w-full max-w-[72rem] items-center gap-4 border-b border-[var(--line-hairline-10)] px-6 md:border-b-0 md:px-10">
        <span className="flex text-[var(--accent-primary)]">
          <Logo height={24} label="bluntly" />
        </span>
        <span className="ml-4 hidden w-full max-w-[32rem] flex-1 md:block">
          <Pill className="h-10 w-full" />
        </span>
        <span className="ml-auto flex items-center gap-3.5 md:gap-3">
          {showSearch ? <Circle size={40} className="md:hidden" /> : null}
          {["w-9", "w-[4.5rem]", "w-8", "w-16"].map((w, i) => (
            <Bar key={i} size={10} className={`hidden md:block ${w}`} />
          ))}
          <Pill className="hidden h-9 w-36 md:block" />
          <Circle size={40} />
        </span>
      </div>
    </header>
  );
}
