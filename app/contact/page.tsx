import type { Metadata } from "next";

import { Article, type Block } from "@/components/site/Article";
import { StaticPageShell } from "@/components/site/StaticPageShell";

/**
 * Built once and served from the CDN (cost plan, 2026-10-22). "error" fails the
 * build if anything here ever reads cookies, headers or uncached data, rather
 * than quietly rendering every visit again: tests/frontend/static-pages.test.mjs.
 */
export const dynamic = "error";

export const metadata: Metadata = {
  title: "Contact us — bluntly",
  description:
    "Reach the bluntly team about support, moderation, press, partnerships, or feedback.",
};

const BLOCKS: Block[] = [
  {
    type: "lead",
    text: "Questions, feedback, a review that needs a second look, or a partnership idea? We read everything.",
  },
  { type: "h2", text: "Email" },
  {
    type: "node",
    node: (
      <p>
        The fastest way to reach us is{" "}
        <a href="mailto:bluntly.ph@gmail.com">bluntly.ph@gmail.com</a>. We aim to
        reply within a couple of business days.
      </p>
    ),
  },
  { type: "h2", text: "What to reach out about" },
  {
    type: "ul",
    items: [
      "Support — trouble signing in, a payout question, or something not working.",
      "Moderation — a review you think needs another look.",
      "Press & partnerships — collaborations, affiliate programs, and media.",
      "Feedback — anything that would make bluntly better.",
    ],
  },
  {
    type: "p",
    text: "You can also find us on Reddit, Instagram, Facebook, and TikTok — the links are in the footer.",
  },
];

export default function ContactPage() {
  return (
    <StaticPageShell>
      <Article title="Contact us" blocks={BLOCKS} />
    </StaticPageShell>
  );
}
