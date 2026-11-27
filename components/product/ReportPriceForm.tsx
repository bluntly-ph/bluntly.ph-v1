"use client";

import Link from "next/link";
import { useId, useState } from "react";

import {
  MAX_VARIANT,
  PRICE_PLATFORMS,
  PRICE_PLATFORM_LABEL,
  manilaToday,
  normalisePrice,
  observationBlocker,
  observationPayload,
  type PricePlatform,
} from "@/components/reviews/price-capture-model";
import { Button } from "@/components/ui/Button";
import { PUBLIC_INPUT } from "@/components/ui/field-styles";

/**
 * "Report what you paid" — a community price observation from the product
 * surface, not only from the composer (FR-2, completion contract).
 *
 * Business Rules §16: a price report always belongs to the reporter's OWN
 * review of the product, leaning on that review's photo or receipt for its
 * backing — never a standalone number. So this is offered only on the
 * reader's own review (`reviewId`); on anyone else's it says where to report
 * instead. The API refuses a report without such a review either way
 * (`price_needs_review`).
 *
 * Collapsed by default: the panel is the content, and a form that opens on
 * every review page would crowd the reading column for the many readers who
 * have not bought the product.
 */
export function ReportPriceForm({
  productId,
  signedIn,
  reviewId = null,
}: {
  productId: string;
  signedIn: boolean;
  /** The reader's own review of this product, when this page is it. */
  reviewId?: string | null;
}) {
  const priceId = useId();
  const dateId = useId();
  const variantId = useId();
  const [open, setOpen] = useState(false);
  const [price, setPrice] = useState("");
  const [platform, setPlatform] = useState<PricePlatform | null>(null);
  const [observedAt, setObservedAt] = useState("");
  const [variant, setVariant] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [sent, setSent] = useState(false);

  const trigger =
    "mt-3 cursor-pointer text-[13px] font-medium text-[var(--accent-primary)] underline-offset-4 hover:underline";

  if (!signedIn) {
    return (
      <Link href="/login" className={`${trigger} inline-block`}>
        Log in to report what you paid
      </Link>
    );
  }

  if (!reviewId) {
    return (
      <p className="mt-3 text-[12px] leading-[18px] text-[var(--text-secondary)]">
        Bought this? Prices come from reviews: report what you paid from your own review of it.
      </p>
    );
  }

  if (sent) {
    return (
      <p role="status" className="mt-3 text-[13px] text-[var(--text-secondary)]">
        Thanks. It&rsquo;s on the price history now, unless it&rsquo;s far outside recent prices — then a
        administrator glances at it first.
      </p>
    );
  }

  if (!open) {
    return (
      <button type="button" onClick={() => setOpen(true)} className={trigger}>
        Report what you paid
      </button>
    );
  }

  const today = manilaToday();
  const fields = { price, platform, observedAt, variant };
  const blocker = observationBlocker(fields, today);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (blocker || busy) return;
    setBusy(true);
    setError(null);
    try {
      const res = await fetch(`/api/bff/api/v1/products/${productId}/prices`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ ...observationPayload(fields), review_id: reviewId }),
      });
      if (!res.ok) {
        const p = (await res.json().catch(() => ({}))) as { detail?: string };
        setError(p.detail ?? "Couldn't send your price.");
        return;
      }
      setSent(true);
    } catch {
      setError("Couldn't reach the server.");
    } finally {
      setBusy(false);
    }
  }

  // Figma TextField (6808:456), as Sheet/Product/ReportPrice (8422:35470) places
  // it: white and bordered; every state from the shared public field classes.
  const field = PUBLIC_INPUT;
  const label = "text-[12px] font-medium text-[var(--text-secondary)]";

  return (
    <form
      onSubmit={submit}
      className="mt-3 flex flex-col gap-3 rounded-[var(--radius-sm)] bg-[var(--surface-card)] p-4 shadow-[var(--shadow-hairline-inset)]"
    >
      <p className="text-[14px] font-semibold text-[var(--text-primary)]">What did you pay?</p>

      <div>
        <label htmlFor={priceId} className={label}>
          Amount, in pesos
        </label>
        <input
          id={priceId}
          value={price}
          onChange={(e) => setPrice(normalisePrice(e.target.value))}
          inputMode="decimal"
          placeholder="1299"
          className={`mt-1 ${field}`}
        />
      </div>

      <fieldset>
        <legend className={label}>Where did you buy it?</legend>
        <div className="mt-1 flex flex-wrap gap-2">
          {PRICE_PLATFORMS.map((key) => (
            <button
              key={key}
              type="button"
              onClick={() => setPlatform(key)}
              aria-pressed={platform === key}
              className={`h-8 cursor-pointer rounded-[var(--radius-pill)] px-3 text-[13px] ${
                platform === key
                  ? "bg-[var(--accent-primary)] text-white"
                  : "bg-[var(--surface-app)] text-[var(--text-primary)] shadow-[var(--shadow-hairline-inset)]"
              }`}
            >
              {PRICE_PLATFORM_LABEL[key]}
            </button>
          ))}
        </div>
      </fieldset>

      <div className="grid gap-3 sm:grid-cols-2">
        <div>
          <label htmlFor={dateId} className={label}>
            Date you paid
          </label>
          <input
            id={dateId}
            type="date"
            value={observedAt}
            max={today}
            onChange={(e) => setObservedAt(e.target.value)}
            className={`mt-1 ${field}`}
          />
        </div>
        <div>
          <label htmlFor={variantId} className={label}>
            Variant (optional)
          </label>
          <input
            id={variantId}
            value={variant}
            onChange={(e) => setVariant(e.target.value.slice(0, MAX_VARIANT + 1))}
            placeholder="Colour, size, bundle"
            className={`mt-1 ${field}`}
          />
        </div>
      </div>

      <p aria-live="polite" className="text-[12px] text-[var(--text-muted)]">
        {blocker ?? "It shows on the price history at once; only an unusual price waits for an administrator."}
      </p>
      {error ? (
        <p role="alert" className="text-[13px] text-[var(--accent-danger)]">
          {error}
        </p>
      ) : null}

      <div className="flex items-center gap-4">
        <Button type="submit" disabled={Boolean(blocker) || busy}>
          {busy ? "Sending…" : "Send price"}
        </Button>
        <button
          type="button"
          onClick={() => setOpen(false)}
          className="cursor-pointer text-[13px] text-[var(--text-secondary)] underline-offset-4 hover:underline"
        >
          Cancel
        </button>
      </div>
    </form>
  );
}

export default ReportPriceForm;
