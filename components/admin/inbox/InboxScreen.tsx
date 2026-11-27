"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import {
  ArrowLeft,
  ArrowsDownUp,
  CaretDown,
  Check,
  DotsThree,
  MagnifyingGlass,
  SlidersHorizontal,
} from "@phosphor-icons/react/dist/ssr";

import { ConfirmDialog } from "@/components/admin/ConfirmDialog";
import { TrustMark } from "@/components/admin/queue/QueueCells";
import { Chip } from "@/components/console/Chip";
import { ICON_BUTTON, MENU, usePopover } from "@/components/console/popover";
import { Pagination } from "@/components/console/Pagination";
import {
  TOPIC_LABEL,
  activeInboxFilters,
  agoCompact,
  closedNote,
  firstName,
  inboxHref,
  previewLine,
  staffTitle,
  threadSignature,
  REPLY_TEMPLATES,
  fillTemplate,
  type Topic,
} from "@/components/messages/messages-model";
import { StoreChangesPanel } from "@/components/admin/inbox/StoreChangesPanel";
import { Composer, ContextBar, TOPIC_ICON, ThreadMessages, postMessage, useLiveThread, useSender } from "@/components/messages/Thread";
import { SEARCH_INPUT, TOOLBAR_SEARCH_STATES } from "@/components/ui/search-styles";
import { MENU_ITEM } from "@/components/console/fields";

/**
 * Screen/Admin/Inbox (Figma 8291:30461; Reviewers 8293:31035, Closed
 * 8293:31377, Empty 8314:32508) with Menu/Inbox/Assign 8294:31112, Status
 * 8294:31153, More 8294:31186, Sort 8294:31225, Filter 8294:31258, Search
 * 8294:31307 and Confirm/Inbox/Close 8294:31318.
 *
 * The list and the selected conversation are the URL (?tab, ?topic, ?status,
 * ?handled, ?q, ?sort, ?page, ?c), read on the server; every action posts to
 * /admin/inbox/{id}/… and refreshes. Below lg the two panes take turns: the
 * list, or the open conversation with a back arrow.
 */

type Schemas = import("@/lib/api-types").components["schemas"];
type InboxList = Schemas["InboxListOut"];
type Conversation = Schemas["ConversationDetailOut"];
type Row = Schemas["ConversationRowOut"];
type StaffOption = Schemas["StaffOptionOut"];
export type InboxQuery = {
  tab: string;
  topic: string;
  status: string;
  handled: string;
  q: string;
  sort: string;
  page: number;
  size: number;
};

const TABS: { key: string; label: string; count: keyof InboxList["counts"] | null }[] = [
  { key: "all", label: "All", count: "all" },
  { key: "sellers", label: "Sellers", count: "sellers" },
  { key: "reviewers", label: "Reviewers", count: "reviewers" },
  { key: "closed", label: "Closed", count: null },
];
const SORTS: [string, string][] = [
  ["latest", "Latest activity"],
  ["waiting", "Waiting longest"],
  ["unread", "Unread first"],
];
const STATUS_LABEL: Record<string, string> = { open: "Open", waiting: "Waiting on them", closed: "Closed" };
const FILTER_TOPICS: Topic[] = ["appeal", "claim", "product", "payout", "review", "report", "account", "other"];

export function InboxScreen({
  list,
  query,
  conversation,
  selectedId,
  explicit,
  staff,
  me,
  now,
}: {
  list: InboxList | null;
  query: InboxQuery;
  conversation: Conversation | null;
  selectedId: string | null;
  /** The URL named the conversation (?c): below lg, show it instead of the list. */
  explicit: boolean;
  staff: StaffOption[];
  me: { id: string; name: string };
  now: number;
}) {
  const items = list?.items ?? [];
  const empty = list !== null && items.length === 0 && !query.q && activeInboxFilters(query) === 0;
  return (
    <div className="flex h-[calc(100%-40px)] min-h-[520px] flex-col gap-4">
      <div className="flex flex-wrap items-center gap-3">
        <nav aria-label="Inbox views" className="flex w-fit flex-wrap gap-[2px] rounded-[10px] bg-[var(--surface-app)] p-[3px]">
          {TABS.map((t) => {
            const active = query.tab === t.key;
            const n = t.count && list ? list.counts[t.count] : null;
            return (
              <Link
                key={t.key}
                href={inboxHref(query, { tab: t.key, c: "" })}
                aria-current={active ? "page" : undefined}
                className={`flex items-center gap-[6px] rounded-[8px] px-3 py-[5px] leading-none ${
                  active ? "bg-[var(--surface-card)] shadow-[var(--shadow-segment)]" : "text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
                }`}
              >
                <span className="text-[14px] font-medium">{t.label}</span>
                {n !== null ? <span className="text-[12px] text-[var(--text-secondary)]">{n}</span> : null}
              </Link>
            );
          })}
        </nav>
        <span className="flex-1" />
        <InboxControls query={query} />
      </div>

      <div className="flex min-h-0 flex-1 overflow-hidden rounded-[16px] border border-[var(--border-subtle)]">
        <section
          aria-label="Conversations"
          className={`${explicit ? "hidden lg:flex" : "flex"} w-full min-w-0 flex-col border-[var(--border-subtle)] lg:w-[340px] lg:shrink-0 lg:border-r`}
        >
          {list === null ? (
            <p className="p-6 text-[14px] text-[var(--text-secondary)]">The inbox couldn’t be loaded. Try again in a moment.</p>
          ) : empty ? (
            <div className="flex flex-1 flex-col items-center justify-center gap-2 p-8 text-center" data-testid="inbox-empty">
              <p className="text-[16px] font-semibold">{query.tab === "closed" ? "Nothing closed yet" : "You’re all caught up"}</p>
              <p className="max-w-[260px] text-[12px] text-[var(--text-secondary)]">
                {query.tab === "closed" ? "Closed conversations show up here." : "New messages from sellers and reviewers show up here."}
              </p>
            </div>
          ) : items.length === 0 ? (
            <div className="flex flex-1 flex-col items-center justify-center gap-2 p-8 text-center">
              <p className="text-[14px] font-medium">No conversation matches</p>
              <Link href={inboxHref(query, { topic: "", status: "", handled: "", q: "" })} className="text-[12px] text-[var(--chart-honesty-fund)] hover:underline">
                Clear search and filters
              </Link>
            </div>
          ) : (
            <ul className="flex min-h-0 flex-1 flex-col gap-1 overflow-y-auto p-2">
              {items.map((row) => (
                <InboxRow key={row.id} row={row} active={row.id === selectedId} href={inboxHref(query, { page: query.page, c: row.id })} now={now} />
              ))}
            </ul>
          )}
          {list && list.total > query.size ? (
            <div className="border-t border-[var(--border-subtle)] px-3 py-2">
              <Pagination
                page={query.page}
                size={query.size}
                total={list.total}
                basePath="/admin/inbox"
                query={Object.fromEntries(
                  Object.entries({ tab: query.tab === "all" ? "" : query.tab, topic: query.topic, status: query.status, handled: query.handled, q: query.q, sort: query.sort === "latest" ? "" : query.sort }).filter(([, v]) => v),
                )}
                label="Inbox pages"
              />
            </div>
          ) : null}
        </section>

        <section aria-label="Conversation" className={`${explicit ? "flex" : "hidden lg:flex"} min-w-0 flex-1 flex-col`}>
          {conversation ? (
            <InboxThread key={conversation.id} conversation={conversation} staff={staff} me={me} now={now} backHref={inboxHref(query, { page: query.page, c: "" })} />
          ) : (
            <div className="flex flex-1 flex-col items-center justify-center gap-2 p-8 text-center">
              <p className="text-[16px] font-semibold">No conversation open</p>
              <p className="text-[12px] text-[var(--text-secondary)]">
                {items.length ? "Pick one on the left." : "Pick one on the left when something comes in."}
              </p>
            </div>
          )}
        </section>
      </div>
    </div>
  );
}

function InboxRow({ row, active, href, now }: { row: Row; active: boolean; href: string; now: number }) {
  const Icon = TOPIC_ICON[row.topic as Topic] ?? TOPIC_ICON.other;
  return (
    <li>
      <Link
        href={href}
        scroll={false}
        aria-current={active ? "true" : undefined}
        data-testid="inbox-row"
        className={`flex gap-3 rounded-[12px] px-3 py-3 ${active ? "bg-[var(--surface-app)]" : "hover:bg-[var(--surface-app)]"}`}
      >
        <span
          aria-hidden
          className={`grid size-8 shrink-0 place-items-center rounded-full ${active ? "bg-[var(--status-high-bg)] text-[var(--accent-primary)]" : "bg-[var(--surface-app)]"}`}
        >
          <Icon size={16} />
        </span>
        <span className="flex min-w-0 flex-1 flex-col gap-1 leading-none">
          <span className="flex items-start gap-2">
            <span className={`min-w-0 flex-1 truncate text-[14px] ${row.unread ? "font-semibold" : "font-medium"}`}>{staffTitle(row)}</span>
            <span className="shrink-0 text-[11px] text-[var(--text-secondary)]" suppressHydrationWarning>
              {agoCompact(row.last_message_at, now)}
            </span>
          </span>
          <span className="flex items-center gap-2">
            <span className="min-w-0 flex-1 truncate text-[12px] text-[var(--text-secondary)]">{previewLine(row, "staff")}</span>
            {row.unread ? (
              <span className="size-[7px] shrink-0 rounded-full bg-[var(--accent-primary)]">
                <span className="sr-only">Unread</span>
              </span>
            ) : null}
          </span>
        </span>
      </Link>
    </li>
  );
}

function InboxControls({ query }: { query: InboxQuery }) {
  const router = useRouter();
  const { open: sortOpen, setOpen: setSortOpen, ref: sortRef } = usePopover();
  const { open: filterOpen, setOpen: setFilterOpen, ref: filterRef } = usePopover();
  const { open: searchOpen, setOpen: setSearchOpen, ref: searchRef } = usePopover();
  const [q, setQ] = useState(query.q);
  const active = activeInboxFilters(query);
  const chip = (on: boolean) =>
    `rounded-full border px-3 py-[6px] text-[12px] ${on ? "border-[var(--text-primary)] bg-[var(--text-primary)] text-[var(--surface-card)]" : "border-[var(--border-subtle)] hover:border-[var(--text-secondary)]"}`;
  return (
    <div className="flex items-center gap-1">
      <div ref={sortRef} className="relative">
        <button type="button" onClick={() => setSortOpen(!sortOpen)} aria-expanded={sortOpen} aria-label="Sort" className={ICON_BUTTON}>
          <ArrowsDownUp size={18} />
        </button>
        {sortOpen ? (
          <ul className={`${MENU} w-[220px] p-2`} role="menu" aria-label="Sort">
            {SORTS.map(([key, label]) => (
              <li key={key} role="none">
                <Link
                  role="menuitemradio"
                  aria-checked={query.sort === key}
                  href={inboxHref(query, { sort: key })}
                  scroll={false}
                  onClick={() => setSortOpen(false)}
                  className={MENU_ITEM}
                >
                  {label}
                  {query.sort === key ? <Check size={16} aria-hidden /> : null}
                </Link>
              </li>
            ))}
          </ul>
        ) : null}
      </div>
      <div ref={filterRef} className="relative">
        <button
          type="button"
          onClick={() => setFilterOpen(!filterOpen)}
          aria-expanded={filterOpen}
          aria-label={active ? `Filters, ${active} on` : "Filters"}
          className={ICON_BUTTON}
        >
          <SlidersHorizontal size={18} />
          {active ? <span aria-hidden className="absolute right-1 top-1 size-[6px] rounded-full bg-[var(--accent-primary)]" /> : null}
        </button>
        {filterOpen ? (
          <div role="group" aria-label="Filters" className={`${MENU} flex w-[340px] flex-col gap-4 p-4`}>
            <FilterGroup title="Handled by">
              {[
                ["unassigned", "Unassigned"],
                ["me", "Me"],
                ["others", "Others"],
              ].map(([key, label]) => (
                <Link key={key} href={inboxHref(query, { handled: query.handled === key ? "" : key })} scroll={false} className={chip(query.handled === key)}>
                  {label}
                </Link>
              ))}
            </FilterGroup>
            <FilterGroup title="Topic">
              {FILTER_TOPICS.map((key) => (
                <Link key={key} href={inboxHref(query, { topic: query.topic === key ? "" : key })} scroll={false} className={chip(query.topic === key)}>
                  {key === "other" ? "Something else" : TOPIC_LABEL[key]}
                </Link>
              ))}
            </FilterGroup>
            {query.tab !== "closed" ? (
              <FilterGroup title="Status">
                {[
                  ["open", "Open"],
                  ["waiting", "Waiting on them"],
                ].map(([key, label]) => (
                  <Link key={key} href={inboxHref(query, { status: query.status === key ? "" : key })} scroll={false} className={chip(query.status === key)}>
                    {label}
                  </Link>
                ))}
              </FilterGroup>
            ) : null}
            <Link
              href={inboxHref(query, { topic: "", status: "", handled: "" })}
              scroll={false}
              onClick={() => setFilterOpen(false)}
              className="self-start border-t border-[var(--border-subtle)] pt-3 text-[14px] text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
            >
              Clear all
            </Link>
          </div>
        ) : null}
      </div>
      <div ref={searchRef} className="relative">
        <button type="button" onClick={() => setSearchOpen(!searchOpen)} aria-expanded={searchOpen} aria-label="Search the inbox" className={ICON_BUTTON}>
          <MagnifyingGlass size={18} />
          {query.q ? <span aria-hidden className="absolute right-1 top-1 size-[6px] rounded-full bg-[var(--accent-primary)]" /> : null}
        </button>
        {searchOpen ? (
          <form
            role="search"
            onSubmit={(e) => {
              e.preventDefault();
              setSearchOpen(false);
              router.push(inboxHref(query, { q: q.trim() }), { scroll: false });
            }}
            className={`${MENU} flex w-[360px] items-center gap-2 p-2`}
          >
            {/* Admin/ToolbarSearch (8270:28869). */}
            <span className={`flex h-9 min-w-0 flex-1 items-center gap-2 rounded-[32px] pl-[14px] pr-3 ${TOOLBAR_SEARCH_STATES}`}>
              <MagnifyingGlass size={16} aria-hidden className="shrink-0 text-[var(--text-secondary)]" />
              <input
                autoFocus
                value={q}
                onChange={(e) => setQ(e.target.value)}
                placeholder="Search names, stores, messages"
                aria-label="Search the inbox"
                className={`${SEARCH_INPUT} h-8 text-[14px] placeholder:text-[var(--text-secondary)]`}
              />
            </span>
            {query.q ? (
              <Link href={inboxHref(query, { q: "" })} scroll={false} onClick={() => setQ("")} className="text-[12px] text-[var(--text-secondary)] hover:text-[var(--text-primary)]">
                Clear
              </Link>
            ) : null}
          </form>
        ) : null}
      </div>
    </div>
  );
}

function FilterGroup({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-2">
      <p className="text-[12px] text-[var(--text-secondary)]">{title}</p>
      <div className="flex flex-wrap gap-2">{children}</div>
    </div>
  );
}

async function act(path: string, body?: unknown): Promise<string | null> {
  try {
    const res = await fetch(`/api/bff/api/v1/admin/inbox/${path}`, {
      method: "POST",
      headers: body === undefined ? undefined : { "content-type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
    if (res.ok) return null;
    const p = (await res.json().catch(() => ({}))) as { detail?: unknown };
    return typeof p.detail === "string" ? p.detail : "That didn’t work. Try again.";
  } catch {
    return "Couldn’t reach the server.";
  }
}

function InboxThread({
  conversation: c,
  staff,
  me,
  now,
  backHref,
}: {
  conversation: Conversation;
  staff: StaffOption[];
  me: { id: string; name: string };
  now: number;
  backHref: string;
}) {
  const router = useRouter();
  const [closing, setClosing] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const sender = useSender((body, file) => postMessage(`/api/v1/admin/inbox/${c.id}/messages`, body, file));
  useLiveThread(`/api/v1/admin/inbox/${c.id}`, threadSignature(c.messages));
  const member = c.member?.name ?? (c.audience === "seller" ? c.seller_name : null) ?? "Member";
  const closed = c.status === "closed";
  const summary = c.member_summary;

  async function run(path: string, body?: unknown) {
    setBusy(true);
    setError(null);
    const err = await act(`${c.id}/${path}`, body);
    setBusy(false);
    if (err) setError(err);
    else router.refresh();
    return err;
  }

  const summaryLine = summary
    ? summary.role === "seller"
      ? [summary.label, summary.store_name].filter(Boolean).join(" · ")
      : [
          summary.label,
          summary.reviews != null ? `${summary.reviews} review${summary.reviews === 1 ? "" : "s"}` : null,
          summary.earned != null ? `₱${Number(summary.earned).toLocaleString("en-PH", { maximumFractionDigits: 2 })} earned` : null,
        ]
          .filter(Boolean)
          .join(" · ")
    : null;

  return (
    <>
      <header className="flex flex-wrap items-center gap-3 border-b border-[var(--border-subtle)] px-5 py-3">
        <Link href={backHref} aria-label="Back to the inbox" className="grid size-8 place-items-center rounded-full hover:bg-[var(--surface-app)] lg:hidden">
          <ArrowLeft size={18} />
        </Link>
        <span aria-hidden className="grid size-8 shrink-0 place-items-center rounded-full bg-[var(--surface-app)] text-[12px] font-medium">
          {member.replace(/^@/, "").slice(0, 1).toUpperCase()}
        </span>
        <span className="flex min-w-0 flex-1 flex-col gap-1 leading-none">
          <span className="truncate text-[16px]">{member}</span>
          {summaryLine ? (
            <span className="flex items-center gap-1 truncate text-[12px] text-[var(--text-secondary)]">
              <TrustMark />
              {summaryLine}
            </span>
          ) : null}
        </span>
        <Chip tone="muted">{c.audience === "seller" ? "Seller" : "Reviewer"}</Chip>
        <AssignMenu value={c.assigned_admin?.id ?? null} staff={staff} me={me} disabled={busy} onPick={(id) => void run("assign", { admin_id: id })} />
        {closed ? null : (
          <StatusMenu
            value={c.status}
            disabled={busy}
            onPick={(s) => (s === "closed" ? setClosing(true) : void run("status", { status: s }))}
          />
        )}
        <MoreMenu
          conversation={c}
          disabled={busy}
          onMove={() => void run("move-to-support")}
          onClose={() => setClosing(true)}
        />
      </header>
      {c.link ? <ContextBar link={c.link} /> : null}
      {c.audience === "seller" ? <StoreChangesPanel key={c.id} conversationId={c.id} /> : null}
      {error || sender.error ? (
        <p role="alert" className="border-b border-[var(--border-subtle)] px-5 py-2 text-[12px] text-[var(--accent-danger)]">
          {error ?? sender.error}
        </p>
      ) : null}
      <div className="min-h-0 flex-1 overflow-y-auto">
        <ThreadMessages
          messages={c.messages}
          viewer={{ id: me.id, side: "staff" }}
          actionsBase={`/api/bff/api/v1/admin/inbox/${c.id}`}
          now={now}
          pending={sender.pending}
          onRetry={sender.retry}
          nameOf={() => (c.audience === "seller" && c.seller_name ? `${member} · ${c.seller_name}` : member)}
        />
      </div>
      {closed ? (
        <div className="flex flex-wrap items-center gap-3 border-t border-[var(--border-subtle)] px-5 py-4" data-testid="inbox-closed">
          <p className="flex-1 text-[12px] text-[var(--text-secondary)]">
            {closedNote(c.closed_by, c.closed_at, { id: me.id, side: "staff" }, member)}
            {c.support_reference ? ` In Queue → Support as ${c.support_reference}.` : ""}
          </p>
          <button
            type="button"
            disabled={busy}
            onClick={() => void run("status", { status: "open" })}
            className="h-9 rounded-full border border-[var(--text-primary)] px-4 text-[12px] disabled:opacity-50"
          >
            Reopen
          </button>
        </div>
      ) : (
        <Composer
          placeholder={`Reply to ${firstName(member)}. They also get it by email.`}
          onSend={sender.send}
          guardTags
          templates={
            c.audience === "seller"
              ? REPLY_TEMPLATES.map((t) => ({
                  label: t.label,
                  text: fillTemplate(t.text, {
                    seller_name: c.member?.name ? firstName(c.member.name) : null,
                    store_name: c.seller_name,
                    platform: c.seller_platform ? `${c.seller_platform.charAt(0).toUpperCase()}${c.seller_platform.slice(1)}` : null,
                    reference: c.reference,
                  }),
                }))
              : undefined
          }
        />
      )}
      <ConfirmDialog
        open={closing}
        title="Close this conversation?"
        confirmLabel="Close conversation"
        busyLabel="Closing…"
        busy={busy}
        error={error}
        onConfirm={() =>
          void run("status", { status: "closed" }).then((err) => {
            if (!err) setClosing(false);
          })
        }
        onClose={() => setClosing(false)}
      >
        <p>{firstName(member)} gets an email that it’s closed.</p>
        <p>If they reply, it opens again in your inbox.</p>
      </ConfirmDialog>
    </>
  );
}

const PILL = "flex h-9 items-center gap-2 rounded-full border border-[var(--text-primary)] px-3 text-[12px] disabled:opacity-50";

function AssignMenu({
  value,
  staff,
  me,
  disabled,
  onPick,
}: {
  value: string | null;
  staff: StaffOption[];
  me: { id: string; name: string };
  disabled: boolean;
  onPick: (id: string | null) => void;
}) {
  const { open, setOpen, ref } = usePopover();
  const others = staff.filter((s) => s.id !== me.id);
  const current = value === null ? "Unassigned" : value === me.id ? "Me" : (staff.find((s) => s.id === value)?.name ?? "Assigned");
  const options: [string | null, string][] = [[null, "Unassigned"], [me.id, `Me (${me.name})`], ...others.map((s) => [s.id, s.name] as [string, string])];
  return (
    <div ref={ref} className="relative">
      <button type="button" disabled={disabled} onClick={() => setOpen(!open)} aria-expanded={open} aria-haspopup="menu" aria-label={`Handled by: ${current}`} className={PILL}>
        {current}
        <CaretDown size={14} aria-hidden />
      </button>
      {open ? (
        <ul role="menu" aria-label="Assign" className={`${MENU} max-h-[280px] w-[220px] overflow-y-auto p-2`}>
          {options.map(([id, label]) => (
            <li key={id ?? "none"} role="none">
              <button
                type="button"
                role="menuitemradio"
                aria-checked={value === id}
                onClick={() => {
                  setOpen(false);
                  if (id !== value) onPick(id);
                }}
                className={MENU_ITEM}
              >
                <span className="truncate">{label}</span>
                {value === id ? <Check size={16} aria-hidden /> : null}
              </button>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}

function StatusMenu({ value, disabled, onPick }: { value: string; disabled: boolean; onPick: (s: string) => void }) {
  const { open, setOpen, ref } = usePopover();
  return (
    <div ref={ref} className="relative">
      <button type="button" disabled={disabled} onClick={() => setOpen(!open)} aria-expanded={open} aria-haspopup="menu" aria-label={`Status: ${STATUS_LABEL[value]}`} className={PILL}>
        {STATUS_LABEL[value] ?? value}
        <CaretDown size={14} aria-hidden />
      </button>
      {open ? (
        <ul role="menu" aria-label="Status" className={`${MENU} w-[220px] p-2`}>
          {["open", "waiting", "closed"].map((s) => (
            <li key={s} role="none">
              <button
                type="button"
                role="menuitemradio"
                aria-checked={value === s}
                onClick={() => {
                  setOpen(false);
                  if (s !== value) onPick(s);
                }}
                className={MENU_ITEM}
              >
                {STATUS_LABEL[s]}
                {value === s ? <Check size={16} aria-hidden /> : null}
              </button>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}

function MoreMenu({
  conversation: c,
  disabled,
  onMove,
  onClose,
}: {
  conversation: Conversation;
  disabled: boolean;
  onMove: () => void;
  onClose: () => void;
}) {
  const { open, setOpen, ref } = usePopover();
  const item = "block w-full rounded-[10px] px-3 py-[10px] text-left text-[14px] hover:bg-[var(--surface-app)]";
  const canMove = c.audience === "seller" && !!c.seller_id && !c.support_reference;
  return (
    <div ref={ref} className="relative">
      <button type="button" disabled={disabled} onClick={() => setOpen(!open)} aria-expanded={open} aria-haspopup="menu" aria-label="More actions" className={ICON_BUTTON}>
        <DotsThree size={20} weight="bold" />
      </button>
      {open ? (
        <ul role="menu" aria-label="More" className={`${MENU} w-[240px] p-2`}>
          {c.seller_id ? (
            <li role="none">
              <Link role="menuitem" href={`/sellers/${c.seller_id}`} className={item} onClick={() => setOpen(false)}>
                View store
              </Link>
            </li>
          ) : null}
          {c.member?.id ? (
            <li role="none">
              <Link role="menuitem" href={`/admin/people/${c.member.id}`} className={item} onClick={() => setOpen(false)}>
                View person
              </Link>
            </li>
          ) : null}
          {canMove ? (
            <li role="none">
              <button
                type="button"
                role="menuitem"
                className={item}
                onClick={() => {
                  setOpen(false);
                  onMove();
                }}
              >
                Move to Queue → Support
              </button>
            </li>
          ) : null}
          {c.status !== "closed" ? (
            <li role="none">
              <button
                type="button"
                role="menuitem"
                className={`${item} text-[var(--accent-danger)]`}
                onClick={() => {
                  setOpen(false);
                  onClose();
                }}
              >
                Close conversation
              </button>
            </li>
          ) : null}
        </ul>
      ) : null}
    </div>
  );
}
