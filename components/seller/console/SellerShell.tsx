"use client";

import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import {
  ArrowSquareOut,
  CaretUpDown,
  ChartLineUp,
  ChatCircleDots,
  ChatText,
  Cube,
  DownloadSimple,
  Flag,
  GearSix,
  House,
  LinkSimple,
  Lightning,
  List,
  MagnifyingGlass,
  PencilSimple,
  Plus,
  Question,
  Scales,
  SignOut,
  SquaresFour,
  Storefront,
  X,
} from "@phosphor-icons/react/dist/ssr";

import { UnreadBadge } from "@/components/ui/UnreadBadge";
import { useLiveCount } from "@/components/ui/useLiveCount";

import { logout } from "@/app/actions/auth";
import { NavRow, isActive, type Attention, type NavItem } from "@/components/admin/AdminNav";
import { GlobalSearch } from "@/components/console/GlobalSearch";
import { ClaimStatusDialog, type ClaimView } from "@/components/seller/console/ClaimStatusDialog";
import { ExportDialog } from "@/components/seller/console/ExportDialog";
import { filterActions, quickActions, type QuickAction, type QuickIcon } from "@/components/seller/console/quick-actions-model";
import { StoreNotifications } from "@/components/seller/console/StoreNotifications";

/**
 * The Seller console's frame (Figma Seller Sidebar + top bar, as drawn in
 * Screen/Seller/Overview 8190:20643): the Admin console's shell with a store
 * owner's sections. Same rail width, rows, pills, spacing and drawer below lg —
 * NavRow is the Admin rail's own row.
 *
 * It only shows what this account may open: the server layout passes the
 * approved stores and the account's own claims, and every screen's data comes
 * from owner-only endpoints. Hiding nothing here is a permission.
 */

export type ShellStore = { id: string; name: string; platform: string };
export type ShellCounts = { reviews: number; questions: number; appeals: number };

function sections(store: string): { heading: string | null; items: NavItem[] }[] {
  const base = `/seller/${store}`;
  return [
    { heading: null, items: [{ label: "Overview", Icon: SquaresFour, href: base, exact: true }] },
    {
      heading: "Buyers",
      items: [
        { label: "Reviews", Icon: ChatText, href: `${base}/reviews`, pill: (a) => count(a.reviews) },
        { label: "Questions", Icon: Question, href: `${base}/questions`, pill: (a) => count(a.questions) },
        { label: "Appeals", Icon: Flag, href: `${base}/appeals`, pill: (a) => count(a.appeals) },
      ],
    },
    {
      heading: "Store",
      items: [
        { label: "Products", Icon: Cube, href: `${base}/products` },
        { label: "Insights", Icon: ChartLineUp, href: `${base}/insights` },
        { label: "Store profile", Icon: Storefront, href: `${base}/profile` },
      ],
    },
  ];
}

function footer(store: string): NavItem[] {
  return [
    { label: "Public page", Icon: ArrowSquareOut, href: `/seller/${store}/public` },
    { label: "Seller rules", Icon: Scales, href: `/seller/${store}/rules` },
    { label: "Settings", Icon: GearSix, href: `/seller/${store}/settings` },
  ];
}

function count(n: number | null | undefined) {
  return n && n > 0 ? { text: String(n), tone: "count" as const } : null;
}

const PLATFORM: Record<string, string> = { shopee: "Shopee", lazada: "Lazada", tiktok: "TikTok Shop", other: "Other" };
export const platformLabel = (p: string) => PLATFORM[p] ?? p;

function useOutside(open: boolean, close: () => void) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    function onClick(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) close();
    }
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") close();
    }
    window.addEventListener("mousedown", onClick);
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("mousedown", onClick);
      window.removeEventListener("keydown", onKey);
    };
  }, [open, close]);
  return ref;
}

/**
 * Menu/Store/Switcher (8212:23238): the stores this account runs, a claim still
 * in review (opens its Claim status), and "Claim another store".
 */
function StoreSwitcher({
  store,
  stores,
  claims,
  viewer,
  onClaim,
}: {
  store: ShellStore;
  stores: ShellStore[];
  claims: ClaimView[];
  viewer: string;
  onClaim: (c: ClaimView) => void;
}) {
  const [open, setOpen] = useState(false);
  const ref = useOutside(open, () => setOpen(false));
  return (
    <div ref={ref} className="relative">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        aria-haspopup="menu"
        aria-label={`Store: ${store.name}. Switch store`}
        className="flex w-full items-center gap-[10px] rounded-[10px] px-1 py-[5px] text-left hover:bg-[var(--surface-card)]/60 focus-visible:outline focus-visible:outline-2 focus-visible:outline-[var(--accent-primary)]"
      >
        {/* Screen/Seller/Overview (8190:20643): the store's own initial on a
            grey tile — this is the store's console, not Bluntly's. */}
        <span aria-hidden="true" className="grid size-8 shrink-0 place-items-center rounded-[9px] bg-[var(--base-gray-200)] text-[16px] font-semibold leading-none text-[var(--text-primary)]">
          {store.name.trim().charAt(0).toUpperCase() || "S"}
        </span>
        <span className="min-w-0 flex-1">
          <span className="block truncate text-[14px] font-semibold leading-none">{store.name}</span>
          <span className="mt-0.5 block truncate text-[10px] leading-none text-[var(--text-secondary)]">
            Store owner · {platformLabel(store.platform)}
          </span>
        </span>
        <CaretUpDown size={16} className="shrink-0 text-[var(--text-secondary)]" />
      </button>
      {open ? (
        <div
          role="menu"
          aria-label="Your stores"
          className="absolute left-0 right-0 top-[calc(100%+4px)] z-40 rounded-[12px] border border-[var(--border-subtle)] bg-[var(--surface-card)] py-1 shadow-[var(--shadow-modal)]"
        >
          {stores.map((s) => (
            <Link
              key={s.id}
              role="menuitemradio"
              aria-checked={s.id === store.id}
              href={`/seller/${s.id}`}
              onClick={() => setOpen(false)}
              className="flex items-center gap-2 px-3 py-2 text-[12px] leading-none hover:bg-[var(--surface-app)]"
            >
              <span className={`size-1.5 rounded-full ${s.id === store.id ? "bg-[var(--accent-primary)]" : "bg-transparent"}`} aria-hidden />
              {s.name} · {platformLabel(s.platform)}
            </Link>
          ))}
          {claims.map((c) => (
            <button
              key={c.id}
              type="button"
              role="menuitem"
              onClick={() => {
                setOpen(false);
                onClaim(c);
              }}
              className="flex w-full items-center gap-2 px-3 py-2 text-left text-[12px] leading-none text-[var(--text-secondary)] hover:bg-[var(--surface-app)]"
            >
              <span className="size-1.5 rounded-full" aria-hidden />
              {c.storeName} · {platformLabel(c.platform)} (in review)
            </button>
          ))}
          <Link
            role="menuitem"
            href="/search?tab=sellers"
            className="flex items-center gap-2 border-t border-[var(--border-subtle)] px-3 py-2 text-[12px] leading-none hover:bg-[var(--surface-app)]"
          >
            <Plus size={14} aria-hidden /> Claim another store
          </Link>
          <p className="truncate border-t border-[var(--border-subtle)] px-3 pb-1.5 pt-2 text-[12px] leading-none text-[var(--text-secondary)]">
            Signed in as <span className="font-medium text-[var(--text-primary)]">{viewer}</span>
          </p>
          <Link role="menuitem" href="/feed" className="flex items-center gap-2 px-3 py-2 text-[12px] leading-none hover:bg-[var(--surface-app)]">
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

const QUICK_ICONS: Record<QuickIcon, typeof ChatText> = {
  review: ChatText,
  question: Question,
  flag: Flag,
  pencil: PencilSimple,
  link: LinkSimple,
  download: DownloadSimple,
};

/**
 * Overlay/Store/QuickActions (8212:23261): ⌘K or the rail button opens a
 * centred command palette (560px): a search box over what is waiting (each
 * count opens its own screen) and the frame's actions; ↑ / ↓ move, Enter opens,
 * Escape closes. Items come from quick-actions-model.ts.
 */
function QuickActions({ store, counts }: { store: string; counts: ShellCounts }) {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [active, setActive] = useState(0);
  const [exporting, setExporting] = useState(false);
  const ref = useOutside(open, () => setOpen(false));
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setOpen((o) => !o);
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);
  const items = filterActions(quickActions(store, counts), query);
  const at = Math.min(active, Math.max(0, items.length - 1));

  function toggle(next: boolean) {
    setOpen(next);
    setQuery("");
    setActive(0);
  }

  function run(item: QuickAction) {
    toggle(false);
    if (item.opens === "export") setExporting(true);
    else if (item.href) router.push(item.href);
  }

  function onKeyDown(e: React.KeyboardEvent) {
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault();
      if (items.length) setActive((at + (e.key === "ArrowDown" ? 1 : items.length - 1)) % items.length);
    } else if (e.key === "Enter" && items[at]) {
      e.preventDefault();
      run(items[at]);
    } else if (e.key === "Escape") {
      toggle(false);
    }
  }

  return (
    <div ref={ref} className="relative">
      <button
        type="button"
        onClick={() => toggle(!open)}
        aria-expanded={open}
        aria-haspopup="dialog"
        className="flex w-full items-center gap-2 rounded-[10px] border border-[var(--border-subtle)] bg-[var(--surface-card)] py-[7px] pl-[10px] pr-2 text-left focus-visible:outline focus-visible:outline-2 focus-visible:outline-[var(--accent-primary)]"
      >
        <Lightning size={16} className="shrink-0" />
        <span className="flex-1 text-[12px] font-medium leading-none">Quick actions</span>
        <kbd className="rounded-[6px] bg-[var(--surface-app)] px-[6px] py-px font-sans text-[10px] leading-none text-[var(--text-secondary)]">⌘K</kbd>
      </button>
      {open ? (
        <div
          role="dialog"
          aria-label="Quick actions"
          onKeyDown={onKeyDown}
          className="fixed left-1/2 top-[12vh] z-50 w-[560px] max-w-[calc(100vw-32px)] -translate-x-1/2 overflow-hidden rounded-[16px] border border-[var(--border-subtle)] bg-[var(--surface-card)] shadow-[var(--shadow-modal)]"
        >
          <label className="flex items-center gap-3 border-b border-[var(--border-subtle)] px-5 py-4">
            <MagnifyingGlass size={18} aria-hidden className="shrink-0 text-[var(--text-secondary)]" />
            <span className="sr-only">Search actions</span>
            <input
              autoFocus
              role="combobox"
              aria-expanded
              aria-controls="quick-actions-list"
              aria-activedescendant={items[at] ? `qa-${items[at].key}` : undefined}
              value={query}
              onChange={(e) => {
                setQuery(e.target.value);
                setActive(0);
              }}
              placeholder="Type a command or search…"
              className="console-field min-w-0 flex-1 bg-transparent text-[14px] placeholder:text-[var(--text-secondary)]"
            />
            <kbd className="rounded-[6px] bg-[var(--surface-app)] px-[6px] py-[2px] font-sans text-[10px] leading-none text-[var(--text-secondary)]">esc</kbd>
          </label>
          <ul id="quick-actions-list" role="listbox" aria-label="Quick actions" className="max-h-[min(420px,60vh)] overflow-y-auto px-2 pb-2">
            {items.length === 0 ? (
              <li role="presentation" className="px-3 py-4 text-[14px] text-[var(--text-secondary)]">
                No action matches &ldquo;{query.trim()}&rdquo;.
              </li>
            ) : null}
            {items.map((item, i) => {
              const heading = i === 0 || items[i - 1].group !== item.group ? item.group : null;
              const Icon = QUICK_ICONS[item.icon];
              return (
                <li key={item.key} role="presentation">
                  {heading ? (
                    <span role="presentation" className="block px-3 pb-2 pt-4 text-[12px] uppercase leading-none tracking-[0.02em] text-[var(--text-secondary)]">
                      {heading}
                    </span>
                  ) : null}
                  <div
                    id={`qa-${item.key}`}
                    role="option"
                    aria-selected={i === at}
                    // Real movement only: a list that re-filters under a still cursor must not steal the keyboard selection.
                    onMouseMove={() => i !== at && setActive(i)}
                    onMouseDown={(e) => e.preventDefault()}
                    onClick={() => run(item)}
                    className={`flex h-[42px] cursor-pointer items-center gap-3 rounded-[8px] px-3 text-[14px] leading-none ${i === at ? "bg-[var(--surface-app)]" : ""}`}
                  >
                    <Icon size={16} aria-hidden className="shrink-0" />
                    <span className="flex-1">{item.label}</span>
                    {item.count != null ? <span className="text-[12px] text-[var(--text-secondary)] [font-variant-numeric:tabular-nums]">{item.count}</span> : null}
                  </div>
                </li>
              );
            })}
          </ul>
        </div>
      ) : null}
      {exporting ? <ExportDialog storeId={store} initialPeriod="6m" onClose={() => setExporting(false)} /> : null}
    </div>
  );
}

const TITLES: Record<string, string> = { "": "Overview", reviews: "Reviews", questions: "Questions", appeals: "Appeals", settings: "Settings", rules: "Seller rules", messages: "Messages", products: "Products", insights: "Insights", profile: "Store profile", public: "Public page" };

export function SellerShell({
  store,
  stores,
  claims,
  counts,
  viewer,
  unread = 0,
  messagesUnread = 0,
  children,
}: {
  store: ShellStore;
  stores: ShellStore[];
  claims: ClaimView[];
  counts: ShellCounts;
  viewer: string;
  /** Unread notifications, for the bell's count. */
  unread?: number;
  /** Conversations with an unread reply from the team, for the chat button's count. */
  messagesUnread?: number;
  children: React.ReactNode;
}) {
  const pathname = usePathname() ?? `/seller/${store.id}`;
  const search = useSearchParams()?.toString() ?? "";
  // MQA-032: the icons' counts, read again on every page or conversation opened.
  const liveMessages = useLiveCount(
    messagesUnread,
    `/api/bff/api/v1/conversations/unread?seller_id=${store.id}`,
    (b) => (b as { unread?: number } | null)?.unread,
    `${pathname}?${search}`,
  );
  const liveNotes = useLiveCount(
    unread,
    "/api/bff/api/v1/notifications/unread-count",
    (b) => (b as { count?: number } | null)?.count,
    `${pathname}?${search}`,
  );
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [claim, setClaim] = useState<ClaimView | null>(null);
  const attention: Attention = counts;
  const close = () => setDrawerOpen(false);
  const groups = sections(store.id);
  const rest = pathname.replace(`/seller/${store.id}`, "").replace(/^\//, "").split("/")[0] ?? "";
  const section = TITLES[rest] ?? "Overview";

  const rail = (
    <div className="flex h-full flex-col gap-[14px] px-3 pb-1 pt-3">
      <StoreSwitcher store={store} stores={stores} claims={claims} viewer={viewer} onClaim={setClaim} />
      <QuickActions store={store.id} counts={counts} />
      <nav aria-label="Store sections" className="flex min-h-0 flex-1 flex-col gap-[14px] overflow-y-auto">
        {groups.map((group) => (
          <div key={group.heading ?? "home"} className="flex flex-col gap-[2px]">
            {group.heading ? <p className="h-[18px] px-2 text-[10px] leading-[14px] text-[var(--text-secondary)]">{group.heading}</p> : null}
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
      <ul aria-label="Store" className="flex flex-col gap-[2px]">
        {footer(store.id).map((item) => (
          <li key={item.label}>
            <NavRow item={item} active={isActive(item, pathname)} attention={attention} onNavigate={close} />
          </li>
        ))}
      </ul>
    </div>
  );

  return (
    <div className="flex h-dvh overflow-hidden bg-[var(--surface-app)] p-2 lg:pl-0">
      <aside className="hidden h-full w-[232px] shrink-0 lg:block">{rail}</aside>
      <button
        type="button"
        onClick={() => setDrawerOpen(true)}
        aria-label="Open store navigation"
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
              aria-label="Close store navigation"
              className="absolute right-2 top-2 z-10 grid h-8 w-8 place-items-center rounded-full text-[var(--text-secondary)] hover:bg-[var(--surface-card)]"
            >
              <X size={18} weight="bold" />
            </button>
            {rail}
          </aside>
        </div>
      ) : null}

      <div className="flex min-w-0 flex-1 flex-col overflow-hidden rounded-[16px] border border-[var(--border-subtle)] bg-[var(--surface-card)]">
        <header className="flex h-14 shrink-0 items-center gap-[10px] border-b border-[var(--border-subtle)] pl-6 pr-4">
          <nav aria-label="Breadcrumb" className="flex min-w-0 flex-1 items-center gap-[6px] text-[12px] leading-none">
            <Link href={`/seller/${store.id}`} className="-my-1.5 truncate py-1.5 text-[var(--text-secondary)] hover:text-[var(--text-primary)]">
              {store.name}
            </Link>
            <span className="text-[var(--border-default)]">/</span>
            <span className="font-medium">{section}</span>
          </nav>
          <GlobalSearch
            endpoint={`/api/v1/sellers/${store.id}/search`}
            placeholder="Search your reviews and questions…"
            footer="Searches your store only · Esc to close"
            emptyHint="Try a buyer’s name, words from a review, or a product name."
          />
          <Link
            href={`/seller/${store.id}/messages`}
            aria-label={liveMessages ? `Messages, ${liveMessages} unread` : "Messages"}
            className="relative grid size-9 shrink-0 place-items-center rounded-full border border-[var(--border-subtle)] hover:bg-[var(--surface-app)]"
          >
            <ChatCircleDots size={18} />
            <UnreadBadge count={liveMessages} testId="messages-unread" />
          </Link>
          <StoreNotifications storeId={store.id} unread={liveNotes} />
        </header>
        <main className="relative min-h-0 flex-1 overflow-y-auto px-4 pb-6 pt-5 sm:px-6">{children}</main>
      </div>
      {claim ? <ClaimStatusDialog claim={claim} onClose={() => setClaim(null)} /> : null}
    </div>
  );
}
