"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useState } from "react";
import { CheckCircle, Info, Star, Storefront, WarningCircle, ArrowsClockwise, ArrowSquareOut } from "@phosphor-icons/react/dist/ssr";

import { AdminModal } from "@/components/admin/AdminModal";
import { ConfirmDialog } from "@/components/admin/ConfirmDialog";
import { APPEAL_DEFAULT_SORT, APPEAL_FILTERS, APPEAL_SORTS, CLAIM_DEFAULT_SORT, CLAIM_FILTERS, CLAIM_SORTS, applyAppeals, applyClaims, registrationLabel, registrationNumber } from "@/components/admin/list-models";
import { PersonCell, shortAge } from "@/components/admin/queue/QueueCells";
import { CaseChat, type CaseAttachment, type CaseMessage } from "@/components/admin/sellers/CaseChat";
import { AttachmentCard } from "@/components/messages/Thread";
import { ListControls } from "@/components/console/ListControls";
import { Pagination } from "@/components/console/Pagination";
import { Chip } from "@/components/console/Chip";
import { StoreProductLinks } from "@/components/admin/sellers/StoreProductLinks";
import type { AdminSellerAppeal, AdminSellerClaim, AdminStoreProduct } from "@/lib/sellers";
import { appealKind, appealKindLabel, type AppealKind } from "@/components/seller/console/appeal-kinds";

/**
 * Admin Sellers, built to Figma Screen/Admin/Sellers/Claims (7992:11327) and
 * Appeals (7992:11823), with Overlay/Seller/Claim (7996:11538) and
 * Overlay/Seller/Appeal (7996:11826).
 *
 * Claims: the store, its DTI/SEC registration and business name, the shop name
 * with the §9 match, who claimed it; the modal adds the evidence, a chat with
 * the claimant (cases/claim) and Reject / Approve.
 *
 * Appeals: the store and order, the review's rating, the reviewer, the store's
 * reason and the reviewer's status — Not asked / Waiting / Answered, read from
 * the appeal's substantiation record. The modal shows the appealed review and
 * two threads, Seller (cases/appeal) and Reviewer (cases/appeal-reviewer):
 * staff's first message to the reviewer IS the request to back the review up,
 * and "Remove review" stays locked until it was sent (enforced by the API).
 *
 * Evidence files: the claim form takes text only (Figma ClaimStore draws no
 * upload); files the claimant sends in the case's thread (an Inbox
 * conversation, private bucket) are listed under Evidence and open through a
 * signed link. Sending files from the case chat ("+") is not built.
 */

type Tab = "claims" | "appeals" | "links";

function platformLabel(p: string | null | undefined): string {
  return p ? p[0].toUpperCase() + p.slice(1) : "—";
}

function StoreCell({ name, sub }: { name: string; sub: string }) {
  return (
    <span className="flex items-center gap-[10px]">
      <span aria-hidden className="grid size-8 shrink-0 place-items-center rounded-[8px] bg-[var(--surface-app)] text-[var(--text-secondary)]">
        <Storefront size={16} />
      </span>
      <span className="flex min-w-0 flex-col gap-1 leading-none">
        <span className="truncate">{name}</span>
        <span className="truncate text-[12px] text-[var(--text-secondary)]">{sub}</span>
      </span>
    </span>
  );
}

export function appealState(a: Pick<AdminSellerAppeal, "substantiation_requested_at" | "substantiated_at">): "not_asked" | "waiting" | "answered" {
  if (a.substantiated_at) return "answered";
  if (a.substantiation_requested_at) return "waiting";
  return "not_asked";
}

const STATE = {
  not_asked: { label: "Not asked", Icon: WarningCircle, cls: "text-[var(--accent-primary)]" },
  waiting: { label: "Waiting", Icon: ArrowsClockwise, cls: "text-[var(--chart-honesty-fund)]" },
  answered: { label: "Answered", Icon: CheckCircle, cls: "text-[var(--accent-success)]" },
} as const;

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-center gap-4 border-b border-[var(--border-subtle)] py-3 text-[14px] last:border-b-0">
      <span className="w-[104px] shrink-0 text-[var(--text-secondary)] sm:w-[140px]">{label}</span>
      <span className="min-w-0 flex-1 [overflow-wrap:anywhere]">{children}</span>
    </div>
  );
}

function StoreHeader({ name, url, sellerId }: { name: string; url?: string | null; sellerId: string }) {
  return (
    <div className="flex items-center gap-4">
      <span aria-hidden className="grid size-20 shrink-0 place-items-center rounded-[16px] bg-[var(--surface-app)] text-[var(--text-secondary)]">
        <Storefront size={20} />
      </span>
      <span className="flex min-w-0 flex-1 flex-col gap-1">
        <span className="text-[16px] font-semibold [overflow-wrap:anywhere]">{name}</span>
        {url ? (
          <a href={url} target="_blank" rel="noreferrer nofollow" className="truncate text-[12px] text-[var(--chart-honesty-fund)]">
            {url.replace(/^https?:\/\//, "")}
          </a>
        ) : null}
      </span>
      <Link href={`/sellers/${sellerId}`} target="_blank" className="h-9 shrink-0 rounded-full border border-[var(--text-primary)] px-4 pt-[9px] text-[12px] leading-none">
        Open store
      </Link>
    </div>
  );
}

/**
 * MQA-020: the store's link is on another marketplace than the store (a Shopee
 * store linking to Lazada). The moderator pastes the right link; it is saved
 * as an approved store change (POST /admin/sellers/{id}/details), audited.
 */
function StoreLinkFix({ sellerId, problem, onFixed }: { sellerId: string; problem: string; onFixed: (url: string) => void }) {
  const [value, setValue] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  async function save() {
    setBusy(true);
    setError(null);
    const res = await fetch(`/api/bff/api/v1/admin/sellers/${sellerId}/details`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ field: "store_url", value: value.trim(), note: "Corrected while reviewing the claim." }),
    }).catch(() => null);
    setBusy(false);
    if (res?.ok) return onFixed(value.trim());
    const p = res ? ((await res.json().catch(() => ({}))) as { detail?: unknown }) : {};
    setError(typeof p.detail === "string" ? p.detail : "Couldn't save the link.");
  }
  return (
    <div role="alert" data-testid="store-link-problem" className="flex flex-col gap-2 rounded-[12px] bg-[var(--status-critical-bg)] p-3 text-[13px]">
      <p className="flex items-start gap-1.5 text-[var(--status-critical-fg)]">
        <WarningCircle size={16} weight="fill" aria-hidden className="mt-px shrink-0" /> {problem}
      </p>
      <div className="flex flex-wrap items-center gap-2">
        <label htmlFor="store-link-fix" className="sr-only">
          The store&rsquo;s link on its marketplace
        </label>
        <input
          id="store-link-fix"
          value={value}
          onChange={(e) => setValue(e.target.value)}
          placeholder="Paste the store's link on its marketplace"
          className="h-8 min-w-0 flex-1 rounded-full border border-[var(--line-hairline-30)] bg-[var(--surface-card)] px-3 text-[12px] outline-none focus:border-[var(--accent-primary)]"
        />
        <button type="button" disabled={busy || value.trim().length < 8} onClick={() => void save()} className="h-8 rounded-full bg-[var(--text-primary)] px-3 text-[12px] text-[var(--surface-card)] disabled:opacity-50">
          {busy ? "Saving…" : "Save link"}
        </button>
      </div>
      {error ? <p className="text-[12px] text-[var(--accent-danger)]">{error}</p> : null}
    </div>
  );
}

async function post(url: string, body: object): Promise<string | null> {
  const res = await fetch(`/api/bff/api/v1${url}`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(body) }).catch(() => null);
  if (!res) return "Couldn't reach the server.";
  if (res.ok) return null;
  const p = (await res.json().catch(() => ({}))) as { detail?: unknown };
  return typeof p.detail === "string" ? p.detail : "Couldn't record that.";
}

function ClaimModal({ claim, onClose }: { claim: AdminSellerClaim; onClose: () => void }) {
  const router = useRouter();
  // Figma 7996:11538 lists the claimant's files under Evidence: the ones sent in the case's thread.
  const [files, setFiles] = useState<{ id: string; at: string; attachment: CaseAttachment }[]>([]);
  const [now] = useState(() => Date.now());
  const onMessages = useCallback((messages: CaseMessage[]) => {
    setFiles(messages.flatMap((m) => (!m.from_staff && m.attachment ? [{ id: m.id, at: m.sent_at, attachment: m.attachment }] : [])));
  }, []);
  const [confirm, setConfirm] = useState<"approve" | "reject" | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // MQA-020: a store whose link is on another marketplace is not approved
  // until the link is corrected (the API refuses it too).
  const [fixedUrl, setFixedUrl] = useState<string | null>(null);
  const blocked = Boolean(claim.link_problem) && !fixedUrl;
  const name = claim.claimant?.display_name ?? claim.claimant?.username ?? "Member";
  async function decide(decision: "approve" | "reject") {
    setBusy(true);
    const err = await post(`/admin/seller-claims/${claim.id}/decision`, { decision });
    setBusy(false);
    if (err) return setError(err);
    setConfirm(null);
    onClose();
    router.refresh();
  }
  return (
    <AdminModal title="Review claim" onClose={onClose}>
      <div className="grid grid-cols-[minmax(0,1fr)] md:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
        <div className="flex flex-col gap-5 px-6 py-5 md:border-r md:border-[var(--border-subtle)]">
          <StoreHeader name={claim.seller_display_name ?? "Store"} url={fixedUrl ?? claim.store_url} sellerId={claim.seller_id} />
          {claim.link_problem && !fixedUrl ? (
            <StoreLinkFix sellerId={claim.seller_id} problem={claim.link_problem} onFixed={setFixedUrl} />
          ) : null}
          <div>
            <Row label={`${(claim.registration_kind ?? "dti").toUpperCase()} number`}>{registrationNumber(claim.registration_kind, claim.registration_number)}</Row>
            <Row label="Business name">{claim.registered_business_name ?? "—"}</Row>
            <Row label="Shop name">
              <span className="flex flex-wrap items-center gap-x-2 gap-y-1">
                {claim.shop_name_matches ? <CheckCircle size={16} weight="fill" className="text-[var(--accent-success)]" aria-hidden /> : <WarningCircle size={16} weight="fill" className="text-[var(--accent-danger)]" aria-hidden />}
                {claim.marketplace_shop_name ?? "—"}
                <span className="text-[12px] text-[var(--text-secondary)]">{claim.shop_name_matches ? "Matches store" : "Doesn't match the store"}</span>
              </span>
            </Row>
            <Row label="Claimed by">
              <PersonCell name={name} stage={claim.claimant?.trust_stage} levelName={claim.claimant?.trust_level_name} href={claim.claimant ? `/admin/people/${claim.claimant.id}` : undefined} />
            </Row>
          </div>
          <div>
            <p className="text-[12px] text-[var(--text-secondary)]">Evidence</p>
            <p className="mt-1 whitespace-pre-line text-[14px] leading-[1.55]">{claim.evidence || "No evidence was written."}</p>
            {files.length ? (
              <ul className="mt-2 flex flex-col gap-1" aria-label="Files from the claimant">
                {files.map((f) => (
                  <li key={f.id}>
                    <AttachmentCard {...f.attachment} at={f.at} now={now} />
                  </li>
                ))}
              </ul>
            ) : null}
          </div>
        </div>
        <CaseChat kind="claim" caseId={claim.id} opened={claim.created_at} openedLabel="Claim submitted" partyName={name} onMessages={onMessages} />
      </div>
      <div className="flex items-center gap-3 border-t border-[var(--border-subtle)] px-6 py-4">
        <button type="button" onClick={() => setConfirm("reject")} className="h-9 rounded-full border border-[var(--text-primary)] px-4 text-[12px]">
          Reject
        </button>
        <button
          type="button"
          disabled={blocked}
          title={blocked ? "Correct the store's link first" : undefined}
          onClick={() => setConfirm("approve")}
          className="h-9 rounded-full bg-[var(--accent-primary)] px-4 text-[12px] text-white disabled:opacity-50"
        >
          Approve
        </button>
        {blocked ? <span className="text-[12px] text-[var(--text-secondary)]">Correct the store’s link to approve.</span> : null}
      </div>
      <ConfirmDialog
        open={confirm !== null}
        title={confirm === "approve" ? "Approve this claim?" : "Reject this claim?"}
        confirmLabel={confirm === "approve" ? "Confirm approval" : "Confirm rejection"}
        busy={busy}
        tone={confirm === "approve" ? "primary" : "danger"}
        error={error}
        onConfirm={() => confirm && void decide(confirm)}
        onClose={() => setConfirm(null)}
      >
        {confirm === "approve"
          ? `${name} becomes this store's owner: they answer for it and can no longer vote anywhere (§9).`
          : `${name} is told the claim was not accepted. The store stays unclaimed.`}
      </ConfirmDialog>
    </AdminModal>
  );
}

function AppealModal({ appeal, now, onClose }: { appeal: AdminSellerAppeal; now: number; onClose: () => void }) {
  const router = useRouter();
  const [thread, setThread] = useState<"appeal" | "appeal-reviewer">("appeal-reviewer");
  const [asked, setAsked] = useState(appealState(appeal) !== "not_asked");
  const [confirm, setConfirm] = useState<"uphold" | "dismiss" | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const state = asked && appealState(appeal) === "not_asked" ? "waiting" : appealState(appeal);
  const s = STATE[state];
  const reviewer = appeal.reviewer?.display_name ?? appeal.reviewer?.username ?? "the reviewer";
  async function decide(decision: "uphold" | "dismiss") {
    setBusy(true);
    const err = await post(`/admin/seller-review-appeals/${appeal.id}/decision`, { decision });
    setBusy(false);
    if (err) return setError(err);
    setConfirm(null);
    onClose();
    router.refresh();
  }
  return (
    <AdminModal title="Review appeal" onClose={onClose}>
      <div className="grid grid-cols-[minmax(0,1fr)] md:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
        <div className="flex flex-col gap-5 px-6 py-5 md:border-r md:border-[var(--border-subtle)]">
          <StoreHeader name={appeal.seller_name ?? "Store"} url={appeal.store_url} sellerId={appeal.seller_id} />
          <div className="rounded-[16px] border border-[var(--border-subtle)] p-4">
            <p className="flex items-center text-[12px]">
              <span className="flex-1 text-[var(--chart-honesty-fund)]">Appealed review</span>
              <Link href={`/sellers/${appeal.seller_id}#review-${appeal.seller_review_id}`} target="_blank" className="flex items-center gap-1 text-[14px] text-[var(--chart-honesty-fund)]">
                Open review <ArrowSquareOut size={14} aria-hidden />
              </Link>
            </p>
            <div className="mt-2 flex items-center">
              <span className="flex-1">
                <PersonCell name={reviewer} stage={appeal.reviewer?.trust_stage} levelName={appeal.reviewer?.trust_level_name} href={appeal.reviewer ? `/admin/people/${appeal.reviewer.id}` : undefined} />
              </span>
              <span className="flex items-center gap-1 text-[14px]">
                <Star size={16} weight="fill" className="text-[var(--accent-danger)]" aria-hidden /> {appeal.review_rating ?? "—"}
              </span>
            </div>
            <p className="mt-3 whitespace-pre-line text-[14px] leading-[1.55]">{appeal.review_comment || appeal.review_title || "No written review."}</p>
            <p className="mt-2 text-[12px] text-[var(--text-secondary)]" suppressHydrationWarning>
              Order ID {appeal.order_id ?? "not given"}
              {appeal.review_created_at ? ` · Posted ${shortAge(appeal.review_created_at, now)} ago` : ""}
            </p>
          </div>
          <div>
            <p className="flex flex-wrap items-center gap-2 text-[12px] text-[var(--text-secondary)]">
              Seller&apos;s flag <Chip tone="warning">{appealKindLabel(appeal.kind)}</Chip>
            </p>
            <p className="mt-1 whitespace-pre-line text-[14px] leading-[1.55] [overflow-wrap:anywhere]">{appeal.reason}</p>
            <p className="mt-1 text-[12px] text-[var(--text-secondary)]">{appealKind((appeal.kind as AppealKind) ?? "never_ordered").check}</p>
          </div>
          <div>
            <Row label="Reviewer">
              <span className={`flex items-center gap-1.5 ${s.cls}`} data-testid="appeal-state">
                <s.Icon size={16} aria-hidden />
                <span className="text-[var(--text-primary)]">{state === "not_asked" ? "Not asked yet" : state === "waiting" ? "Asked, waiting" : "Answered"}</span>
              </span>
            </Row>
            <Row label="Filed">
              <span suppressHydrationWarning>{shortAge(appeal.created_at, now)} ago</span>
            </Row>
          </div>
        </div>
        <div className="flex flex-col">
          <div className="border-b border-[var(--border-subtle)] px-6 py-3">
            <div role="tablist" aria-label="Conversation" className="inline-flex gap-[2px] rounded-[10px] bg-[var(--surface-app)] p-[3px]">
              {(["appeal", "appeal-reviewer"] as const).map((k) => (
                <button key={k} role="tab" type="button" aria-selected={thread === k} onClick={() => setThread(k)} className={`rounded-[8px] px-3 py-[5px] text-[14px] ${thread === k ? "bg-[var(--surface-card)] font-medium" : "text-[var(--text-secondary)]"}`}>
                  {k === "appeal" ? "Seller" : "Reviewer"}
                </button>
              ))}
            </div>
          </div>
          <CaseChat
            key={thread}
            kind={thread}
            caseId={appeal.id}
            opened={appeal.created_at}
            openedLabel="Appeal filed"
            partyName={thread === "appeal" ? (appeal.seller_name ?? "the store") : reviewer}
            placeholder={thread === "appeal-reviewer" && state === "not_asked" ? `Ask ${reviewer} to back up the review` : undefined}
            onSent={() => thread === "appeal-reviewer" && setAsked(true)}
          />
        </div>
      </div>
      <div className="flex flex-wrap items-center gap-3 border-t border-[var(--border-subtle)] px-6 py-4">
        <span className="flex flex-1 items-center gap-1.5 text-[12px] text-[var(--text-secondary)]">
          {state === "not_asked" ? (
            <>
              <WarningCircle size={14} className="text-[var(--accent-primary)]" aria-hidden /> Ask the reviewer first to unlock removal
            </>
          ) : (
            <>
              <Info size={14} aria-hidden /> Removing the review takes it off the store&apos;s page and numbers
            </>
          )}
        </span>
        <button type="button" onClick={() => setConfirm("dismiss")} className="h-9 rounded-full border border-[var(--text-primary)] px-4 text-[12px]">
          Dismiss
        </button>
        <button type="button" disabled={state === "not_asked"} onClick={() => setConfirm("uphold")} className="h-9 rounded-full bg-[var(--accent-primary)] px-4 text-[12px] text-white disabled:bg-[var(--disabled-surface)] disabled:text-[var(--disabled-text)]">
          Remove review
        </button>
      </div>
      <ConfirmDialog
        open={confirm !== null}
        title={confirm === "uphold" ? "Remove this review?" : "Dismiss this appeal?"}
        confirmLabel={confirm === "uphold" ? "Remove review" : "Dismiss appeal"}
        busy={busy}
        tone={confirm === "uphold" ? "danger" : "primary"}
        error={error}
        onConfirm={() => confirm && void decide(confirm)}
        onClose={() => setConfirm(null)}
      >
        {confirm === "uphold" ? "The review comes off the store's page and its numbers." : "The review stays up; the store is told its appeal was not accepted."}
      </ConfirmDialog>
    </AdminModal>
  );
}

export function SellersScreen({ tab, query = {}, claims: allClaims, appeals: allAppeals, links = null, page, size: SIZE = 10, now }: { tab: Tab; query?: Record<string, string>; claims: AdminSellerClaim[] | null; appeals: AdminSellerAppeal[] | null; links?: AdminStoreProduct[] | null; page: number; size?: number; now: number }) {
  const [openClaim, setOpenClaim] = useState<AdminSellerClaim | null>(null);
  const [openAppeal, setOpenAppeal] = useState<AdminSellerAppeal | null>(null);
  // Menu/Sellers/Claims/* and Menu/Sellers/Appeals/* (8288:29775–29902): sort, filter, search.
  const claims = allClaims ? applyClaims([...allClaims], query) : null;
  const appeals = allAppeals ? applyAppeals([...allAppeals], query) : null;
  const filtered = Object.keys(query).some((k) => k !== "tab");
  const list = tab === "claims" ? claims : appeals;
  const total = list?.length ?? 0;
  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center gap-3">
        <nav aria-label="Sellers views" className="flex w-fit gap-[2px] rounded-[10px] bg-[var(--surface-app)] p-[3px]">
          {(["claims", "appeals", "links"] as const).map((t) => (
            <Link key={t} href={t === "claims" ? "/admin/sellers" : `/admin/sellers?tab=${t}`} aria-current={tab === t ? "page" : undefined} className={`flex items-center gap-[6px] rounded-[8px] px-3 py-[5px] leading-none ${tab === t ? "bg-[var(--surface-card)] shadow-[var(--shadow-segment)]" : "text-[var(--text-secondary)] hover:text-[var(--text-primary)]"}`}>
              <span className="text-[14px] font-medium">{t === "claims" ? "Claims" : t === "appeals" ? "Appeals" : "Product links"}</span>
              <span className="text-[12px] text-[var(--text-secondary)]">{(t === "claims" ? allClaims : t === "appeals" ? allAppeals : links)?.length ?? "—"}</span>
            </Link>
          ))}
        </nav>
        <span className="flex-1" />
        {tab === "links" ? null : tab === "claims" ? (
          <ListControls key="claims" basePath="/admin/sellers" params={query} sorts={CLAIM_SORTS} defaultSort={CLAIM_DEFAULT_SORT} filters={CLAIM_FILTERS} search={{ placeholder: "Store, shop name or claimant", label: "Search claims" }} />
        ) : (
          <ListControls key="appeals" basePath="/admin/sellers" params={query} sorts={APPEAL_SORTS} defaultSort={APPEAL_DEFAULT_SORT} filters={APPEAL_FILTERS} search={{ placeholder: "Store, reviewer or reason", label: "Search appeals" }} />
        )}
      </div>

      {tab === "links" ? <StoreProductLinks rows={links} now={now} /> : null}
      <div className={`overflow-x-auto rounded-[16px] border border-[var(--border-subtle)] ${tab === "links" ? "hidden" : ""}`}>
        <table className="w-full min-w-[960px] border-collapse text-left text-[14px]">
          <caption className="sr-only">{tab === "claims" ? "Store claims" : "Review appeals"}</caption>
          <thead className="bg-[var(--surface-app)] text-[12px] text-[var(--text-secondary)]">
            <tr>
              {(tab === "claims" ? ["Store", "Registration", "Shop name", "Claimed by", "Submitted", "Action"] : ["Store", "Rating", "Reviewer", "Reason", "Status", "Filed", "Action"]).map((h) => (
                <th key={h} scope="col" className="h-10 px-3 font-normal">
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {list === null ? (
              <tr><td colSpan={7} className="border-t border-[var(--border-subtle)] px-3 py-10 text-center text-[var(--text-secondary)]">This list could not be loaded.</td></tr>
            ) : list.length === 0 ? (
              <tr><td colSpan={7} className="border-t border-[var(--border-subtle)] px-3 py-10 text-center text-[var(--text-secondary)]">{filtered ? "Nothing matches these filters." : tab === "claims" ? "No claim is waiting." : "No appeal is open."}</td></tr>
            ) : tab === "claims" ? (
              (claims ?? []).slice((page - 1) * SIZE, page * SIZE).map((c) => {
                const name = c.claimant?.display_name ?? c.claimant?.username ?? "Member";
                return (
                  <tr key={c.id} data-testid="claim-row" className="group border-t border-[var(--border-subtle)] hover:bg-[var(--surface-app)]">
                    <td className="px-3 py-[10px]"><StoreCell name={c.seller_display_name ?? "Store"} sub={platformLabel(c.seller_platform)} /></td>
                    <td className="px-3">
                      <span className="flex flex-col gap-1 leading-4 [&>:first-child]:leading-5">
                        <span>{registrationLabel(c.registration_kind, c.registration_number)}</span>
                        <span className="text-[12px] text-[var(--text-secondary)]">{c.registered_business_name ?? ""}</span>
                      </span>
                    </td>
                    <td className="px-3">
                      <span className="flex items-center gap-2" title={c.shop_name_matches ? "Matches this store" : "Does not match this store's name"}>
                        {c.shop_name_matches ? <CheckCircle size={14} weight="fill" className="text-[var(--accent-success)]" aria-label="Matches" /> : <WarningCircle size={14} weight="fill" className="text-[var(--accent-danger)]" aria-label="Doesn't match" />}
                        {c.marketplace_shop_name ?? "—"}
                      </span>
                    </td>
                    <td className="px-3"><PersonCell name={name} stage={c.claimant?.trust_stage} levelName={c.claimant?.trust_level_name} href={c.claimant ? `/admin/people/${c.claimant.id}` : undefined} /></td>
                    <td className="px-3 text-[var(--text-secondary)]" suppressHydrationWarning>{shortAge(c.created_at, now)}</td>
                    <td className="px-3">
                      <button type="button" onClick={() => setOpenClaim(c)} className="h-7 rounded-full border border-[var(--border-subtle)] bg-[var(--surface-card)] px-3 text-[12px] opacity-0 focus:opacity-100 group-hover:opacity-100 max-md:opacity-100">
                        Review
                      </button>
                    </td>
                  </tr>
                );
              })
            ) : (
              (appeals ?? []).slice((page - 1) * SIZE, page * SIZE).map((a) => {
                const s = STATE[appealState(a)];
                const reviewer = a.reviewer?.display_name ?? a.reviewer?.username ?? "Member";
                return (
                  <tr key={a.id} data-testid="appeal-row" className="group border-t border-[var(--border-subtle)] hover:bg-[var(--surface-app)]">
                    <td className="px-3 py-[10px]"><StoreCell name={a.seller_name ?? "Store"} sub={a.order_id ? `Order ${a.order_id}` : "No order ID"} /></td>
                    <td className="px-3">
                      <span className="flex items-center gap-1"><Star size={16} weight="fill" className="text-[var(--accent-danger)]" aria-hidden />{a.review_rating ?? "—"}</span>
                    </td>
                    <td className="px-3"><PersonCell name={reviewer} stage={a.reviewer?.trust_stage} levelName={a.reviewer?.trust_level_name} href={a.reviewer ? `/admin/people/${a.reviewer.id}` : undefined} /></td>
                    <td className="max-w-[260px] px-3" title={a.reason}>
                      <span className="flex min-w-0 flex-col gap-1">
                        <span className="text-[12px] text-[var(--text-secondary)]">{appealKindLabel(a.kind)}</span>
                        <span className="truncate">{a.reason}</span>
                      </span>
                    </td>
                    <td className="px-3"><span className={`flex items-center gap-1.5 ${s.cls}`}><s.Icon size={16} aria-hidden /><span className="text-[var(--text-primary)]">{s.label}</span></span></td>
                    <td className="px-3 text-[var(--text-secondary)]" suppressHydrationWarning>{shortAge(a.created_at, now)}</td>
                    <td className="px-3">
                      <button type="button" onClick={() => setOpenAppeal(a)} className="h-7 rounded-full border border-[var(--border-subtle)] bg-[var(--surface-card)] px-3 text-[12px] opacity-0 focus:opacity-100 group-hover:opacity-100 max-md:opacity-100">
                        Review
                      </button>
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>
      {tab === "links" ? null : (
        <Pagination page={page} size={SIZE} total={total} basePath="/admin/sellers" query={query} label="Seller pages" />
      )}
      {openClaim ? <ClaimModal claim={openClaim} onClose={() => setOpenClaim(null)} /> : null}
      {openAppeal ? <AppealModal appeal={openAppeal} now={now} onClose={() => setOpenAppeal(null)} /> : null}
    </div>
  );
}
