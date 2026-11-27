"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { RequestProductField, type RequestProduct } from "@/components/requests/RequestProductField";
import { Button } from "@/components/ui/Button";
import { PUBLIC_INPUT, PUBLIC_TEXTAREA } from "@/components/ui/field-styles";

/**
 * Post a review request. Free — the backend AI-screens it (422 `request_invalid`
 * returns `reasons[]`) and that is the only way it can be rejected.
 *
 * There was a token bounty here, escrowed from a balance the page never showed,
 * so the first anyone heard about affording it was a 409 after writing the whole
 * thing (BUG-025). Tokens are retired; asking for a review costs nothing and
 * up-votes are what tell reviewers which questions people actually want answered.
 */
export function RequestForm() {
  const router = useRouter();
  // Every request names its product (dev/QA sync 2026-09-29): it belongs to
  // that product for good, and every later review of it is an answer.
  const [product, setProduct] = useState<RequestProduct | null>(null);
  const [title, setTitle] = useState("");
  const [details, setDetails] = useState("");
  const [sourceUrl, setSourceUrl] = useState("");
  const [busy, setBusy] = useState(false);
  const [errors, setErrors] = useState<string[]>([]);

  const ready = product && title.trim() && details.trim();

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!ready || busy) return;
    setBusy(true);
    setErrors([]);
    try {
      const res = await fetch("/api/bff/api/v1/requests", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          product_id: product?.id,
          title: title.trim(),
          details: details.trim(),
          source_url: sourceUrl.trim() || null,
        }),
      });
      if (!res.ok) {
        const p = (await res.json().catch(() => ({}))) as {
          detail?: string;
          reasons?: string[];
        };
        setErrors(p.reasons?.length ? p.reasons : [p.detail ?? "Couldn't post that request."]);
        return;
      }
      const posted = (await res.json().catch(() => null)) as { id?: string } | null;
      router.push(posted?.id ? `/requests/${posted.id}` : "/requests");
    } catch {
      setErrors(["Couldn't reach the server."]);
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit}>
      <h1 className="text-[24px] font-bold text-[var(--text-primary)]">
        Ask for a review
      </h1>
      <p className="mt-1 text-[14px] text-[var(--text-secondary)]">
        Ask and the community answers. The more people up-vote your request, the
        further up the board it goes.
      </p>

      <div className="mt-6 flex flex-col gap-5">
        <RequestProductField value={product} onChange={setProduct} />

        <label className="flex flex-col gap-1.5">
          <span className="text-[13px] font-medium text-[var(--text-primary)]">What do you want reviewed?</span>
          <input
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            maxLength={200}
            placeholder="Is the Ugreen 145W power bank worth it?"
            className={inputCls}
          />
        </label>

        <label className="flex flex-col gap-1.5">
          <span className="text-[13px] font-medium text-[var(--text-primary)]">Details</span>
          <textarea
            value={details}
            onChange={(e) => setDetails(e.target.value)}
            rows={4}
            placeholder="What specifically are you unsure about?"
            className={`${PUBLIC_TEXTAREA} resize-y`}
          />
        </label>

        <label className="flex flex-col gap-1.5">
          <span className="text-[13px] font-medium text-[var(--text-primary)]">Shopee / Lazada link (optional)</span>
          <input
            value={sourceUrl}
            onChange={(e) => setSourceUrl(e.target.value)}
            placeholder="https://shopee.ph/…"
            className={inputCls}
          />
        </label>

        {errors.length > 0 ? (
          <ul role="alert" className="flex flex-col gap-1 rounded-[var(--radius-sm)] bg-[color-mix(in_srgb,var(--accent-danger)_10%,transparent)] px-4 py-3 text-[13px] text-[var(--accent-danger)]">
            {errors.map((e, i) => (
              <li key={i}>{e}</li>
            ))}
          </ul>
        ) : null}

        <div className="flex items-center gap-3">
          <Button type="submit" disabled={!ready || busy}>
            {busy ? "Posting…" : "Post request"}
          </Button>
        </div>
      </div>
    </form>
  );
}

// Figma TextField (6808:456): every state from the shared public field classes.
const inputCls = PUBLIC_INPUT;
