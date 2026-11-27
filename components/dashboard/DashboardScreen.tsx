import Image from "next/image";
import Link from "next/link";
import { ArrowLeft, ChatCircleDots } from "@phosphor-icons/react/dist/ssr";

import { BackControl } from "@/components/site/BackControl";
import { SiteHeader, type HeaderUser } from "@/components/site/SiteHeader";

/**
 * The chrome every dashboard sub-screen shares.
 *
 * Transfer (5762:332), History (5762:472) and Reviews (6159:1510) all open the
 * same way: a 72px nav carrying a back arrow and the Contributor pill, an
 * orange hero, then a white sheet with a rounded top edge. Building it once
 * means the four screens cannot drift apart from each other, which is the
 * failure the entry frame already had when its hero was an absolutely
 * positioned overlay.
 *
 * `heroHeight` is the frame's own hero depth. It differs per screen — 510 on
 * Transfer, shallower on History — so it is a prop rather than a constant.
 *
 * WEBSITE: the frames are phones, and a 430px orange strip centred on a monitor
 * with no site navigation is what the owner rejected (review, 2026-09-16). From
 * `md` the site header returns and the column widens; from `lg` the hero
 * becomes a sticky card at the left and the sheet's content reads beside it.
 */
export function DashboardScreen({
  user,
  title,
  backHref = "/dashboard",
  hero,
  heroHeight = 402,
  trustLevel,
  parentLabel = "Dashboard",
  children,
}: {
  /** For the site header, which the website shows above the screen. */
  user: HeaderUser;
  /**
   * What the screen is. The frames draw no title — the hero and the sheet are
   * the whole composition — so it is read out on the phone and drawn on the
   * website, where a page with no heading is just a slab of figures.
   */
  title: string;
  backHref?: string;
  hero: React.ReactNode;
  /**
   * The account's computed level (`users.trust_level_name`). The frame's pill
   * reads "Contributor"; drawing that text for every account would be a
   * decorative trust level (contract §9), so the pill carries the real one.
   */
  trustLevel: string;
  heroHeight?: number;
  /** The page `backHref` leads to, named on the website's back link (QA-016). */
  parentLabel?: string;
  children?: React.ReactNode;
}) {
  return (
    <>
      <div className="hidden md:block">
        <SiteHeader user={user} />
      </div>
      {/* Under 768px a flex column at least a screen tall, so the white sheet
          runs to the foot of the screen as every frame draws it; with a short
          list it stopped under the last row and the grey page showed below
          (History, compared against 5762:472 on 2026-09-17).
          <main>: the dashboard screens had no main landmark, so assistive
          tech could not skip the site header to the content (full-system QA,
          found by the real-stack width sweep). */}
      <main className="mx-auto w-full max-w-[430px] max-md:flex max-md:min-h-dvh max-md:flex-col md:max-w-[40rem] md:pt-6 lg:grid lg:max-w-[64rem] lg:grid-cols-[24rem_minmax(0,1fr)] lg:items-start lg:gap-10 lg:px-10 lg:py-10">
        <div
          className="relative md:overflow-hidden md:rounded-[28px] lg:sticky lg:top-[96px]"
          style={{ background: DASHBOARD_GRADIENT }}
        >
          <DashboardNav backHref={backHref} trustLevel={trustLevel} />

          <div className="relative z-10" style={{ minHeight: `${Math.max(heroHeight - 72, 0)}px` }}>
            {hero}
          </div>
        </div>

        {/* The frame's white sheet, pulled up over the hero's foot so its rounded
          top edge reads as the sheet sitting on the gradient rather than as a
          gap between two blocks. White with a 32px top radius, as Transfer
          (6161:1690) and History (5762:614) draw it — it was the grey app
          surface at 28px. The hero sits above it (z-10) so a card that
          straddles the edge, like History's, is not painted over. */}
        <div className="relative -mt-8 min-h-[40vh] flex-1 rounded-t-[32px] bg-[var(--surface-card)] pt-6 lg:mt-0 lg:min-h-0 lg:rounded-none lg:bg-transparent lg:pt-0">
          {/* QA-016: on the website the hero's arrow is a white glyph on the
              gradient card beside the content, which the retest did not read
              as navigation. From lg the content column also carries a worded
              link up to the parent page — a plain link, so it works the same
              after a direct visit, when there is no page behind this one. */}
          <Link
            href={backHref}
            className="mb-3 hidden w-fit items-center gap-1 rounded-[var(--radius-sm)] text-[14px] font-medium text-[var(--text-secondary)] no-underline hover:text-[var(--accent-primary)] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--accent-primary)] lg:inline-flex"
          >
            <ArrowLeft size={18} aria-hidden="true" />
            {parentLabel}
          </Link>
          <h1 className="sr-only px-4 lg:not-sr-only lg:mb-5 lg:px-0 lg:text-[24px] lg:font-bold lg:text-[var(--text-primary)]">
            {title}
          </h1>
          {children}
        </div>
      </main>
    </>
  );
}

/**
 * The dashboard gradient every frame paints behind its hero: Reviewer Dashboard
 * 5572:7130, Transfer 6015:1311, History 6152:683 (read 2026-09-17). The frames
 * vary the angle by a few degrees (116–126); one angle keeps the four screens
 * from shifting as a reviewer moves between them. It replaces an invented
 * orange-to-#c2410c ramp that lost the frame's peach highlight.
 */
export const DASHBOARD_GRADIENT =
  "linear-gradient(120deg, rgb(255, 197, 150) 13.15%, rgb(239, 120, 45) 26.85%, rgb(150, 55, 25) 92.12%)";

/**
 * NavBar type "Profile" (7023:1271): a transparent 72px bar, the 28px back
 * arrow 24px in, and the trust pill — #f2f2f2 with a same-colour 1px border,
 * 32px tall, 12px sides, the 16px mark 4px before 12px Regular ink, and a
 * 0 4 2 25% drop shadow — 24px from the right edge.
 *
 * QA-018: the arrow goes BACK — to the page the reader came from, usually
 * their profile, since the avatar is how the dashboard is reached — and only
 * falls back to `backHref` when there is no in-app page behind this one.
 */
export function DashboardNav({
  backHref,
  trustLevel,
  tone = "onGradient",
  unread,
}: {
  backHref: string;
  trustLevel: string;
  /** "light": the white bar of Screen/Dashboard 7833:9534 (ink arrow). */
  tone?: "onGradient" | "light";
  /**
   * Unread conversations. When given, the bar carries the frame's "Chat" link
   * (7833:9536: a 24px ChatCircleDots in a 32px box, 12px before the stage
   * pill) to /messages, with the brand dot while anything is unread. Every
   * screen under Screen/Dashboard draws it; DashboardBar passes it there.
   */
  unread?: number;
}) {
  const arrow =
    tone === "light"
      ? "text-[var(--text-primary)] focus-visible:outline-[var(--accent-primary)]"
      : "text-white focus-visible:outline-white";
  return (
    <div className="flex h-[72px] items-center justify-between px-6">
      <BackControl
        fallbackHref={backHref}
        className={`-ml-1 cursor-pointer rounded-full p-1 focus-visible:outline focus-visible:outline-2 ${arrow}`}
      >
        <ArrowLeft size={28} weight="regular" />
      </BackControl>
      <div className="flex items-center gap-3">
      {unread !== undefined ? (
        <Link
          href="/messages"
          aria-label={unread > 0 ? `Messages, ${unread} unread` : "Messages"}
          className={`relative grid size-8 place-items-center rounded-full focus-visible:outline focus-visible:outline-2 ${arrow}`}
        >
          <ChatCircleDots size={24} aria-hidden="true" />
          {unread > 0 ? <span aria-hidden="true" className="absolute right-[3px] top-[3px] size-[6px] rounded-full bg-[var(--accent-primary)]" /> : null}
        </Link>
      ) : null}
      <span className="inline-flex h-8 items-center gap-1 rounded-[16px] border border-[#f2f2f2] bg-[#f2f2f2] px-3 text-[12px] leading-none text-[var(--text-primary)] [filter:drop-shadow(0_4px_2px_rgba(0,0,0,0.25))]">
        <Image src="/icon.svg" alt="" width={16} height={16} className="h-4 w-4" />
        {trustLevel}
      </span>
      </div>
    </div>
  );
}

/**
 * The centred "Est. Comm" + amount the Transfer and entry frames both show:
 * 48px under the bar, 12px Regular at 70% white over 32px SemiBold #f2f2f7 on
 * its natural line, 4px apart, the pair carrying a 0 4 2 25% drop shadow
 * (6164:1694). It was 13px Medium over 40px Bold.
 */
export function HeroAmount({
  label,
  amount,
  children,
}: {
  label: string;
  amount: string;
  children?: React.ReactNode;
}) {
  return (
    <div className="pb-10 pt-12 text-center">
      <div className="[filter:drop-shadow(0_4px_2px_rgba(0,0,0,0.25))]">
        <p className="text-[12px] leading-none text-white/70">{label}</p>
        <p className="mt-1 text-[32px] font-semibold leading-normal text-[#f2f2f7] [font-variant-numeric:tabular-nums]">
          {amount}
        </p>
      </div>
      {children}
    </div>
  );
}
