import Image from "next/image";
import Link from "next/link";
import { ArrowLeft, UserCircle } from "@phosphor-icons/react/dist/ssr";

import { BackControl } from "@/components/site/BackControl";
import { usablePhoto } from "@/lib/image";

/**
 * The phone bar of a detail page: Figma "NavBar" Type=Detail (7023:1280), as
 * drawn on Screen/Question (7731:15603) and Screen/Question/Thread — 72px of
 * brand orange (#ef5821), a 28px ArrowLeft 16px in, then on the right the
 * page's own controls (a 28px DotsThree at x286) and the 40px avatar ending on
 * the 16px gutter, 20px past them.
 *
 * Below `md` only: it replaces the site header there, which the page renders
 * from `md` up (no frame draws a wider Detail bar). The review page and the
 * store page draw the same bar inline (ReviewDetail, SellerPageBar).
 *
 * The avatar goes to the reader's profile, or to log in when nobody is signed
 * in — the frames draw only the signed-in state.
 */
export function DetailNavBar({
  label,
  backFallback,
  user,
  loginHref = "/login",
  children,
}: {
  /** What the bar is for, for screen readers ("Question"). */
  label: string;
  /** Where Back goes for a page opened cold (BUG-033). */
  backFallback: string;
  user: { username: string | null; avatarUrl: string | null } | null;
  loginHref?: string;
  /** The page's own bar controls, white on the orange (e.g. its ⋯ menu). */
  children?: React.ReactNode;
}) {
  const avatar = usablePhoto(user?.avatarUrl ?? null);
  return (
    <nav
      aria-label={label}
      className="sticky top-0 z-30 flex h-[72px] items-center justify-between bg-[var(--accent-primary)] px-4 text-[var(--text-on-brand)] md:hidden"
    >
      <BackControl
        fallbackHref={backFallback}
        label="Back"
        className="-ml-1.5 grid h-10 w-10 place-items-center rounded-full hover:bg-white/15"
      >
        <ArrowLeft size={28} />
      </BackControl>
      <div className="flex items-center gap-2">
        {children}
        <Link
          href={user ? "/profile" : loginHref}
          aria-label={user ? "Your profile" : "Log in"}
          className="grid h-10 w-10 place-items-center overflow-hidden rounded-full hover:opacity-90"
        >
          {avatar ? (
            <Image src={avatar} alt="" width={40} height={40} className="h-10 w-10 rounded-full object-cover" />
          ) : user?.username ? (
            <span className="grid h-10 w-10 place-items-center rounded-full bg-[var(--surface-card)] text-[14px] font-medium text-[var(--text-primary)]">
              {user.username[0]?.toUpperCase()}
            </span>
          ) : (
            <UserCircle size={40} weight="light" />
          )}
        </Link>
      </div>
    </nav>
  );
}
