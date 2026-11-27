"use client";

import Image from "next/image";
import { createPortal } from "react-dom";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useCallback, useEffect, useId, useRef, useState } from "react";
import {
  Atom,
  Bell,
  ChalkboardTeacher,
  ChatCenteredDots,
  ChatCircleDots,
  Compass,
  List,
  PaperPlaneTilt,
  PencilLine,
  Shapes,
  ShieldCheck,
  SignOut,
  UserCircle,
  X,
} from "@phosphor-icons/react/dist/ssr";
import type { Icon } from "@phosphor-icons/react";

import { logout } from "@/app/actions/auth";

import { badgeLabel } from "@/components/site/notification-model";
import { refreshUnread, useUnreadCount } from "@/components/site/unread-store";
import { isStaffRole } from "@/lib/roles";

/**
 * The navigation panel behind the header avatar: Figma "ProfileDrawer"
 * (7057:1377) and "ProfileSidebar" (7056:1368), read 2026-09-15.
 *
 *   scrim     black at 40% over the screen
 *   panel     300px against the right edge in the page colour
 *   header    a 100px avatar 24px in, the name 20px after it in 28px Bold and
 *             the member line 13px under it in 10px Light
 *   rows      SidebarItem: a 28px glyph 12px before 16px Light, 16px apart, 24px
 *             in; groups split by hairlines at a 20px inset with 24px above and
 *             below them
 *
 * This replaces the mobile bottom navigation bar: one entry point (the avatar)
 * opening a panel that lists only destinations that genuinely exist.
 *
 * INTENTIONAL PRODUCT DIFFERENCES:
 *  - "Admin" appears only for an Administrator or a Super Admin, and only as a
 *    way in: /admin is guarded by requireStaff, so hiding the row is
 *    presentation, not the boundary.
 *  - "Log out" ends the session through the server action rather than clearing
 *    anything in the browser, so nothing authenticated survives it.
 *  - "Bookmarks" and "Recent reads" are not listed: neither has a route, and a
 *    menu row to `#` or "coming soon" would lie about what the product does.
 *    Their group carries "Q&A" instead, which does exist; the feed is the
 *    panel's first row, "Feed" (owner, 2026-09-28).
 *  - "Notifications" joins Profile and Dashboard: it is a real page with an
 *    unread count and no other way in on a phone.
 *  - A close button in the header, and "Log in" for a signed-out visitor.
 *  - No dark mode row (QA-013): the design of record is light-only
 *    (docs/DEVIATIONS.md #65) and the owner removed the dead toggle.
 *  - The frame's "Founding member" line has no data behind it; it reads
 *    "Member".
 *  - Owner review (2026-09-16) found the drawn scale too big in use: a 100px
 *    avatar and a 28px name truncated even short handles. The panel keeps the
 *    frame's structure, order, hairlines and 300px width at a compact scale — a
 *    64px avatar, the name in 20px SemiBold, 24px glyphs 12px before 15px Light
 *    rows on a 40px pitch, 20px insets.
 */

type Item = { href: string; icon: Icon; label: string };

// Owner, 2026-09-28: "Feed" first in the side navigation, for everyone. It is
// the reader's way back to the review feed from anywhere on a phone, where the
// header's own Feed link is hidden.
const FEED_ITEM: Item = { href: "/feed", icon: Compass, label: "Feed" };

const ACCOUNT_GROUP: Item[] = [
  FEED_ITEM,
  { href: "/profile", icon: UserCircle, label: "Profile" },
  { href: "/dashboard", icon: Atom, label: "Dashboard" },
  { href: "/notifications", icon: Bell, label: "Notifications" },
  // Screen/Messages (8296:31219): talking to the Bluntly team has no other way
  // in on a phone.
  { href: "/messages", icon: ChatCircleDots, label: "Messages" },
];

const CREATE_GROUP: Item[] = [
  { href: "/reviews/new", icon: PencilLine, label: "Write a review" },
  { href: "/requests/new", icon: PaperPlaneTilt, label: "Request review" },
  { href: "/requests", icon: ChalkboardTeacher, label: "Bounty board" },
  { href: "/categories", icon: Shapes, label: "Categories" },
];

/** Shown only to an administrator or an admin; the route enforces the same thing. */
const ADMIN_ITEM: Item = { href: "/admin", icon: ShieldCheck, label: "Admin" };

// No second /feed row: Feed heads the panel (QA-021: one row per destination).
const READ_GROUP: Item[] = [{ href: "/questions", icon: ChatCenteredDots, label: "Q&A" }];

/**
 * Shown to a signed-out visitor. The header's own links are `hidden …
 * md:inline-flex`, so without these a visitor on a phone could reach the feed,
 * categories, Q&A and the bounty board from nowhere in the site chrome.
 */
const PUBLIC_GROUP: Item[] = [
  FEED_ITEM,
  { href: "/categories", icon: Shapes, label: "Categories" },
  { href: "/questions", icon: ChatCenteredDots, label: "Q&A" },
  { href: "/requests", icon: ChalkboardTeacher, label: "Bounty board" },
];

const ROW =
  "flex h-6 items-center gap-3 px-5 text-[15px] font-light leading-none text-[var(--text-primary)] no-underline hover:text-[var(--accent-primary)] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--accent-primary)]";
const GROUP = "flex flex-col gap-4 py-5";
const DIVIDER = "mx-5 border-t border-[var(--line-hairline-10)]";

export type PanelUser = {
  username: string | null;
  avatarUrl: string | null;
  /**
   * The account's role. Only an Administrator or a Super Admin sees the Admin
   * entry — and hiding it is presentation, never the boundary: /admin is
   * guarded server-side by requireStaff (app/admin/layout.tsx).
   */
  role?: string | null;
  /** The reviewer's own trust, for previews of their posts (ReviewQuoteCard). */
  reputationScore?: string | number | null;
  trustStage?: number | null;
  trustLevelName?: string | null;
} | null;

export function ProfileNavPanel({ user }: { user: PanelUser }) {
  const staff = isStaffRole(user?.role);
  const accountGroup = staff ? [...ACCOUNT_GROUP, ADMIN_ITEM] : ACCOUNT_GROUP;
  // Derived, not an effect: the panel is open only while the route it was
  // opened on is still the current one, so navigating closes it without a
  // pathname effect calling setState.
  const pathname = usePathname();
  const [openedOn, setOpenedOn] = useState<string | null>(null);
  const open = openedOn !== null && openedOn === pathname;
  const panelId = useId();
  const panelRef = useRef<HTMLDivElement | null>(null);
  const triggerRef = useRef<HTMLButtonElement | null>(null);

  // The unread count, for a signed-in reader only. Keyed on the username rather
  // than the `user` object, which is a new object on every server render; the
  // count is read when the account changes and on each page load, and after
  // that follows the shared store — opening, marking or clearing a
  // notification anywhere updates this badge at once (QA-064).
  const username = user?.username ?? null;
  const signedIn = user !== null;
  useEffect(() => {
    if (!signedIn) return;
    void refreshUnread();
  }, [signedIn, username]);
  const unread = useUnreadCount() ?? 0;
  const badge = signedIn ? badgeLabel(unread) : null;

  const close = useCallback(() => {
    setOpenedOn(null);
    triggerRef.current?.focus();
  }, []);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.preventDefault();
        close();
      }
    };
    document.addEventListener("keydown", onKey);
    // Body scroll is locked while the sheet is open, and restored to whatever
    // it was — not hardcoded to "", which would clobber another lock.
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    // Move focus into the panel so a keyboard user is not left behind it.
    const first = panelRef.current?.querySelector<HTMLElement>("a, button");
    first?.focus();
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = previous;
    };
  }, [open, close]);

  const initial = (user?.username ?? "?").slice(0, 1).toUpperCase();
  const groups = user ? [accountGroup, CREATE_GROUP, READ_GROUP] : [PUBLIC_GROUP];

  return (
    <>
      <button
        ref={triggerRef}
        type="button"
        onClick={() => setOpenedOn((v) => (v === null ? pathname : null))}
        aria-expanded={open}
        aria-controls={open ? panelId : undefined}
        aria-haspopup="dialog"
        aria-label={
          user
            ? badge
              ? `Menu and profile, ${unread} unread notification${unread === 1 ? "" : "s"}`
              : "Menu and profile"
            : "Menu"
        }
        className="relative grid h-10 w-10 shrink-0 cursor-pointer place-items-center overflow-hidden rounded-full bg-[var(--base-gray-200)] ring-1 ring-[var(--line-hairline-10)] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--accent-primary)]"
      >
        {user ? (
          user.avatarUrl ? (
            <Image src={user.avatarUrl} alt="" fill sizes="40px" className="object-cover" />
          ) : (
            <span className="text-[13px] font-semibold text-[var(--text-primary)]">{initial}</span>
          )
        ) : (
          <List size={20} weight="bold" className="text-[var(--text-primary)]" />
        )}
      </button>

      {open
        ? createPortal(
            /* CRITICAL: portalled to <body> on purpose. The site header is
               `backdrop-blur-md`, and a non-`none` backdrop-filter makes an
               element the containing block for its `fixed` descendants — so
               rendering in place resolved `fixed inset-y-0` against the 64px
               header box and the sheet came out as an unusable 64px strip with
               a backdrop covering only the header. Measured in Chromium:
               844px tall without the blur, 64px with it. */
            <>
              {/* The scrim closes, and is not a link: a stray tap on it must not
                  navigate anywhere. */}
              <button
                type="button"
                aria-label="Close menu"
                onClick={close}
                className="fixed inset-0 z-40 cursor-default bg-[rgba(0,0,0,0.4)]"
              />
              <div
                ref={panelRef}
                id={panelId}
                role="dialog"
                aria-modal="true"
                aria-label="Navigation and profile"
                className="fixed inset-y-0 right-0 z-50 flex w-[min(300px,88vw)] flex-col overflow-y-auto bg-[var(--surface-app)] shadow-[var(--shadow-sheet)]"
              >
                <div className="relative flex items-center gap-4 p-5">
                  {user ? (
                    <span className="relative grid h-16 w-16 shrink-0 place-items-center overflow-hidden rounded-full bg-[var(--base-gray-200)]">
                      {user.avatarUrl ? (
                        <Image src={user.avatarUrl} alt="" fill sizes="64px" className="object-cover" />
                      ) : (
                        <span className="text-[24px] font-semibold text-[var(--text-primary)]">{initial}</span>
                      )}
                    </span>
                  ) : null}
                  <span className="min-w-0 flex-1 pr-8">
                    <span className="line-clamp-2 text-[18px] font-semibold leading-[1.2] text-[var(--text-primary)] [overflow-wrap:anywhere]">
                      {user ? (user.username ?? "Your account") : "Menu"}
                    </span>
                    {user ? (
                      <span className="mt-1 block text-[12px] font-light leading-none text-[rgba(32,32,32,0.7)]">
                        Member
                      </span>
                    ) : null}
                  </span>
                  <button
                    type="button"
                    onClick={close}
                    aria-label="Close menu"
                    className="absolute right-3 top-3 grid h-9 w-9 cursor-pointer place-items-center rounded-full text-[var(--text-primary)] hover:bg-[var(--line-hairline-10)] focus-visible:outline focus-visible:outline-2 focus-visible:outline-[var(--accent-primary)]"
                  >
                    <X size={20} aria-hidden="true" />
                  </button>
                </div>

                <nav aria-label="Primary" className="flex flex-col">
                  {groups.map((group, gi) => (
                    <div key={gi}>
                      <div className={DIVIDER} />
                      <div className={GROUP}>
                        {group.map(({ href, icon: Glyph, label }) => (
                          <Link key={href} href={href} className={ROW}>
                            <Glyph size={24} aria-hidden="true" className="shrink-0" />
                            {label}
                            {href === "/notifications" && badge ? (
                              <span className="ml-auto rounded-full bg-[var(--accent-primary)] px-2 py-0.5 text-[11px] font-semibold leading-4 text-white">
                                {badge}
                                <span className="sr-only"> unread</span>
                              </span>
                            ) : null}
                          </Link>
                        ))}
                      </div>
                    </div>
                  ))}

                  {user ? (
                    /* A real session end: the server action clears the cookie
                       and sends the reader to the signed-out home. It is a
                       submit button, so it is reachable by keyboard and by
                       touch like every other row here. */
                    <div className={DIVIDER} />
                  ) : null}
                  {user ? (
                    <form action={logout} className="py-5">
                      <button type="submit" className={`${ROW} w-full cursor-pointer text-left`}>
                        <SignOut size={24} aria-hidden="true" className="shrink-0" />
                        Log out
                      </button>
                    </form>
                  ) : (
                    <div className="px-5 pb-5">
                      <Link
                        href="/login"
                        className="flex h-14 items-center justify-center rounded-[var(--radius-pill)] bg-[var(--accent-primary)] text-[16px] font-semibold text-white no-underline"
                      >
                        Log in
                      </Link>
                    </div>
                  )}
                </nav>
              </div>
            </>,
            document.body,
          )
        : null}
    </>
  );
}

export default ProfileNavPanel;
