"use client";

import Link from "next/link";
import Image from "next/image";
import { useRouter } from "next/navigation";
import { useRef, useState } from "react";

import { AdminModal } from "@/components/admin/AdminModal";
import { prepareImageForUpload, usablePhoto } from "@/lib/image";
import { FIELD_INPUT_COMPACT } from "@/components/console/fields";
import { Switch } from "@/components/console/Switch";
import { passwordCheck } from "./account-model";
import { EmailChange } from "@/components/account/EmailChange";
import { GiveUpDialog } from "./StoreProfileActions";
import { PREF_ROWS, prefEnabled, withPref, type Prefs } from "./notification-prefs-model";

/**
 * Screen/Seller/Settings (Figma 8218:24151) and Overlay/Store/Account
 * (8232:25342), as far as the product supports them today:
 *
 * - Account: who is signed in, the role, the stores and claims in review, and
 *   "Profile and password" — display name and username through the existing
 *   PATCH /users/me, and Change photo through POST /users/me/avatar. The email is shown masked; "Change email" runs the
 *   verified change (owner decision 2026-10-04, backend 0084: a code to the current and to the new address, then every
 *   other session ends). Change password (Overlay/Store/Account
 *   8232:25342: current, new of at least 10, repeat) goes to POST /users/me/password; an account made with an email
 *   code has no password, and says so instead.
 * - Notifications: the frame's switches, saved on change through PUT
 *   /users/me/notification-prefs (0083) and applied when a notice is queued. Every
 *   notice shows in the app; "Also by email" sends the same ones to the account's
 *   email, and "Weekly summary" is the Monday email (0085, the email outbox). Each
 *   email's footer link turns its channel off without signing in (/unsubscribe).
 * - Need help: Contact support opens New message (Overlay/Store/Chat/New; owner
 *   decision 2026-10-03: messages replace the support request form).
 *
 * - Give up this store: the danger card opens the same confirm as Store profile
 *   (POST /sellers/{id}/give-up; the store goes back to unclaimed).
 *
 * Layout as the frame: Notifications and Account on the left (614px), Need help and
 * Give up on the right (360px); one column on a phone.
 */

type Me = { displayName: string | null; username: string | null; email: string; joined: string; avatarUrl?: string | null; hasPassword?: boolean };


export function SellerSettings({
  storeId,
  storeName,
  prefs,
  stores,
  inReview,
  me,
}: {
  storeId: string;
  storeName: string;
  prefs: Prefs | null;
  stores: string[];
  inReview: string[];
  me: Me;
}) {
  const [account, setAccount] = useState(false);
  const [giveUp, setGiveUp] = useState(false);
  const name = me.displayName || (me.username ? `@${me.username}` : "You");
  return (
    <div className="flex flex-col gap-4">
      <h1 className="text-[24px] font-semibold leading-none">Settings</h1>
      <div className="grid grid-cols-[minmax(0,1fr)] items-start gap-4 lg:grid-cols-[minmax(0,614px)_minmax(0,360px)]">
        <div className="flex min-w-0 flex-col gap-4">
          <Section title="Notifications" sub="In the app, and by email if you choose">
            {prefs ? (
              <NotificationSwitches initial={prefs} />
            ) : (
              <p className="text-[12px] text-[var(--text-secondary)]">Your notification settings couldn&rsquo;t be loaded. Reload the page to try again.</p>
            )}
          </Section>

          <Section title="Account">
            <dl className="grid grid-cols-[140px_minmax(0,1fr)] gap-y-3 text-[14px]">
              <dt className="text-[var(--text-secondary)]">Signed in as</dt>
              <dd>{name}</dd>
              <dt className="text-[var(--text-secondary)]">Role</dt>
              <dd>Store owner</dd>
              <dt className="text-[var(--text-secondary)]">Stores</dt>
              <dd className="[overflow-wrap:anywhere]">
                {[...stores, ...inReview.map((s) => `${s} (in review)`)].join(" · ")}
              </dd>
            </dl>
            <button type="button" onClick={() => setAccount(true)} className="mt-4 h-9 rounded-full border border-[var(--text-primary)] px-4 text-[12px]">
              Profile and password
            </button>
          </Section>
        </div>

        <div className="flex min-w-0 flex-col gap-4">
          <Section title="Need help?" sub="Questions about a review, a flag or your claim go to the Bluntly team.">
            <Link href={`/seller/${storeId}/messages?new=1`} className="inline-block h-9 rounded-full border border-[var(--text-primary)] px-4 text-[12px] leading-9">
              Contact support
            </Link>
          </Section>

          <section aria-labelledby="give-up-h" className="rounded-[16px] border border-[var(--accent-danger)] p-5">
            <h2 id="give-up-h" className="text-[16px] font-semibold leading-none">Give up this store</h2>
            <p className="mt-2 text-[12px] leading-[18px]">
              You stop being the owner of {storeName}. Your past responses and answers stay up. The limits on voting, reviewing and earning stay on your
              account.
            </p>
            <button
              type="button"
              onClick={() => setGiveUp(true)}
              className="mt-4 h-9 max-w-full truncate rounded-full border border-[var(--text-primary)] px-4 text-[12px] hover:bg-[var(--surface-app)]"
            >
              Give up {storeName}
            </button>
          </section>
        </div>
      </div>

      <GiveUpDialog storeId={storeId} storeName={storeName} open={giveUp} onClose={() => setGiveUp(false)} />

      {account ? <AccountModal me={me} storeName={storeName} onClose={() => setAccount(false)} /> : null}
    </div>
  );
}

/** Saves each change at once; a failed save puts the switch back and says so. */
function NotificationSwitches({ initial }: { initial: Prefs }) {
  const [prefs, setPrefs] = useState(initial);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  // Saves go out one at a time, in click order. Two quick switches used to send
  // two PUTs at once, and whichever the server committed last won, so the
  // later click could be lost.
  const queue = useRef<Promise<unknown>>(Promise.resolve());

  async function change(key: keyof Prefs, on: boolean) {
    const before = prefs;
    const next = withPref(prefs, key, on);
    setPrefs(next);
    setError(null);
    setSaving(true);
    const send = queue.current.then(() =>
      fetch("/api/bff/api/v1/users/me/notification-prefs", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(next),
      }),
    );
    queue.current = send.catch(() => undefined);
    try {
      const res = await send;
      // The whole state is sent each time, so the last change wins; the echo isn't
      // applied (an earlier, slower reply would undo a later click).
      if (!res.ok) throw new Error(String(res.status));
    } catch {
      setPrefs(before);
      setError("That change wasn’t saved. Try again.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <>
      <ul className="flex flex-col" aria-busy={saving}>
        {PREF_ROWS.map((row) => {
          const id = `pref-${row.key}`;
          const on = prefs[row.key];
          return (
            <li key={row.key} className="flex items-center gap-4 border-t border-[var(--border-subtle)] py-3">
              <span className="flex min-w-0 flex-1 flex-col gap-1">
                <span id={id} className="text-[14px]">
                  {row.title}
                </span>
                <span id={`${id}-sub`} className="text-[12px] text-[var(--text-secondary)]">
                  {row.sub}
                </span>
              </span>
              <Switch
                checked={on}
                labelledBy={id}
                describedBy={`${id}-sub`}
                disabled={!prefEnabled(prefs, row.key)}
                onChange={(next) => void change(row.key, next)}
              />
            </li>
          );
        })}
      </ul>
      {error ? (
        <p role="alert" className="mt-2 text-[12px] text-[var(--accent-danger)]">
          {error}
        </p>
      ) : null}
    </>
  );
}

function Section({ title, sub, children }: { title: string; sub?: string; children: React.ReactNode }) {
  return (
    <section className="rounded-[16px] border border-[var(--border-subtle)] p-5" aria-label={title}>
      <h2 className="text-[16px] font-semibold leading-none">{title}</h2>
      {sub ? <p className="mt-1 text-[12px] text-[var(--text-secondary)]">{sub}</p> : null}
      <div className="mt-4">{children}</div>
    </section>
  );
}

const FIELD = FIELD_INPUT_COMPACT;
const LABEL = "mb-1.5 block text-[12px] font-medium uppercase tracking-[0.04em] text-[var(--text-secondary)]";

function AccountModal({ me, storeName, onClose }: { me: Me; storeName: string; onClose: () => void }) {
  const router = useRouter();
  const [displayName, setDisplayName] = useState(me.displayName ?? "");
  const [username, setUsername] = useState(me.username ?? "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [avatar, setAvatar] = useState<string | null>(usablePhoto(me.avatarUrl ?? null));
  const file = useRef<HTMLInputElement>(null);
  const usernameOk = /^[a-z0-9_]{3,32}$/.test(username);
  const [currentPw, setCurrentPw] = useState("");
  const [newPw, setNewPw] = useState("");
  const [repeatPw, setRepeatPw] = useState("");
  const [done, setDone] = useState<string | null>(null);
  const profileChanged = displayName.trim() !== (me.displayName ?? "") || username !== (me.username ?? "");
  const pw = passwordCheck(currentPw, newPw, repeatPw);
  const changed = profileChanged || pw.wanted;

  async function save() {
    if (pw.wanted && pw.problem) {
      setError(pw.problem);
      return;
    }
    setBusy(true);
    setError(null);
    try {
      if (pw.wanted) {
        const res = await fetch("/api/bff/api/v1/users/me/password", {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({ current_password: currentPw, new_password: newPw }),
        });
        if (!res.ok) {
          const p = (await res.json().catch(() => ({}))) as { detail?: unknown };
          setError(typeof p.detail === "string" ? p.detail : "Your password couldn't be changed.");
          return;
        }
        setCurrentPw("");
        setNewPw("");
        setRepeatPw("");
        if (!profileChanged) {
          setDone("Password changed. We emailed you a notice.");
          return;
        }
      }
      const res = await fetch("/api/bff/api/v1/users/me", {
        method: "PATCH",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          ...(displayName.trim() !== (me.displayName ?? "") ? { display_name: displayName.trim() } : {}),
          ...(username !== (me.username ?? "") ? { username } : {}),
        }),
      });
      if (!res.ok) {
        const p = (await res.json().catch(() => ({}))) as { detail?: unknown };
        setError(typeof p.detail === "string" ? p.detail : "Your profile couldn't be saved.");
        return;
      }
      onClose();
      router.refresh();
    } catch {
      setError("Couldn't reach the server.");
    } finally {
      setBusy(false);
    }
  }

  async function changePhoto(e: React.ChangeEvent<HTMLInputElement>) {
    const f = e.target.files?.[0];
    e.target.value = "";
    if (!f) return;
    setBusy(true);
    setError(null);
    try {
      const prepared = await prepareImageForUpload(f, "photo");
      if (prepared.error) {
        setError(prepared.error);
        return;
      }
      const body = new FormData();
      body.append("file", prepared.file);
      const res = await fetch("/api/bff/api/v1/users/me/avatar", { method: "POST", body });
      if (!res.ok) {
        const p = (await res.json().catch(() => ({}))) as { detail?: unknown };
        setError(typeof p.detail === "string" ? p.detail : "That photo couldn't be uploaded.");
        return;
      }
      const u = (await res.json()) as { avatar_url?: string | null };
      setAvatar(usablePhoto(u.avatar_url ?? null));
      router.refresh();
    } catch {
      setError("Couldn't reach the server.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <AdminModal title="Profile and password" width={560} onClose={onClose}>
      <div className="flex flex-col gap-4 overflow-y-auto px-6 pb-5 pt-4">
        <div className="flex items-center gap-3">
          {avatar ? (
            <Image src={avatar} alt="" width={48} height={48} unoptimized className="size-12 rounded-full object-cover" />
          ) : (
            <span className="grid size-12 place-items-center rounded-full bg-[var(--surface-app)] text-[18px] font-semibold" aria-hidden>
              {(displayName || username || "?").slice(0, 1).toUpperCase()}
            </span>
          )}
          <span className="flex flex-1 flex-col gap-1">
            <span className="text-[16px] font-semibold">{displayName || username}</span>
            <span className="text-[12px] text-[var(--text-secondary)]">Store owner · joined {new Date(me.joined).toLocaleDateString("en-PH", { month: "long", year: "numeric" })}</span>
          </span>
          <button type="button" disabled={busy} onClick={() => file.current?.click()} className="h-9 shrink-0 rounded-full border border-[var(--text-primary)] px-4 text-[12px] disabled:opacity-50">
            Change photo
          </button>
          <input ref={file} type="file" accept="image/png,image/jpeg,image/webp" aria-label="Profile photo" className="hidden" onChange={(e) => void changePhoto(e)} />
        </div>
        <div>
          <label htmlFor="acct-name" className={LABEL}>Display name</label>
          <input id="acct-name" className={FIELD} value={displayName} maxLength={120} onChange={(e) => setDisplayName(e.target.value)} />
        </div>
        <div>
          <label htmlFor="acct-user" className={LABEL}>Username</label>
          <input
            id="acct-user"
            className={FIELD}
            value={username}
            maxLength={32}
            aria-invalid={!usernameOk}
            onChange={(e) => setUsername(e.target.value.toLowerCase())}
          />
          {!usernameOk ? <p className="mt-1 text-[12px] text-[var(--accent-danger)]">3 to 32 lowercase letters, numbers or underscores.</p> : null}
        </div>
        <EmailChange email={me.email} />
        {me.hasPassword ? (
          <fieldset className="flex flex-col gap-3">
            <legend className={`${LABEL} mb-2`}>Change password</legend>
            <div>
              <label htmlFor="acct-pw-current" className={LABEL}>Current password</label>
              <input id="acct-pw-current" type="password" autoComplete="current-password" className={FIELD} value={currentPw} maxLength={128} onChange={(e) => setCurrentPw(e.target.value)} />
            </div>
            <div>
              <label htmlFor="acct-pw-new" className={LABEL}>New password</label>
              <input id="acct-pw-new" type="password" autoComplete="new-password" placeholder="At least 10 characters" className={FIELD} value={newPw} maxLength={128} onChange={(e) => setNewPw(e.target.value)} />
            </div>
            <div>
              <label htmlFor="acct-pw-repeat" className={LABEL}>Repeat new password</label>
              <input id="acct-pw-repeat" type="password" autoComplete="new-password" placeholder="Type it again" className={FIELD} value={repeatPw} maxLength={128} onChange={(e) => setRepeatPw(e.target.value)} />
            </div>
            {pw.wanted && pw.problem ? <p className="text-[12px] text-[var(--accent-danger)]">{pw.problem}</p> : null}
          </fieldset>
        ) : (
          <div className="rounded-[12px] bg-[var(--surface-app)] p-3 text-[12px] leading-5 text-[var(--text-secondary)]">
            This account has no password: Bluntly signs you in with a one-time code sent to your email.
          </div>
        )}
        <p className="text-[12px] text-[var(--text-secondary)]">
          Buyers only see your store name ({storeName}) on responses and answers. Your email is never shown.
        </p>
        {error ? (
          <p role="alert" className="text-[12px] text-[var(--accent-danger)]">
            {error}
          </p>
        ) : null}
        {done ? (
          <p role="status" className="text-[12px] text-[var(--accent-success)]">
            {done}
          </p>
        ) : null}
      </div>
      <div className="flex items-center justify-end gap-3 border-t border-[var(--border-subtle)] px-6 py-4">
        <button type="button" onClick={onClose} className="h-9 rounded-full border border-[var(--text-primary)] px-4 text-[12px]">
          Cancel
        </button>
        <button
          type="button"
          disabled={!changed || !usernameOk || busy || (pw.wanted && Boolean(pw.problem))}
          onClick={() => void save()}
          className="h-9 rounded-full bg-[var(--accent-primary)] px-4 text-[12px] text-white disabled:opacity-50"
        >
          {busy ? "Saving…" : "Save changes"}
        </button>
      </div>
    </AdminModal>
  );
}
