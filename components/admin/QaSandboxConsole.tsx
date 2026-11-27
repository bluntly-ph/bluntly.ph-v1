"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useId, useState } from "react";

import type { QaSandboxData } from "@/lib/moderation";

/** ₱ with two decimals. lib/dashboard's `peso` is server-only. */
function peso(amount: string): string {
  return `₱${Number(amount).toLocaleString("en-PH", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

const FIELD =
  "h-8 min-w-0 rounded-[var(--radius-sm)] bg-[var(--surface-app)] px-2.5 text-[13px] text-[var(--text-primary)] shadow-[var(--shadow-hairline-inset)] outline-none focus-visible:shadow-[0_0_0_2px_var(--accent-primary)]";
const PRIMARY =
  "h-8 cursor-pointer rounded-[var(--radius-pill)] bg-[var(--accent-primary)] px-3.5 text-[12px] font-semibold text-white disabled:cursor-not-allowed disabled:opacity-60";
const SECONDARY =
  "h-8 cursor-pointer rounded-[var(--radius-pill)] px-3 text-[12px] font-semibold text-[var(--text-primary)] shadow-[var(--shadow-hairline-inset)] hover:bg-[var(--surface-app)] disabled:cursor-not-allowed disabled:opacity-60";

async function problem(res: Response, fallback: string): Promise<string> {
  const p = (await res.json().catch(() => ({}))) as { detail?: unknown };
  return typeof p.detail === "string" ? p.detail : fallback;
}

/**
 * QA sandbox test earnings (owner decision, 2026-09-27).
 *
 * A Super Admin names the QA testers; any administrator can then credit one of a
 * tester's published reviews with a labelled test earning, once per review.
 * It lands cleared, so the tester can go straight to Transfer and request a
 * withdrawal, which is then paid from the Payouts screen through PayPal
 * sandbox. It is never platform revenue and never counts toward the Honesty
 * Fund; it is refused while payouts run on live PayPal.
 */
export function QaSandboxConsole({ data, allowed }: { data: QaSandboxData | null; allowed: boolean }) {
  const router = useRouter();
  const id = useId();
  const [identifier, setIdentifier] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!data) {
    return (
      <p className="rounded-[var(--radius-md)] bg-[var(--surface-card)] p-4 text-[12px] text-[var(--accent-danger)] shadow-[var(--shadow-card)]">
        The QA tester list couldn&rsquo;t be loaded.
      </p>
    );
  }

  async function addTester(e: React.FormEvent) {
    e.preventDefault();
    if (!identifier.trim() || busy) return;
    setBusy(true);
    setError(null);
    try {
      const res = await fetch("/api/bff/api/v1/admin/qa-sandbox/testers", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ identifier: identifier.trim() }),
      });
      if (!res.ok) {
        setError(await problem(res, "Couldn't add that account."));
        return;
      }
      setIdentifier("");
      router.refresh();
    } catch {
      setError("Couldn't reach the server.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex flex-col gap-4">
      {!allowed ? (
        <p role="alert" className="rounded-[var(--radius-md)] bg-[var(--surface-card)] p-4 text-[12px] text-[var(--accent-danger)] shadow-[var(--shadow-card)]">
          Payouts run on live PayPal, so test earnings are switched off.
        </p>
      ) : null}

      <section
        aria-labelledby={`${id}-testers`}
        className="rounded-[var(--radius-md)] bg-[var(--surface-card)] p-4 shadow-[var(--shadow-card)]"
      >
        <h3 id={`${id}-testers`} className="text-[14px] font-semibold text-[var(--text-primary)]">
          QA testers
        </h3>
        <p className="mt-1 max-w-[46rem] text-[12px] text-[var(--text-secondary)]">
          {data.can_manage_testers
            ? "Only the accounts you name here can receive a test earning. Add a tester by username or email."
            : "Only a Super Admin can add or remove QA testers."}
        </p>
        {data.can_manage_testers ? (
          <form onSubmit={addTester} className="mt-3 flex flex-wrap items-end gap-2">
            <label className="flex min-w-[16rem] flex-1 flex-col gap-1 text-[12px] text-[var(--text-secondary)] sm:max-w-[24rem]">
              Username or email
              <input
                value={identifier}
                onChange={(e) => setIdentifier(e.target.value.slice(0, 320))}
                className={FIELD}
                placeholder="@username or name@example.com"
              />
            </label>
            <button type="submit" className={PRIMARY} disabled={busy || !identifier.trim()}>
              Add tester
            </button>
          </form>
        ) : null}
        {error ? (
          <p role="alert" className="mt-2 text-[12px] text-[var(--accent-danger)]">
            {error}
          </p>
        ) : null}
        {data.testers.length === 0 ? (
          <p className="mt-3 text-[12px] text-[var(--text-secondary)]">No QA testers yet.</p>
        ) : null}
      </section>

      {data.testers.map((t) => (
        <TesterCard
          key={t.user_id}
          tester={t}
          canManage={data.can_manage_testers}
          allowed={allowed}
          defaultAmount={data.default_amount}
          maxAmount={data.max_amount}
          onDone={() => router.refresh()}
        />
      ))}
    </div>
  );
}

function TesterCard({
  tester,
  canManage,
  allowed,
  defaultAmount,
  maxAmount,
  onDone,
}: {
  tester: QaSandboxData["testers"][number];
  canManage: boolean;
  allowed: boolean;
  defaultAmount: string;
  maxAmount: string;
  onDone: () => void;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [amounts, setAmounts] = useState<Record<string, string>>({});
  const name = tester.username ? `@${tester.username}` : (tester.display_name ?? "Tester");

  async function remove() {
    setBusy(true);
    setError(null);
    try {
      const res = await fetch(`/api/bff/api/v1/admin/qa-sandbox/testers/${tester.user_id}`, { method: "DELETE" });
      if (!res.ok) {
        setError(await problem(res, "Couldn't remove the tester."));
        return;
      }
      onDone();
    } catch {
      setError("Couldn't reach the server.");
    } finally {
      setBusy(false);
    }
  }

  async function credit(reviewId: string) {
    setBusy(true);
    setError(null);
    const amount = (amounts[reviewId] ?? "").trim();
    try {
      const res = await fetch("/api/bff/api/v1/admin/qa-sandbox/credits", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ review_id: reviewId, amount: amount || null }),
      });
      if (!res.ok) {
        setError(await problem(res, "Couldn't credit the test earning."));
        return;
      }
      onDone();
    } catch {
      setError("Couldn't reach the server.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section
      aria-label={`QA tester ${name}`}
      data-testid="qa-tester"
      className="rounded-[var(--radius-md)] bg-[var(--surface-card)] p-4 shadow-[var(--shadow-card)]"
    >
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <p className="text-[14px] font-semibold text-[var(--text-primary)]">{name}</p>
          <p className="mt-0.5 text-[12px] text-[var(--text-secondary)]">
            Balance {peso(tester.wallet_balance)} · test earnings {peso(tester.test_earned)} ·{" "}
            {tester.payout_account_set ? "PayPal address set" : "no PayPal address yet"}
          </p>
        </div>
        {canManage ? (
          <button type="button" className={SECONDARY} disabled={busy} onClick={remove}>
            Remove tester
          </button>
        ) : null}
      </div>
      {error ? (
        <p role="alert" className="mt-2 text-[12px] text-[var(--accent-danger)]">
          {error}
        </p>
      ) : null}
      {tester.reviews.length === 0 ? (
        <p className="mt-3 text-[12px] text-[var(--text-secondary)]">
          No published reviews yet. The tester needs to post a review before it can take a test earning.
        </p>
      ) : (
        <ul className="mt-3 flex flex-col divide-y divide-[var(--line-hairline-10)]">
          {tester.reviews.map((r) => (
            <li key={r.review_id} className="flex flex-wrap items-center justify-between gap-2 py-2.5">
              <Link
                href={`/reviews/${r.review_id}`}
                className="min-w-0 max-w-full truncate text-[13px] text-[var(--text-primary)] underline-offset-2 hover:underline"
              >
                {r.title ?? "Untitled review"}
              </Link>
              {r.credited_amount ? (
                <span className="text-[12px] text-[var(--text-secondary)]">
                  Test earning {peso(r.credited_amount)} credited
                  {r.credited_at ? ` ${new Date(r.credited_at).toLocaleDateString("en-PH", { dateStyle: "medium" })}` : ""}
                </span>
              ) : (
                <span className="flex items-center gap-2">
                  <label className="flex items-center gap-1 text-[12px] text-[var(--text-secondary)]">
                    ₱
                    <input
                      inputMode="decimal"
                      aria-label={`Test amount for ${r.title ?? "this review"}`}
                      value={amounts[r.review_id] ?? ""}
                      placeholder={String(Number(defaultAmount))}
                      onChange={(e) =>
                        setAmounts({ ...amounts, [r.review_id]: e.target.value.replace(/[^0-9.]/g, "").slice(0, 8) })
                      }
                      className={`${FIELD} w-20`}
                    />
                  </label>
                  <button
                    type="button"
                    className={PRIMARY}
                    disabled={busy || !allowed || Number(amounts[r.review_id] || defaultAmount) > Number(maxAmount)}
                    onClick={() => credit(r.review_id)}
                  >
                    Credit test earning
                  </button>
                </span>
              )}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
