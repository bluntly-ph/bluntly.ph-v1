"use client";

import Link from "next/link";
import { usePathname, useSearchParams } from "next/navigation";
import { ChatCircleDots } from "@phosphor-icons/react/dist/ssr";

import { AdminActivityMenu } from "@/components/admin/AdminActivityMenu";
import { AdminNav, isActive, sectionFor, sectionTabsFor, type Attention } from "@/components/admin/AdminNav";
import { AdminSearch } from "@/components/admin/AdminSearch";
import type { ActivityRow } from "@/lib/moderation";

/**
 * The admin console shell, built to "Draft/Admin/Overview v3" (7879:10223,
 * read 2026-10-02): a 232px rail on the grey app surface, and the workspace as
 * one white card (radius 16, hairline border) whose 56px top bar carries the
 * breadcrumb, the search and the activity button.
 *
 * The shell is exactly the viewport and only the workspace body scrolls:
 *
 *   the shell is exactly the viewport      h-dvh, overflow-hidden
 *   the rail never moves                   its own column, full height
 *   the top bar never moves                outside the scrolling region
 *   long data scrolls inside its own pane  min-h-0 + overflow-y-auto
 *
 * A merged section (Products, People, Payouts) shows its tabs under the top
 * bar, so the screens the 18 → 12 merge folded away stay one click from here.
 */
/** Where the frame's page title differs from the rail label. */
const PAGE_TITLE: Record<string, string> = { Queue: "Review Queue" };
/**
 * Pages inside a section that are not its list and have no subtab row any more
 * (owner, 2026-10-03: the leftover "Catalogue | Prices" and "Members | Users"
 * rows were removed). Named here so the title and the crumb still say where you are.
 */
const PATH_PAGE: Record<string, { crumb: string; title: string }> = {
  "/admin/prices": { crumb: "Prices", title: "Price observations" },
  "/admin/users": { crumb: "Users", title: "User management" },
};
/** The Queue frames title each view: Answer / Report / Support Queue. */
const QUEUE_TITLE: Record<string, string> = {
  answers: "Answer Queue",
  report: "Report Queue",
  support: "Support Queue",
  all: "All reviews",
};

export function AdminShell({
  viewer,
  attention,
  inboxUnread = 0,
  activity,
  activityFetchedAt,
  children,
}: {
  viewer: { name: string; role: string };
  attention: Attention;
  inboxUnread?: number;
  activity: ActivityRow[] | null;
  activityFetchedAt: number;
  children: React.ReactNode;
}) {
  const pathname = usePathname() ?? "/admin";
  const section = sectionFor(pathname);
  // A person's investigation page is under People but is not one of its lists.
  const personPage = pathname.startsWith("/admin/people/");
  const tabs = personPage ? [] : sectionTabsFor(pathname, viewer.role);
  // A tab named like its section ("Payouts / Payouts") adds nothing to the crumb.
  const pathPage = PATH_PAGE[pathname];
  const current =
    tabs.find((t) => isActive(t, pathname) && t.label !== section?.label) ??
    (pathPage ? { label: pathPage.crumb } : undefined);
  // The page's one h1. The Queue frame titles its body "Review Queue" in 24px
  // SemiBold; the Overview frame draws no title, so there it is for screen
  // readers only. No page renders its own h1.
  const overview = pathname === "/admin";
  const tab = useSearchParams()?.get("tab") ?? "";
  const title =
    pathPage?.title ??
    (section?.label === "Queue" ? QUEUE_TITLE[tab] : undefined) ??
    PAGE_TITLE[section?.label ?? ""] ??
    section?.label ??
    "Overview";

  return (
    <div className="flex h-dvh overflow-hidden bg-[var(--surface-app)] p-2 lg:pl-0">
      <AdminNav viewer={viewer} attention={attention} />

      <div className="flex min-w-0 flex-1 flex-col overflow-hidden rounded-[16px] border border-[var(--border-subtle)] bg-[var(--surface-card)]">
        <header className="flex h-14 shrink-0 items-center gap-[10px] border-b border-[var(--border-subtle)] pl-6 pr-4">
          <nav aria-label="Breadcrumb" className="flex min-w-0 flex-1 items-center gap-[6px] text-[12px] leading-none">
            <Link href="/admin" className="text-[var(--text-secondary)] hover:text-[var(--text-primary)]">
              Admin
            </Link>
            <span className="text-[var(--border-default)]">/</span>
            {current && section?.href ? (
              <Link href={section.href} className="text-[var(--text-secondary)] hover:text-[var(--text-primary)]">
                {section.label}
              </Link>
            ) : (
              <span className={current ? "text-[var(--text-secondary)]" : "font-medium"}>
                {section?.label ?? "Overview"}
              </span>
            )}
            {current ? (
              <>
                <span className="text-[var(--border-default)]">/</span>
                <span className="truncate font-medium">{current.label}</span>
              </>
            ) : null}
          </nav>
          <AdminSearch />
          <Link
            href="/admin/inbox"
            aria-label={inboxUnread ? `Inbox, ${inboxUnread} unread` : "Inbox"}
            className="relative grid size-9 shrink-0 place-items-center rounded-full border border-[var(--border-subtle)] hover:bg-[var(--surface-app)]"
          >
            <ChatCircleDots size={18} />
            {inboxUnread ? <span aria-hidden className="absolute right-[7px] top-[7px] size-[7px] rounded-full bg-[var(--accent-primary)]" /> : null}
          </Link>
          <AdminActivityMenu rows={activity} fetchedAt={activityFetchedAt} />
        </header>

        {tabs.length > 0 ? (
          <nav
            aria-label={`${section?.label ?? ""} sections`}
            className="flex shrink-0 gap-5 border-b border-[var(--border-subtle)] px-6"
          >
            {tabs.map((t) => {
              const active = isActive(t, pathname);
              return (
                <Link
                  key={t.href}
                  href={t.href!}
                  aria-current={active ? "page" : undefined}
                  className={`-mb-px border-b-2 pb-[9px] pt-3 text-[12px] font-medium leading-none ${
                    active
                      ? "border-[var(--text-primary)] text-[var(--text-primary)]"
                      : "border-transparent text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
                  }`}
                >
                  {t.label}
                </Link>
              );
            })}
          </nav>
        ) : null}

        {/* The only scrolling region. `relative` makes it the containing block
            for sr-only (position:absolute) descendants, which otherwise escape
            this box's overflow and scroll the whole document. */}
        <main className="relative min-h-0 flex-1 overflow-y-auto px-4 pb-6 pt-5 sm:px-6">
          <h1 className={overview || personPage ? "sr-only" : "mb-4 pt-1 text-[24px] font-semibold leading-8"}>
            {personPage ? "Person investigation" : title}
          </h1>
          {children}
        </main>
      </div>
    </div>
  );
}
