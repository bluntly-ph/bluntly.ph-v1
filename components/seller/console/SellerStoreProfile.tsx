import Link from "next/link";
import { CheckCircle, Lock, Plus, Storefront, XCircle } from "@phosphor-icons/react/dist/ssr";

import { Chip } from "@/components/console/Chip";
import { PLATFORM_LABEL, type SellerPlatform } from "@/components/sellers/seller-model";
import { Callout } from "@/components/console/Callout";

import { CHANGE_STATUS, dayMonthYear, linkLabel, monthYear, registrationLabel, type ChangeKind } from "./profile-model";
import { RequestChangeButton } from "./StoreProfileActions";

/**
 * Screen/Seller/StoreProfile (Figma 8209:23011): what buyers see about the
 * store, how its claim was verified, what owning a store allows, and the
 * account's other stores.
 *
 * Nothing here is editable in place: the name and link come from the
 * marketplace and the registration was checked by a moderator, so "Request a
 * change" sends the team a message (Overlay/Store/RequestChange). The
 * registration number is never sent to the browser whole.
 */

type Schemas = import("@/lib/api-types").components["schemas"];
type Profile = Schemas["StoreProfileOut"];
type Store = { id: string; name: string; platform: string };
type Claim = { id: string; storeName: string; platform: string };
type Change = Schemas["StoreChangeOut"];
const KIND_OF: Record<string, ChangeKind> = { display_name: "name", store_url: "link", registration: "registration" };

const CARD = "rounded-[16px] border border-[var(--border-subtle)] p-5";
const market = (p: string) => PLATFORM_LABEL[p as SellerPlatform] ?? p;

export function SellerStoreProfile({
  profile,
  stores,
  claims,
  changes = [],
}: {
  profile: Profile;
  stores: Store[];
  claims: Claim[];
  /** This store's change requests, newest first (MQA-025). */
  changes?: Change[];
}) {
  const pending = changes.filter((c) => c.status === "pending").map((c) => KIND_OF[c.field]);
  const own = profile.ownership;
  const link = linkLabel(profile.store_url);
  const platform = market(profile.platform);
  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center gap-3">
        <h1 className="flex-1 text-[24px] font-semibold leading-none">Store profile</h1>
        <Link href={`/seller/${profile.id}/public`} className="grid h-9 place-items-center rounded-full border border-[var(--text-primary)] px-4 text-[12px] hover:bg-[var(--surface-app)]">
          View public page
        </Link>
      </div>

      <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_22rem]">
        <div className="flex min-w-0 flex-col gap-4">
          <section className={CARD} aria-label="Your store">
            <div className="flex flex-wrap items-center gap-3">
              <span className="grid size-14 shrink-0 place-items-center rounded-[12px] bg-[var(--surface-app)]" aria-hidden>
                <Storefront size={22} />
              </span>
              <span className="flex min-w-0 flex-1 flex-col gap-1">
                <span className="flex flex-wrap items-center gap-2">
                  <span className="text-[20px] font-semibold leading-tight">{profile.display_name}</span>
                  <Chip tone="success">Verified owner</Chip>
                </span>
                <span className="text-[12px] text-[var(--text-secondary)]">
                  {platform} · on Bluntly since {monthYear(profile.on_bluntly_since)}
                </span>
              </span>
              <RequestChangeButton storeId={profile.id} storeName={profile.display_name} platform={platform} pending={pending} />
            </div>
            <dl className="mt-4">
              <Row label="Store name">{profile.display_name}</Row>
              <Row label="Marketplace">{platform}</Row>
              <Row label="Store link">
                {link && profile.store_url ? (
                  <a href={profile.store_url} target="_blank" rel="nofollow noopener noreferrer" className="break-all hover:underline">
                    {link}
                  </a>
                ) : (
                  <span className="text-[var(--text-secondary)]">Not added. Request a change to add it.</span>
                )}
              </Row>
              <Row label="Rating on Bluntly">
                {profile.rating != null ? `${fmt(profile.rating)} / 5 · ` : ""}
                {profile.reviews} review{profile.reviews === 1 ? "" : "s"}
              </Row>
            </dl>
            <Callout className="mt-2">
              Buyers see this on your store page. The name and link come from the marketplace, so a moderator makes any change.
            </Callout>
            {changes.length ? (
              // MQA-025: each change's state, the same one the team sees on the thread.
              <div className="mt-4" aria-label="Requested changes">
                <h3 className="text-[14px] font-semibold">Requested changes</h3>
                <ul className="mt-2 flex flex-col">
                  {changes.map((c) => (
                    <li key={c.id} className="flex flex-wrap items-start gap-x-3 gap-y-1 border-t border-[var(--border-subtle)] py-3 text-[14px]">
                      <span className="flex min-w-0 flex-1 flex-col gap-1">
                        <span className="font-medium">{c.label}</span>
                        <span className="text-[12px] text-[var(--text-secondary)] [overflow-wrap:anywhere]">
                          {c.current_value ? `${c.current_value} → ` : ""}
                          {c.requested_value}
                        </span>
                        {c.decision_note ? <span className="text-[12px] [overflow-wrap:anywhere]">“{c.decision_note}”</span> : null}
                      </span>
                      <span className="flex flex-col items-end gap-1">
                        <Chip tone={CHANGE_STATUS[c.status].tone}>{CHANGE_STATUS[c.status].label}</Chip>
                        <span className="text-[12px] text-[var(--text-secondary)]">{dayMonthYear(c.decided_at ?? c.created_at)}</span>
                      </span>
                    </li>
                  ))}
                </ul>
              </div>
            ) : null}
          </section>

          <section className={CARD} aria-label="Ownership">
            <div className="flex items-start gap-3">
              <span className="flex flex-1 flex-col gap-1">
                <h2 className="text-[16px] font-semibold leading-none">Ownership</h2>
                <span className="text-[12px] text-[var(--text-secondary)]">How your claim was verified</span>
              </span>
              <Chip tone="success">Approved</Chip>
            </div>
            <dl className="mt-4">
              <Row label="Registration">{registrationLabel(own.registration_kind, own.registration_last4) ?? <Missing />}</Row>
              <Row label="Registered business name">{own.registered_business_name ?? <Missing />}</Row>
              <Row label={`Shop name on ${platform}`}>
                {own.marketplace_shop_name ? (
                  <span className="flex flex-wrap items-center gap-2">
                    {own.marketplace_shop_name}
                    {own.shop_name_matches ? <Chip tone="success">Matches</Chip> : own.shop_name_matches === false ? <Chip tone="warning">Differs from the store name</Chip> : null}
                  </span>
                ) : (
                  <Missing />
                )}
              </Row>
              <Row label="Approved">{own.approved_at ? `${dayMonthYear(own.approved_at)} by a moderator` : <Missing />}</Row>
              <Row label="Owner account">{own.owner_name}</Row>
            </dl>
            <Callout className="mt-2" icon={<Lock size={16} aria-hidden />}>
              Only you and moderators see this. The full registration number is never shown.
            </Callout>
          </section>
        </div>

        <div className="flex min-w-0 flex-col gap-4">
          <section className={CARD} aria-label="What owning a store means">
            <h2 className="text-[16px] font-semibold leading-none">What owning a store means</h2>
            <p className="mt-4 text-[11px] font-medium uppercase tracking-[0.06em] text-[var(--text-secondary)]">You can</p>
            <ul className="mt-2 flex flex-col gap-2 text-[14px]">
              {["Respond publicly to reviews", "Answer questions as the store", "Flag a review you think is fake", "See analytics for your store and products"].map((t) => (
                <li key={t} className="flex items-start gap-2">
                  <CheckCircle size={18} weight="fill" aria-hidden className="mt-px shrink-0" /> {t}
                </li>
              ))}
            </ul>
            <p className="mt-4 text-[11px] font-medium uppercase tracking-[0.06em] text-[var(--text-secondary)]">You can’t</p>
            <ul className="mt-2 flex flex-col gap-2 text-[14px]">
              {["Remove, hide or rank reviews", "Vote, write reviews or earn on Bluntly", "Pick a Best Answer"].map((t) => (
                <li key={t} className="flex items-start gap-2">
                  <XCircle size={18} aria-hidden className="mt-px shrink-0" /> {t}
                </li>
              ))}
            </ul>
            <p className="mt-4 text-[12px] text-[var(--text-secondary)]">These limits stay on this account for good, even if you give up the store.</p>
            <Link href={`/seller/${profile.id}/rules`} className="mt-3 inline-block text-[12px] text-[var(--chart-honesty-fund)] hover:underline">
              Read the seller rules
            </Link>
          </section>

          <section className={CARD} aria-label="Your stores">
            <h2 className="text-[16px] font-semibold leading-none">Your stores</h2>
            <p className="mt-1 text-[12px] text-[var(--text-secondary)]">Stores this account runs</p>
            <ul className="mt-2 flex flex-col">
              {stores.map((s) => (
                <li key={s.id} className="flex items-center gap-3 border-t border-[var(--border-subtle)] py-3 first:border-t-0">
                  <span className="grid size-8 shrink-0 place-items-center rounded-[8px] bg-[var(--surface-app)]" aria-hidden>
                    <Storefront size={16} />
                  </span>
                  <span className="flex min-w-0 flex-1 flex-col gap-0.5">
                    <span className="truncate text-[14px] font-medium">{s.name}</span>
                    <span className="text-[12px] text-[var(--text-secondary)]">{market(s.platform)}</span>
                  </span>
                  {s.id === profile.id ? (
                    <Chip tone="muted">Viewing</Chip>
                  ) : (
                    <Link href={`/seller/${s.id}/profile`} className="text-[12px] text-[var(--chart-honesty-fund)] hover:underline">
                      Open
                    </Link>
                  )}
                </li>
              ))}
              {claims.map((c) => (
                <li key={c.id} className="flex items-center gap-3 border-t border-[var(--border-subtle)] py-3">
                  <span className="grid size-8 shrink-0 place-items-center rounded-[8px] bg-[var(--surface-app)]" aria-hidden>
                    <Storefront size={16} />
                  </span>
                  <span className="flex min-w-0 flex-1 flex-col gap-0.5">
                    <span className="truncate text-[14px] font-medium">{c.storeName}</span>
                    <span className="text-[12px] text-[var(--text-secondary)]">{market(c.platform)}</span>
                  </span>
                  <Chip tone="warning">Claim in review</Chip>
                </li>
              ))}
            </ul>
            <Link href="/search?tab=sellers" className="mt-2 inline-flex h-9 items-center gap-1 rounded-full border border-[var(--text-primary)] px-4 text-[12px] hover:bg-[var(--surface-app)]">
              <Plus size={14} aria-hidden /> Claim another store
            </Link>
          </section>
        </div>
      </div>
    </div>
  );
}

const fmt = (v: number) => (Number.isInteger(v) ? String(v) : v.toFixed(1));

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="grid grid-cols-1 gap-1 border-t border-[var(--border-subtle)] py-3 sm:grid-cols-[13rem_minmax(0,1fr)] sm:gap-4">
      <dt className="text-[14px] text-[var(--text-secondary)]">{label}</dt>
      <dd className="min-w-0 text-[14px] font-medium">{children}</dd>
    </div>
  );
}

function Missing() {
  return <span className="font-normal text-[var(--text-secondary)]">Not on file</span>;
}
