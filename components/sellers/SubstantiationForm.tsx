"use client";

import { useRouter } from "next/navigation";
import { useId, useState } from "react";

import { Button } from "@/components/ui/Button";
import { FieldMessage } from "@/components/ui/FieldMessage";
import { PUBLIC_TEXTAREA } from "@/components/ui/field-styles";

/** The reviewer's one answer to an admin's substantiation request (§10). */
export function SubstantiationForm({ appealId }: { appealId: string }) {
  const router = useRouter();
  const id = useId();
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!text.trim() || busy) return;
    setBusy(true);
    setError(null);
    try {
      const res = await fetch(`/api/bff/api/v1/sellers/appeals/${appealId}/substantiation`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ response: text.trim() }),
      });
      if (!res.ok) {
        const p = (await res.json().catch(() => ({}))) as { detail?: unknown };
        setError(typeof p.detail === "string" ? p.detail : "Couldn't send your answer.");
        return;
      }
      router.refresh();
    } catch {
      setError("Couldn't reach the server.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} className="mt-6 flex flex-col gap-3">
      <label htmlFor={id} className="text-[13px] font-medium text-[var(--text-primary)]">
        Your answer
      </label>
      <textarea
        id={id}
        value={text}
        onChange={(e) => setText(e.target.value.slice(0, 4000))}
        rows={5}
        placeholder="For example: your order number and date, what arrived, and when. Links aren't allowed."
        aria-invalid={error ? true : undefined}
        aria-describedby={error ? `${id}-error` : undefined}
        className={`${PUBLIC_TEXTAREA} resize-y`}
      />
      {error ? (
        <FieldMessage id={`${id}-error`} tone="error">
          {error}
        </FieldMessage>
      ) : null}
      <div>
        <Button type="submit" disabled={!text.trim() || busy}>
          {busy ? "Sending…" : "Send to the admin"}
        </Button>
      </div>
    </form>
  );
}
