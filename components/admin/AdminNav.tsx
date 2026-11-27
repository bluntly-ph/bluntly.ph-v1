"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import {
  CaretUpDown,
  ChartLineUp,
  ChatCircleDots,
  ClockCounterClockwise,
  FileText,
  GearSix,
  House,
  Lightning,
  LinkSimple,
  List,
  Package,
  Signpost,
  SignOut,
  SquaresFour,
  Storefront,
  Tray,
  Users,
  Wallet,
  X,
} from "@phosphor-icons/react/dist/ssr";

import { logout } from "@/app/actions/auth";
import { isSuperAdminRole, roleLabel } from "@/lib/roles";

/**
 * The console's rail, built to Admin/Sidebar in "Draft/Admin/Overview v3"
 * (7879:10224, read 2026-10-02).
 *
 * The meeting of 2026-10-02 merged the old 18-item rail into twelve (Figma
 * version note "Sidebar: 18 items → 12"). Nothing was removed: the screens a
 * merge folded away are tabs of the section that absorbed them (SECTION_TABS),
 * so every route still exists and is one click from the rail.
 *
 *   Queue            Review Queue + Q&A (tabs inside the queue screen)
 *   Inbox            conversations with sellers and reviewers (0076)
 *   Special routing  Super Admin only
 *   Products         the catalogue (Price observations open from Needs attention and
 *                    Quick actions; the old "Catalogue | Prices" subtab row is gone)
 *   Sellers          seller claims + review appeals
 *   People           members (Users, the Super Admin's role tool, opens from
 *                    Settings → Team → Manage roles; no subtab row, as drawn)
 *   Affiliate        affiliate links + commission imports
 *   Payouts          Payouts + Honesty Fund + QA payments (views of the Payouts screen)
 *   Reports          the CSV/PDF reports
 *   footer           Analytics, Activity log, Settings
 *
 * Counts on the pills come from the Overview's "Needs attention" panel, so the
 * rail and the panel cannot disagree. Hiding a Super Admin item is presentation
 * only: the API refuses an Administrator on every one of those routes.
 */

type PhosphorIcon = typeof Tray;

export type Attention = Record<string, number | null>;

type Pill = { text: string; tone: "critical" | "count" | "muted" };

export type NavItem = {
  label: string;
  Icon: PhosphorIcon;
  href?: string;
  /** Path prefixes that make this item current. Defaults to `href`. */
  match?: string[];
  exact?: boolean;
  superAdminOnly?: boolean;
  /** Inert items say why on their face instead of routing nowhere. */
  blocked?: string;
  why?: string;
  pill?: (attention: Attention) => Pill | null;
};

function sum(attention: Attention, keys: string[]): number {
  return keys.reduce((n, k) => n + (attention[k] ?? 0), 0);
}

function countPill(n: number, critical = false): Pill | null {
  if (n <= 0) return null;
  return { text: String(n), tone: critical ? "critical" : "count" };
}

/** The four moderation counts are the Queue's tabs (Reviews, Answers,
 *  Reports, Support); red while anything in it is past due. */
const QUEUE_KEYS = ["reviews_past_due", "answers_to_moderate", "open_reports", "support_requests"];

export const NAV: { heading: string | null; items: NavItem[] }[] = [
  {
    heading: null,
    items: [{ label: "Overview", Icon: SquaresFour, href: "/admin", exact: true }],
  },
  {
    heading: "Moderate",
    items: [
      {
        label: "Queue",
        Icon: Tray,
        href: "/admin/review-queue",
        pill: (a) => countPill(sum(a, QUEUE_KEYS), (a.reviews_past_due ?? 0) > 0),
      },
      {
        // Screen/Admin/Inbox (8291:30461): sellers and reviewers write to the team.
        label: "Inbox",
        Icon: ChatCircleDots,
        href: "/admin/inbox",
        pill: (a) => countPill(a.inbox_unread ?? 0, true),
      },
      {
        label: "Special routing",
        Icon: Signpost,
        href: "/admin/special-routing",
        superAdminOnly: true,
        pill: () => ({ text: "Super", tone: "muted" }),
      },
    ],
  },
  {
    heading: "Manage",
    items: [
      {
        label: "Products",
        Icon: Package,
        href: "/admin/products",
        match: ["/admin/products", "/admin/prices"],
        // Figma 7966:11087: the badge repeats the Queue tab (submitted products).
        pill: (a) => countPill(a.products_to_review ?? 0),
      },
      {
        label: "Sellers",
        Icon: Storefront,
        href: "/admin/sellers",
        pill: (a) => countPill(a.seller_claims_appeals ?? 0),
      },
      {
        label: "People",
        Icon: Users,
        href: "/admin/reviewers",
        match: ["/admin/reviewers", "/admin/users", "/admin/people"],
      },
    ],
  },
  {
    heading: "Money",
    items: [
      {
        label: "Affiliate",
        Icon: LinkSimple,
        href: "/admin/affiliate-links",
        pill: (a) => countPill(a.reviews_needing_link ?? 0),
      },
      {
        label: "Payouts",
        Icon: Wallet,
        href: "/admin/payouts",
        match: ["/admin/payouts", "/admin/honesty-fund", "/admin/qa-sandbox"],
        pill: (a) => countPill(a.failed_payouts ?? 0, true),
      },
      { label: "Reports", Icon: FileText, href: "/admin/reports" },
    ],
  },
];

export const FOOTER: NavItem[] = [
  { label: "Analytics", Icon: ChartLineUp, href: "/admin/analytics" },
  { label: "Activity log", Icon: ClockCounterClockwise, href: "/admin/activity" },
  { label: "Settings", Icon: GearSix, href: "/admin/settings" },
];

/**
 * The tabs of a merged section, shown at the top of its workspace. A tab with
 * `superAdminOnly` is left out for an Administrator; its page checks the role
 * on the server as well (getSuperAdminAccess).
 */
export const SECTION_TABS: { section: string; tabs: NavItem[] }[] = [
  {
    // The financial report (Figma Screen/Admin/Reports) and, beside it, the
    // CSV exports that were Reports before the redesign.
    section: "Reports",
    tabs: [
      { label: "Reports", Icon: FileText, href: "/admin/reports", exact: true },
      { label: "Honesty Fund", Icon: FileText, href: "/admin/reports/honesty-fund" },
      { label: "Commissions & Payouts", Icon: FileText, href: "/admin/reports/commissions" },
      { label: "Seller Ratings", Icon: FileText, href: "/admin/reports/seller-ratings" },
    ],
  },
];

function visible(items: NavItem[], superAdmin: boolean): NavItem[] {
  return items.filter((item) => superAdmin || !item.superAdminOnly);
}

/** The rail for this viewer: Super Admin items only for a Super Admin. */
export function navFor(role: string | null | undefined): typeof NAV {
  const superAdmin = isSuperAdminRole(role);
  return NAV.map((group) => ({ ...group, items: visible(group.items, superAdmin) }))
    .filter((group) => group.items.length > 0);
}

export function isActive(item: NavItem, pathname: string): boolean {
  if (!item.href) return false;
  if (item.exact) return pathname === item.href;
  return (item.match ?? [item.href]).some((p) => pathname === p || pathname.startsWith(`${p}/`));
}

/** The section (rail item) a path belongs to, for the breadcrumb and tabs. */
export function sectionFor(pathname: string): NavItem | null {
  for (const item of [...NAV.flatMap((g) => g.items), ...FOOTER]) {
    if (isActive(item, pathname)) return item;
  }
  return null;
}

export function sectionTabsFor(pathname: string, role: string | null | undefined): NavItem[] {
  const section = sectionFor(pathname);
  const entry = SECTION_TABS.find((s) => s.section === section?.label);
  return entry ? visible(entry.tabs, isSuperAdminRole(role)) : [];
}

const PILL_TONE: Record<Pill["tone"], string> = {
  critical: "bg-[var(--status-critical-bg)] text-[var(--status-critical-fg)]",
  count: "bg-[var(--surface-card)] text-[var(--text-primary)]",
  muted: "bg-[var(--border-subtle)] text-[var(--text-secondary)]",
};

export function NavRow({
  item,
  active,
  attention,
  onNavigate,
}: {
  item: NavItem;
  active: boolean;
  attention: Attention;
  onNavigate: () => void;
}) {
  const { label, Icon, href, blocked, why } = item;
  const pill = item.pill?.(attention) ?? null;
  // Admin/Sidebar NavItem (8058:14420): 32px rows, 2px apart.
  const row = `flex h-8 w-full items-center gap-[10px] rounded-[8px] px-2 text-[14px] leading-none`;
  if (!href) {
    return (
      <span title={why} aria-disabled="true" className={`${row} relative cursor-not-allowed text-[var(--text-muted)]`}>
        <Icon size={18} className="shrink-0" />
        <span className="flex-1 truncate">{label}</span>
        <span className="text-[10px]">{blocked}</span>
        <span className="sr-only">{`Unavailable. ${why ?? ""}`}</span>
      </span>
    );
  }
  return (
    <Link
      href={href}
      onClick={onNavigate}
      aria-current={active ? "page" : undefined}
      className={`${row} transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-[var(--accent-primary)] ${
        active
          ? "bg-[var(--surface-card)] font-medium text-[var(--text-primary)] shadow-[0_1px_1px_rgba(0,0,0,0.05)]"
          : "text-[var(--text-primary)] hover:bg-[var(--surface-card)]/60"
      }`}
    >
      {/* Admin/Inbox (8291:30461): the current row keeps its label in ink
          and turns only its outline glyph brand orange. */}
      <Icon size={18} className={`shrink-0 ${active ? "text-[var(--accent-primary)]" : ""}`} />
      <span className="flex-1 truncate">{label}</span>
      {pill ? (
        <span className={`rounded-full px-[7px] py-[2px] text-[10px] leading-none ${PILL_TONE[pill.tone]}`}>
          {pill.text}
        </span>
      ) : null}
    </Link>
  );
}

/** The ⌘K quick actions: the jobs an administrator starts most, one keystroke away. */
const QUICK_ACTIONS: { label: string; href: string; superAdminOnly?: boolean }[] = [
  { label: "Open the review queue", href: "/admin/review-queue" },
  { label: "Answers to moderate", href: "/admin/review-queue?tab=answers" },
  { label: "Open reports", href: "/admin/review-queue?tab=report" },
  { label: "Send payouts", href: "/admin/payouts" },
  { label: "Import an affiliate report", href: "/admin/affiliate-links" },
  { label: "Generate a report", href: "/admin/reports" },
  { label: "Price observations", href: "/admin/prices" },
  { label: "Routing decisions", href: "/admin/special-routing", superAdminOnly: true },
  { label: "Manage roles", href: "/admin/users", superAdminOnly: true },
];

function QuickActions({ superAdmin, onNavigate }: { superAdmin: boolean; onNavigate: () => void }) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setOpen((o) => !o);
      } else if (e.key === "Escape") {
        setOpen(false);
      }
    }
    function onClick(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    }
    window.addEventListener("keydown", onKey);
    window.addEventListener("mousedown", onClick);
    return () => {
      window.removeEventListener("keydown", onKey);
      window.removeEventListener("mousedown", onClick);
    };
  }, []);

  return (
    <div ref={ref} className="relative">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        aria-haspopup="menu"
        className="flex w-full items-center gap-2 rounded-[10px] border border-[var(--border-subtle)] bg-[var(--surface-card)] py-[7px] pl-[10px] pr-2 text-left focus-visible:outline focus-visible:outline-2 focus-visible:outline-[var(--accent-primary)]"
      >
        <Lightning size={16} className="shrink-0" />
        <span className="flex-1 text-[12px] font-medium leading-none">Quick actions</span>
        <kbd className="rounded-[6px] bg-[var(--surface-app)] px-[6px] py-px font-sans text-[10px] leading-none text-[var(--text-secondary)]">
          ⌘K
        </kbd>
      </button>
      {open ? (
        <ul
          role="menu"
          className="absolute left-0 right-0 top-[calc(100%+4px)] z-40 rounded-[12px] border border-[var(--border-subtle)] bg-[var(--surface-card)] py-1 shadow-[var(--shadow-modal)]"
        >
          {QUICK_ACTIONS.filter((a) => superAdmin || !a.superAdminOnly).map((a) => (
            <li key={a.href} role="none">
              <Link
                role="menuitem"
                href={a.href}
                onClick={() => {
                  setOpen(false);
                  onNavigate();
                }}
                className="block px-3 py-2 text-[12px] leading-none hover:bg-[var(--surface-app)]"
              >
                {a.label}
              </Link>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}

/**
 * The workspace switcher behind "Bluntly Admin" (meeting 2026-10-02, 20:40):
 * "add user" was removed; it keeps Home/Feed and Log out. There is one signed-in
 * account, so there is nothing else to switch to.
 */
function Workspace({ viewer }: { viewer: { name: string; role: string } }) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    function onClick(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    }
    window.addEventListener("mousedown", onClick);
    return () => window.removeEventListener("mousedown", onClick);
  }, []);

  return (
    <div ref={ref} className="relative">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        aria-haspopup="menu"
        className="flex w-full items-center gap-[10px] rounded-[10px] px-1 py-[5px] text-left hover:bg-[var(--surface-card)]/60 focus-visible:outline focus-visible:outline-2 focus-visible:outline-[var(--accent-primary)]"
      >
        {/* Figma Overview v4 (8444:38623): the bluntly mark in brand orange
            on the peach tile, not a letter. */}
        <span aria-hidden="true" className="grid size-8 shrink-0 place-items-center rounded-[9px] bg-[var(--status-high-bg)] text-[var(--accent-primary)]">
          <svg width="23" height="14" viewBox="0 0 20.25 12.32" className="rotate-180" fill="currentColor">
            <path
              fillRule="evenodd"
              clipRule="evenodd"
              d="M4.60101 12.315C2.79098 12.272 1.2407 11.1719 0.544266 9.60896C0.0611048 8.52464 -0.00258593 7.68618 7.75363e-05 7.00665C0.00598018 5.50118 7.75363e-05 0.000405948 7.75363e-05 0.000405948H3.80314C3.80314 0.000405948 3.80597 5.81489 3.80314 7.17334C3.80236 7.54307 4.05111 7.96393 4.4332 8.12677C4.76944 8.27007 5.29764 8.17814 5.55733 7.92095C6.9268 6.56468 12.2333 1.30876 13.2343 0.624828C13.8919 0.17551 14.5615 0 15.6435 0C17.4575 0 19.0109 1.14202 19.7079 2.7078C20.2037 3.82177 20.2461 4.38028 20.2474 5.17135C20.25 6.75691 20.2474 12.3164 20.2474 12.3164H16.4443C16.4443 12.3164 16.4443 6.32585 16.4443 4.95C16.4443 4.63161 16.2617 4.20518 15.7652 4.07111C15.3709 3.96462 14.9694 4.11271 14.6901 4.39202C13.3137 5.7685 8.00061 11.0159 7.00033 11.7002C6.34819 12.1464 5.44412 12.3351 4.60101 12.315Z"
            />
          </svg>
        </span>
        <span className="min-w-0 flex-1">
          <span className="block truncate text-[14px] font-semibold leading-none">Bluntly Admin</span>
          <span className="mt-0.5 block truncate text-[10px] leading-none text-[var(--text-secondary)]">
            {roleLabel(viewer.role)}
          </span>
        </span>
        <CaretUpDown size={16} className="shrink-0 text-[var(--text-secondary)]" />
      </button>
      {open ? (
        <div
          role="menu"
          className="absolute left-0 right-0 top-[calc(100%+4px)] z-40 rounded-[12px] border border-[var(--border-subtle)] bg-[var(--surface-card)] py-1 shadow-[var(--shadow-modal)]"
        >
          <p className="truncate px-3 pb-2 pt-1.5 text-[12px] leading-none text-[var(--text-secondary)]">
            Signed in as <span className="font-medium text-[var(--text-primary)]">{viewer.name}</span>
          </p>
          <Link
            role="menuitem"
            href="/feed"
            className="flex items-center gap-2 px-3 py-2 text-[12px] leading-none hover:bg-[var(--surface-app)]"
          >
            <House size={16} /> Home / Feed
          </Link>
          <form action={logout}>
            <button
              type="submit"
              role="menuitem"
              className="flex w-full items-center gap-2 px-3 py-2 text-left text-[12px] leading-none text-[var(--accent-danger)] hover:bg-[var(--surface-app)]"
            >
              <SignOut size={16} /> Log out
            </button>
          </form>
        </div>
      ) : null}
    </div>
  );
}

export function AdminNav({
  viewer,
  attention,
}: {
  viewer: { name: string; role: string };
  attention: Attention;
}) {
  const pathname = usePathname() ?? "/admin";
  const [drawerOpen, setDrawerOpen] = useState(false);
  const superAdmin = isSuperAdminRole(viewer.role);
  const close = () => setDrawerOpen(false);

  const rail = (
    <div className="flex h-full flex-col gap-[14px] px-3 pb-1 pt-3">
      <Workspace viewer={viewer} />
      <QuickActions superAdmin={superAdmin} onNavigate={close} />

      <nav aria-label="Admin sections" className="flex min-h-0 flex-1 flex-col gap-[14px] overflow-y-auto">
        {navFor(viewer.role).map((group) => (
          <div key={group.heading ?? "home"} className="flex flex-col gap-[2px]">
            {group.heading ? (
              <p className="h-[18px] px-2 text-[10px] leading-[14px] text-[var(--text-secondary)]">{group.heading}</p>
            ) : null}
            <ul className="flex flex-col gap-[2px]">
              {group.items.map((item) => (
                <li key={item.label}>
                  <NavRow item={item} active={isActive(item, pathname)} attention={attention} onNavigate={close} />
                </li>
              ))}
            </ul>
          </div>
        ))}
      </nav>

      <ul aria-label="Console" className="flex flex-col gap-[2px]">
        {FOOTER.map((item) => (
          <li key={item.label}>
            <NavRow item={item} active={isActive(item, pathname)} attention={attention} onNavigate={close} />
          </li>
        ))}
      </ul>
    </div>
  );

  return (
    <>
      <aside className="hidden h-full w-[232px] shrink-0 lg:block">{rail}</aside>

      {/* Below lg the rail is a drawer. */}
      <button
        type="button"
        onClick={() => setDrawerOpen(true)}
        aria-label="Open admin navigation"
        className="fixed bottom-4 left-4 z-50 grid h-11 w-11 place-items-center rounded-full bg-[var(--accent-primary)] text-[var(--text-on-brand)] shadow-[var(--shadow-fab)] lg:hidden"
      >
        <List size={22} weight="bold" />
      </button>
      {drawerOpen ? (
        <div className="fixed inset-0 z-50 flex lg:hidden">
          <div className="absolute inset-0 bg-black/40" onClick={close} aria-hidden />
          <aside className="relative h-full w-[260px] bg-[var(--surface-app)]">
            <button
              type="button"
              onClick={close}
              aria-label="Close admin navigation"
              className="absolute right-2 top-2 z-10 grid h-8 w-8 place-items-center rounded-full text-[var(--text-secondary)] hover:bg-[var(--surface-card)]"
            >
              <X size={18} weight="bold" />
            </button>
            {rail}
          </aside>
        </div>
      ) : null}
    </>
  );
}
