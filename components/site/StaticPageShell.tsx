import type { ReactNode } from "react";

import { SiteFooter } from "@/components/site/SiteFooter";
import { SiteHeader } from "@/components/site/SiteHeader";

/**
 * PageShell for pages with nothing per-reader in them (About, Terms, FAQs, …),
 * so they can be built once and served from the CDN.
 *
 * It must never read the session: no `getUser`, no `cookies()`, nothing from
 * lib/dal or lib/session. Any of those makes the page dynamic again, and every
 * visit runs a function (tests/frontend/static-pages.test.mjs guards this). The
 * account corner finds the reader in the browser instead (`account="session"`).
 *
 * Same layout as components/site/PageShell, which stays for pages that render
 * per request anyway.
 */
export function StaticPageShell({
  children,
  width = "prose",
}: {
  children: ReactNode;
  width?: "prose" | "wide";
}) {
  const max = width === "prose" ? "max-w-[46rem]" : "max-w-[72rem]";

  return (
    <div className="flex min-h-dvh flex-col bg-[var(--surface-app)]">
      <SiteHeader user={null} account="session" />
      <main className={`mx-auto w-full flex-1 px-6 py-10 lg:px-10 lg:py-16 ${max}`}>
        {children}
      </main>
      <SiteFooter />
    </div>
  );
}

export default StaticPageShell;
