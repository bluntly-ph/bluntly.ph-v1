import type { Metadata } from "next";

import { Unsubscribe } from "@/components/account/Unsubscribe";
import { scopeOf } from "@/components/account/unsubscribe-model";
import { PageShell } from "@/components/site/PageShell";
import { apiFetch } from "@/lib/api/client";

export const metadata: Metadata = {
  title: "Unsubscribe — bluntly",
  robots: { index: false, follow: false },
};

/**
 * The footer link of every notification and weekly summary email (backend 0085).
 * Public: the signed token says which account and which email. Reading it changes
 * nothing; the button does (components/account/Unsubscribe.tsx).
 */
export default async function UnsubscribePage({ searchParams }: { searchParams: Promise<{ [key: string]: string | string[] | undefined }> }) {
  const raw = (await searchParams).token;
  const token = typeof raw === "string" ? raw.slice(0, 200) : "";
  let found: { scope: unknown; subscribed: boolean } | null = null;
  if (token) {
    try {
      found = await apiFetch(`/api/v1/email/unsubscribe?token=${encodeURIComponent(token)}`);
    } catch {
      found = null;
    }
  }
  const scope = found ? scopeOf(found.scope) : null;

  return (
    <PageShell>
      <div className="flex flex-col items-center gap-6 py-10 lg:py-16">
        <h1 className="text-[24px] font-bold text-[var(--text-primary)] lg:text-[30px]">Email settings</h1>
        {found && scope ? (
          <Unsubscribe token={token} scope={scope} subscribed={found.subscribed} />
        ) : (
          <p className="max-w-[28rem] text-center text-[15px] text-[var(--text-secondary)]">
            This unsubscribe link isn&rsquo;t valid. You can change which emails you get in your store&rsquo;s Settings.
          </p>
        )}
      </div>
    </PageShell>
  );
}
