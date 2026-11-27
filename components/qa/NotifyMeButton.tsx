"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Bell, BellRinging } from "@phosphor-icons/react";

/**
 * "Notify me!" on a question (QA-045, Figma question frame): a new answer
 * reaches the reader's notifications instead of their having to check back.
 * Signed-out readers are sent to log in first and come back here.
 */
export function NotifyMeButton({
  questionId,
  initiallySubscribed,
  signedIn,
}: {
  questionId: string;
  initiallySubscribed: boolean;
  signedIn: boolean;
}) {
  const router = useRouter();
  const [on, setOn] = useState(initiallySubscribed);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function toggle() {
    if (!signedIn) {
      router.push(`/login?next=${encodeURIComponent(`/questions/${questionId}`)}`);
      return;
    }
    const next = !on;
    setPending(true);
    setError(null);
    try {
      const res = await fetch(`/api/bff/api/v1/questions/${questionId}/subscription`, {
        method: "PUT",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ subscribed: next }),
      });
      if (!res.ok) {
        setError("Couldn't update your notification.");
        return;
      }
      setOn(next);
    } catch {
      setError("Couldn't reach the server.");
    } finally {
      setPending(false);
    }
  }

  const Icon = on ? BellRinging : Bell;
  return (
    <span className="inline-flex flex-col items-start gap-1">
      <button
        type="button"
        onClick={toggle}
        disabled={pending}
        aria-pressed={on}
        className="inline-flex cursor-pointer items-center gap-1.5 rounded-[var(--radius-pill)] border border-[var(--line-hairline-30)] px-3 py-1.5 text-[12px] font-medium text-[var(--text-primary)] hover:border-[var(--accent-primary)] hover:text-[var(--accent-primary)] disabled:opacity-60 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--accent-primary)]"
      >
        <Icon size={16} weight={on ? "fill" : "regular"} aria-hidden="true"
              className={on ? "text-[var(--accent-primary)]" : undefined} />
        {on ? "You'll be notified" : "Notify me!"}
      </button>
      {error ? <span role="alert" className="text-[11px] text-[var(--accent-danger)]">{error}</span> : null}
    </span>
  );
}
