import type { Metadata, Viewport } from "next";

import { FALLBACK_SHARE_IMAGE } from "@/lib/share-image";
import { SITE_URL } from "@/lib/site-map";
import { Poppins } from "next/font/google";
import "./globals.css";

import { NavigationDepthTracker } from "@/components/site/NavigationDepthTracker";

// Self-hosted by Next rather than the design system's Google Fonts @import, so
// there is no render-blocking third-party request. The weights are the ones the
// source file actually uses.
const poppins = Poppins({
  variable: "--font-poppins",
  subsets: ["latin"],
  weight: ["200", "300", "400", "500", "600", "700"],
  display: "swap",
});

// Bebas Neue was declared here too and is gone: no element used it (no
// `font-accent` anywhere in app/ or components/), yet next/font preloaded its
// file on every page — one of the seven fonts Lighthouse saw requested at high
// priority before any content (production, 2026-09-17).

export const metadata: Metadata = {
  // QA-070: absolute URLs for every page's social image. Without a base, a
  // relative og:image is not a URL any crawler can fetch.
  metadataBase: new URL(SITE_URL),
  title: "bluntly — Finally. Honest reviews.",
  description:
    "Philippine product reviews you can trust. No sponsorships. No bias. Ever.",
  openGraph: {
    siteName: "bluntly",
    type: "website",
    images: [{ url: FALLBACK_SHARE_IMAGE, width: 1200, height: 630, alt: "bluntly" }],
  },
  twitter: { card: "summary_large_image", images: [FALLBACK_SHARE_IMAGE] },
};

export const viewport: Viewport = {
  // One light treatment (docs/DEVIATIONS.md #65).
  themeColor: "#f2f2f2",
};

export default async function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  // Light only: the design of record has one treatment (docs/DEVIATIONS.md
  // #65), and the dead dark-mode toggle was removed (QA-013).
  return (
    <html lang="en" className={`${poppins.variable} h-full`}>
      <body className="min-h-full flex flex-col">
        {/* The mobile bottom navigation was removed on 2026-09-12. Its five
            tabs implied a route model the product does not have, and the
            header avatar is the single navigation entry point now
            (components/site/ProfileNavPanel). The 68px spacer it rendered
            went with it — leaving that behind would have reserved empty space
            at the foot of every mobile page. */}
        {/* Counts the app's own route changes so the site's Back control knows
            whether the page behind this one is ours (BUG-033). Here because the
            root layout is the only component that survives every navigation. */}
        <NavigationDepthTracker />
        {children}
      </body>
    </html>
  );
}
