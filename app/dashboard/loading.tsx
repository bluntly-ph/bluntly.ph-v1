import { DashboardActions } from "@/components/dashboard/ContributorDashboard";
import { SiteHeaderSkeleton } from "@/components/site/SiteHeader";
import { Block, Circle, Pill } from "@/components/ui/Skeleton";

const BARS = [38, 70, 50, 46, 62, 34, 82];

function Frame({ children }: { children: React.ReactNode }) {
  return (
    <div className="mb-4 rounded-[32px] bg-[var(--surface-app)] p-[3px]">
      {children}
    </div>
  );
}

/**
 * The dashboard while its figures load (Figma Screen/Dashboard/Loading
 * 7855:10750): the three action cards are drawn for real, since they need no
 * data, then grey frames in the shape of the wallet, the earnings chart and
 * the trust ladder, so nothing jumps when the real cards arrive.
 */
export default function Loading() {
  return (
    <>
      <div className="hidden md:block">
        <SiteHeaderSkeleton />
      </div>
      <div className="min-h-dvh bg-[var(--surface-card)]">
        <div className="mx-auto w-full max-w-[390px] px-4 pt-[76px] md:max-w-[880px] md:px-6 md:pt-6">
          <DashboardActions />
          <div
            role="status"
            aria-busy="true"
            aria-live="polite"
            className="md:columns-2 md:gap-4"
          >
            <span className="sr-only">Loading your dashboard</span>
            <Frame>
              <div className="rounded-[32px] bg-[var(--surface-card)] p-5">
                <Block className="h-[150px] bg-[var(--surface-app)]" />
              </div>
              <div className="flex items-center justify-between px-5 py-4">
                <Pill className="h-3 w-[110px] bg-[var(--surface-card)]" />
                <Pill className="h-6 w-[80px] bg-[var(--surface-card)]" />
              </div>
            </Frame>
            <Frame>
              <div className="flex flex-col gap-3 rounded-[32px] bg-[var(--surface-card)] p-5">
                <Pill className="h-3 w-[90px] bg-[var(--surface-app)]" />
                <div className="flex gap-3">
                  <Pill className="h-6 w-[110px] bg-[var(--surface-app)]" />
                  <Pill className="h-6 w-[90px] bg-[var(--surface-app)]" />
                </div>
              </div>
              <div className="flex h-[96px] items-end gap-2 px-5 pb-4 pt-3">
                {BARS.map((h, i) => (
                  <Block className="flex-1 bg-[var(--surface-card)]" key={i}
                    style={{ height: `${h}%` }} />
                ))}
              </div>
            </Frame>
            <Frame>
              <div className="flex flex-col gap-3 rounded-[32px] bg-[var(--surface-card)] p-5">
                <Pill className="h-4 w-[140px] bg-[var(--surface-app)]" />
                <Pill className="h-3 w-[200px] bg-[var(--surface-app)]" />
                <div className="flex items-center gap-2 pt-1">
                  {[0, 1, 2, 3, 4].map((i) => (
                    <span key={i} className="contents">
                      {i > 0 ? (
                        <span
                          aria-hidden
                          className="h-[2px] flex-1 bg-[var(--surface-app)]"
                        />
                      ) : null}
                      <Circle size={32} className="bg-[var(--surface-app)]" />
                    </span>
                  ))}
                </div>
              </div>
            </Frame>
          </div>
        </div>
      </div>
    </>
  );
}
