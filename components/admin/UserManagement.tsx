"use client";

import { useEffect, useRef, useState } from "react";
import { MagnifyingGlass, ShieldCheck } from "@phosphor-icons/react/dist/ssr";

import { Pagination } from "@/components/console/Pagination";
import { PAGE_SIZES } from "@/components/console/pagination-model";
import { roleLabel, type MemberRole } from "@/lib/roles";
import { DROPDOWN_PILL_STATES } from "@/components/ui/search-styles";
import { TOP_SEARCH_STATES } from "@/components/ui/search-styles";

type StaffUser = {
  id: string;
  staff_ref: string;
  display_name: string | null;
  username: string | null;
  email: string | null;
  role: MemberRole;
  is_super_admin: boolean;
  is_suspended: boolean;
  trust_stage: number;
  created_at: string;
  /** Business Rules §11: halves the account's vote weight while set. */
  is_under_investigation?: boolean;
  /** §9: an approved store owner. */
  is_claimed_seller?: boolean;
};

type DirectoryPage = {
  rows: StaffUser[];
  total: number;
  resolved_staff_ref: string | null;
  can_manage_roles: boolean;
};

type Problem = { detail?: string };

/** The roles this screen assigns (PATCH /admin/users/{id}/role). */
const ASSIGNABLE: MemberRole[] = ["user", "administrator", "super_admin"];

/**
 * User management: the Super Admin's (owner decisions C and D, 2026-09-28).
 *
 * Find an account; move it between Member, Administrator and Super Admin, each
 * change confirmed in a dialog that names the account and both roles. The API
 * refuses anyone but a Super Admin, refuses to remove the last Super Admin
 * (409 last_super_admin) and never makes a claimed seller staff; this screen
 * only decides what to offer. The browser holds no access token: requests go
 * through the BFF.
 */
export function UserManagement() {
  const [query, setQuery] = useState("");
  const [page, setPage] = useState<DirectoryPage | null>(null);
  const [loading, setLoading] = useState(false);
  const [changing, setChanging] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  // The search that produced `page`, and where in its matches we are: the
  // results page like every console table instead of stopping at the first 25.
  const [searched, setSearched] = useState({ q: "", page: 1, size: PAGE_SIZES[0] as number });

  async function findUsers(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const candidate = query.trim();
    if (!candidate) return;
    await load({ q: candidate, page: 1, size: searched.size });
  }

  async function load(next: { q: string; page: number; size: number }) {
    setLoading(true);
    setError(null);
    setNotice(null);
    try {
      const params = new URLSearchParams({
        q: next.q,
        limit: String(next.size),
        offset: String((next.page - 1) * next.size),
      });
      const response = await fetch(`/api/bff/api/v1/admin/users?${params}`, {
        cache: "no-store",
      });
      if (!response.ok) {
        const problem = (await response.json().catch(() => ({}))) as Problem;
        throw new Error(problem.detail ?? "Search failed.");
      }
      setPage((await response.json()) as DirectoryPage);
      setSearched(next);
    } catch (cause) {
      setPage(null);
      setError(cause instanceof Error ? cause.message : "Search failed.");
    } finally {
      setLoading(false);
    }
  }

  const [pending, setPending] = useState<{ user: StaffUser; next: MemberRole } | null>(null);

  async function changeRole(user: StaffUser, next: MemberRole) {
    const identity = user.display_name ?? user.username ?? user.staff_ref;
    setChanging(user.id);
    setError(null);
    setNotice(null);
    try {
      const response = await fetch(`/api/bff/api/v1/admin/users/${user.id}/role`, {
        method: "PATCH",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ role: next }),
      });
      if (!response.ok) {
        const problem = (await response.json().catch(() => ({}))) as Problem;
        throw new Error(problem.detail ?? "Role change failed.");
      }
      setPage((current) =>
        current
          ? {
              ...current,
              rows: current.rows.map((row) =>
                row.id === user.id ? { ...row, role: next, is_super_admin: next === "super_admin" } : row,
              ),
            }
          : current,
      );
      setNotice(`${identity} is now ${next === "administrator" ? "an" : "a"} ${roleLabel(next)}.`);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Role change failed.");
    } finally {
      setChanging(null);
      setPending(null);
    }
  }

  /**
   * Business Rules §11: "under investigation" halves an account's vote weight
   * while a suspicion is unproven. What triggers it is still an open rule, so
   * only this explicit, audited staff action sets or clears it. Reversible,
   * so no confirmation step; the API refuses your own account.
   */
  async function toggleInvestigation(user: StaffUser) {
    const next = !user.is_under_investigation;
    const identity = user.display_name ?? user.username ?? user.staff_ref;
    setChanging(user.id);
    setError(null);
    setNotice(null);
    try {
      const response = await fetch(`/api/bff/api/v1/admin/users/${user.id}/investigation`, {
        method: "PUT",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ under_investigation: next }),
      });
      if (!response.ok) {
        const problem = (await response.json().catch(() => ({}))) as Problem;
        throw new Error(problem.detail ?? "Couldn't change the investigation state.");
      }
      setPage((current) =>
        current
          ? {
              ...current,
              rows: current.rows.map((row) =>
                row.id === user.id ? { ...row, is_under_investigation: next } : row,
              ),
            }
          : current,
      );
      setNotice(
        next
          ? `${identity} is under investigation: their votes count half until it is cleared.`
          : `${identity} is no longer under investigation.`,
      );
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Couldn't change the investigation state.");
    } finally {
      setChanging(null);
    }
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-4">
      <header className="shrink-0">
        {/* The shell's h1 names the page ("User management"). */}
        <p className="max-w-[55rem] text-[13px] text-[var(--text-secondary)]">
          Find an account by staff reference, UUID, exact email, display name, or username. Staff references
          are internal and do not grant access to anything.
        </p>
      </header>

      <form
        role="search"
        onSubmit={(event) => void findUsers(event)}
        className="flex shrink-0 flex-col gap-2 rounded-[var(--radius-md)] bg-[var(--surface-card)] p-4 shadow-[var(--shadow-card)] sm:flex-row"
      >
        <label htmlFor="staff-user-query" className="sr-only">
          Find a platform user
        </label>
        <div className="relative min-w-0 flex-1">
          <MagnifyingGlass
            aria-hidden="true"
            size={18}
            className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-[var(--text-muted)]"
          />
          <input
            id="staff-user-query"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="USR-000123, UUID, exact email, or name"
            maxLength={320}
            autoComplete="off"
            className={`h-11 w-full rounded-[var(--radius-pill)] pl-10 pr-4 text-[14px] text-[var(--text-primary)] caret-[var(--accent-primary)] outline-none placeholder:text-[var(--text-muted)] ${TOP_SEARCH_STATES}`}
          />
        </div>
        <button
          type="submit"
          disabled={loading || !query.trim()}
          className="h-11 rounded-[var(--radius-pill)] bg-[var(--accent-primary)] px-5 text-[13px] font-semibold text-[var(--text-on-brand)] disabled:cursor-not-allowed disabled:opacity-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--accent-primary)]"
        >
          {loading ? "Searching…" : "Search"}
        </button>
      </form>

      <div aria-live="polite" className="min-h-5 shrink-0 text-[13px]">
        {error ? (
          <p role="alert" className="text-[var(--accent-danger)]">
            {error}
          </p>
        ) : null}
        {notice ? (
          <p role="status" className="text-[var(--accent-trust)]">
            {notice}
          </p>
        ) : null}
        {!error && !notice && page ? (
          <p className="text-[var(--text-secondary)]">
            {page.total} match{page.total === 1 ? "" : "es"}
            {page.resolved_staff_ref ? ` · resolved as ${page.resolved_staff_ref}` : ""}
          </p>
        ) : null}
      </div>

      <div className="min-h-0 flex-1 overflow-auto rounded-[var(--radius-md)] bg-[var(--surface-card)] shadow-[var(--shadow-card)]">
        {!page ? (
          <EmptyState text="Search for a user to inspect their administrative status." />
        ) : page.rows.length === 0 ? (
          <EmptyState text="No account matched that identifier." />
        ) : (
          <table className="w-full min-w-[54rem] border-collapse text-left">
            <thead className="sticky top-0 z-10 bg-[var(--surface-app)]">
              <tr className="text-[11px] uppercase tracking-[0.08em] text-[var(--text-muted)]">
                <th className="px-4 py-3 font-medium">User</th>
                <th className="px-4 py-3 font-medium">Staff reference</th>
                <th className="px-4 py-3 font-medium">Role</th>
                <th className="px-4 py-3 font-medium">Status</th>
                <th className="px-4 py-3 font-medium">Joined</th>
                <th className="px-4 py-3 text-right font-medium">Access</th>
              </tr>
            </thead>
            <tbody>
              {page.rows.map((user) => {
                const managed = ASSIGNABLE.includes(user.role) && !user.is_claimed_seller;
                return (
                  <tr key={user.id} className="border-t border-[var(--border-subtle)] text-[13px]">
                    <td className="px-4 py-3">
                      <span className="block font-medium text-[var(--text-primary)]">
                        {user.display_name ?? user.username ?? "Unnamed user"}
                      </span>
                      {/* The handle first: it is what staff recognise and what
                          the person uses; then the email (this screen is the
                          Super Admin's), and the opaque id only when an account
                          has neither (owner note, 2026-09-16). */}
                      <span className="block text-[12px] text-[var(--text-muted)]">
                        {user.username ? `@${user.username}` : null}
                        {user.username && user.email ? " · " : null}
                        {user.email}
                        {!user.username && !user.email ? user.id : null}
                      </span>
                    </td>
                    <td className="px-4 py-3 font-mono text-[12px] font-semibold text-[var(--text-primary)]">
                      {user.staff_ref}
                    </td>
                    <td className="px-4 py-3">
                      <span className="inline-flex items-center gap-1.5 text-[var(--text-secondary)]">
                        {user.role === "super_admin" ? (
                          <ShieldCheck size={16} weight="fill" className="text-[var(--accent-primary)]" />
                        ) : null}
                        {roleLabel(user.role)}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-[var(--text-secondary)]">
                      {user.is_suspended ? "Suspended" : `Active · trust ${user.trust_stage}`}
                      {user.is_claimed_seller ? <span className="block text-[12px]">Claimed seller</span> : null}
                      {user.is_under_investigation ? (
                        <span className="block text-[12px] font-medium text-[var(--accent-danger)]">
                          Under investigation
                        </span>
                      ) : null}
                      {user.role !== "super_admin" ? (
                        <button
                          type="button"
                          onClick={() => void toggleInvestigation(user)}
                          disabled={changing === user.id}
                          className="mt-1 block cursor-pointer text-[12px] text-[var(--text-muted)] underline-offset-4 hover:text-[var(--accent-primary)] hover:underline disabled:opacity-50"
                        >
                          {user.is_under_investigation ? "Clear investigation" : "Mark under investigation"}
                        </button>
                      ) : null}
                    </td>
                    <td className="whitespace-nowrap px-4 py-3 text-[12px] text-[var(--text-muted)]">
                      {new Date(user.created_at).toLocaleDateString("en-PH", { dateStyle: "medium" })}
                    </td>
                    <td className="px-4 py-3 text-right">
                      {page.can_manage_roles && managed ? (
                        <label className="inline-flex items-center gap-2 text-[12px] text-[var(--text-secondary)]">
                          <span className="sr-only">Role for {user.display_name ?? user.username ?? user.staff_ref}</span>
                          <select
                            value={user.role}
                            disabled={changing === user.id}
                            onChange={(event) => setPending({ user, next: event.target.value as MemberRole })}
                            className={`min-h-9 rounded-[var(--radius-pill)] px-3 ${DROPDOWN_PILL_STATES} font-semibold`}
                          >
                            {ASSIGNABLE.map((role) => (
                              <option key={role} value={role}>
                                {roleLabel(role)}
                              </option>
                            ))}
                          </select>
                        </label>
                      ) : (
                        <span className="text-[12px] text-[var(--text-muted)]">
                          {user.is_claimed_seller ? "Claimed seller: never staff" : "Not managed here"}
                        </span>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>
      {page && page.total > 0 ? (
        <Pagination
          page={searched.page}
          size={searched.size}
          total={page.total}
          onChange={({ page: p, size }) => void load({ q: searched.q, page: p, size })}
          label="Search result pages"
        />
      ) : null}
      <RoleChangeDialog
        change={pending}
        busy={pending !== null && changing === pending.user.id}
        onCancel={() => setPending(null)}
        onConfirm={() => pending && void changeRole(pending.user, pending.next)}
      />
    </div>
  );
}

/**
 * The confirmation every role change needs: the account, the role it has and
 * the role it will have, and what that means — before anything is sent.
 */
function RoleChangeDialog({
  change,
  busy,
  onCancel,
  onConfirm,
}: {
  change: { user: StaffUser; next: MemberRole } | null;
  busy: boolean;
  onCancel: () => void;
  onConfirm: () => void;
}) {
  const ref = useRef<HTMLDialogElement | null>(null);
  useEffect(() => {
    const dialog = ref.current;
    if (!dialog) return;
    if (change && !dialog.open) dialog.showModal();
    if (!change && dialog.open) dialog.close();
  }, [change]);
  const identity = change ? (change.user.display_name ?? change.user.username ?? change.user.staff_ref) : "";
  const meaning =
    change?.next === "super_admin"
      ? "They will manage users and roles and decide 2.5-star routing, as well as everything an Administrator does."
      : change?.next === "administrator"
        ? "They will work the operational queues (reviews, claims, links, support, reports) but will not manage users."
        : "They will lose access to the Administrator console.";
  return (
    <dialog
      ref={ref}
      aria-labelledby="role-change-title"
      onClose={onCancel}
      className="m-auto w-[min(420px,calc(100vw-2rem))] rounded-[var(--radius-md)] bg-[var(--surface-app)] p-6 text-[var(--text-primary)] shadow-[var(--shadow-sheet)] backdrop:bg-[var(--overlay-scrim-25)]"
    >
      <h2 id="role-change-title" className="text-[16px] font-bold">
        Change {identity}&rsquo;s role?
      </h2>
      {change ? (
        <p className="mt-3 text-[14px] leading-[21px]">
          <strong>{roleLabel(change.user.role)}</strong> &rarr; <strong>{roleLabel(change.next)}</strong>. {meaning} The
          change is recorded against you.
        </p>
      ) : null}
      <div className="mt-6 flex items-center justify-end gap-3">
        <button type="button" onClick={onCancel} className="rounded-[var(--radius-pill)] px-4 py-2 text-[13px]">
          Cancel
        </button>
        <button
          type="button"
          onClick={onConfirm}
          disabled={busy}
          className="rounded-[var(--radius-pill)] bg-[var(--accent-primary)] px-4 py-2 text-[13px] font-semibold text-[var(--text-on-brand)] disabled:opacity-60"
        >
          {busy ? "Saving…" : "Confirm change"}
        </button>
      </div>
    </dialog>
  );
}

function EmptyState({ text }: { text: string }) {
  return (
    <div className="grid min-h-48 place-items-center p-8 text-center text-[13px] text-[var(--text-secondary)]">
      <p>{text}</p>
    </div>
  );
}
