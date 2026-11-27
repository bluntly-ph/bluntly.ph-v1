"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { ConfirmDialog } from "@/components/admin/ConfirmDialog";
import { shortAge } from "@/components/admin/queue/QueueCells";
import { countState } from "@/components/console/counted-model";
import { CountedTextarea } from "@/components/console/CountedTextarea";
import { CATEGORIES } from "@/lib/landing-data";

const NOTE_MAX = 500;

/**
 * Sellers → Product links: stores asking to link product pages they sell
 * (0077). Not drawn in the Figma — the seller frames say "A moderator checks
 * each link" (Overlay/Store/LinkProduct 8204:23173) — so it follows the
 * Claims / Appeals table. Approve or reject, each confirmed; the owner is told.
 */

type Schemas = import("@/lib/api-types").components["schemas"];
type LinkRow = Schemas["AdminStoreProductOut"];
const CATEGORY_LABEL = Object.fromEntries(CATEGORIES.map((c) => [c.slug, c.label]));

export function StoreProductLinks({ rows, now }: { rows: LinkRow[] | null; now: number }) {
  const router = useRouter();
  const [deciding, setDeciding] = useState<{ row: LinkRow; approve: boolean } | null>(null);
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function decide() {
    if (!deciding) return;
    setBusy(true);
    setError(null);
    try {
      const res = await fetch(`/api/bff/api/v1/admin/store-products/${deciding.row.id}/decision`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ decision: deciding.approve ? "approve" : "reject", note: note.trim() || null }),
      });
      if (!res.ok) {
        const p = (await res.json().catch(() => ({}))) as { detail?: unknown };
        setError(typeof p.detail === "string" ? p.detail : "That didn’t work. Try again.");
        return;
      }
      setDeciding(null);
      setNote("");
      router.refresh();
    } catch {
      setError("Couldn’t reach the server.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <div className="overflow-x-auto rounded-[16px] border border-[var(--border-subtle)]">
        <table className="w-full min-w-[860px] border-collapse text-left text-[14px]">
          <caption className="sr-only">Product link requests</caption>
          <thead className="bg-[var(--surface-app)] text-[12px] text-[var(--text-secondary)]">
            <tr>
              {["Store", "Product", "Asked by", "Requested", "Action"].map((h) => (
                <th key={h} scope="col" className="h-10 px-3 font-normal">
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows === null ? (
              <tr>
                <td colSpan={5} className="border-t border-[var(--border-subtle)] px-3 py-10 text-center text-[var(--text-secondary)]">
                  This list could not be loaded.
                </td>
              </tr>
            ) : rows.length === 0 ? (
              <tr>
                <td colSpan={5} className="border-t border-[var(--border-subtle)] px-3 py-10 text-center text-[var(--text-secondary)]">
                  No product link is waiting.
                </td>
              </tr>
            ) : (
              rows.map((r) => (
                <tr key={r.id} data-testid="product-link-row" className="group border-t border-[var(--border-subtle)] hover:bg-[var(--surface-app)]">
                  <td className="px-3 py-[10px]">
                    <Link href={`/sellers/${r.seller_id}`} className="font-medium hover:underline">
                      {r.seller_name}
                    </Link>
                  </td>
                  <td className="px-3">
                    <span className="flex flex-col gap-1 leading-4 [&>:first-child]:leading-5">
                      <Link href={`/admin/products?tab=catalogue&q=${encodeURIComponent(r.product_name)}`} className="hover:underline">
                        {r.product_name}
                      </Link>
                      <span className="text-[12px] text-[var(--text-secondary)]">
                        {CATEGORY_LABEL[r.product_category ?? ""] ?? "No category"} · {r.review_count} review{r.review_count === 1 ? "" : "s"}
                      </span>
                    </span>
                  </td>
                  <td className="px-3">{r.requested_by ?? "—"}</td>
                  <td className="px-3 text-[var(--text-secondary)]" suppressHydrationWarning>
                    {shortAge(r.requested_at, now)}
                  </td>
                  <td className="px-3 py-[6px]">
                    <span className="flex gap-2">
                      <button type="button" onClick={() => setDeciding({ row: r, approve: true })} className="h-7 rounded-full bg-[var(--accent-primary)] px-3 text-[12px] text-white">
                        Approve
                      </button>
                      <button type="button" onClick={() => setDeciding({ row: r, approve: false })} className="h-7 rounded-full border border-[var(--border-subtle)] bg-[var(--surface-card)] px-3 text-[12px]">
                        Reject
                      </button>
                    </span>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
      <ConfirmDialog
        open={deciding !== null}
        title={deciding?.approve ? `Link ${deciding.row.product_name} to ${deciding.row.seller_name}?` : "Reject this link?"}
        confirmLabel={deciding?.approve ? "Approve link" : "Reject link"}
        busyLabel="Saving…"
        busy={busy}
        error={error}
        tone={deciding?.approve ? "primary" : "danger"}
        disabled={countState(note, NOTE_MAX).over}
        onConfirm={() => void decide()}
        onClose={() => setDeciding(null)}
      >
        <p>{deciding?.approve ? "The store’s console shows this product’s figures. The store gains no say over the product page." : "The store is told it wasn’t linked and can ask again."}</p>
        <div className="mt-2">
          <CountedTextarea id="link-decision-note" label="Note to the store · optional" value={note} onChange={setNote} max={NOTE_MAX} rows={2} />
        </div>
      </ConfirmDialog>
    </>
  );
}
