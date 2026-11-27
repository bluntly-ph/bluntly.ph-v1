import { BrowseNav } from "@/components/site/BrowseRails";
import { SiteHeaderSkeleton } from "@/components/site/SiteHeader";
import { Bar, Block, Pill } from "@/components/ui/Skeleton";

/**
 * The feed's shape while its rows are being fetched.
 *
 * `/feed` shipped without one, so a reader got a blank column for as long as
 * the API took — which on a cold Supabase call is over a second of nothing.
 *
 * The rails are drawn rather than omitted so the three-column grid holds
 * its proportions; leaving them out would let the middle column render wide and
 * then snap narrower when the real rails arrive.
 */
export default function Loading() {
  return (
    <>
      <SiteHeaderSkeleton />
      <div
        role="status"
        aria-busy="true"
        aria-live="polite"
        className="mx-auto w-full max-w-[76rem] px-4 py-6 sm:px-6 lg:px-10 lg:py-10"
      >
        <span className="sr-only">Loading feed</span>

        <div className="lg:grid lg:grid-cols-[11rem_minmax(0,1fr)] lg:items-start lg:gap-10 xl:grid-cols-[11rem_minmax(0,1fr)_17rem]">
          {/* Left rail: static links, so the real one. */}
          <BrowseNav current="feed" />

          <div className="min-w-0">
            <Bar size={18} className="my-[7px] w-40 lg:my-[9px] lg:w-56" />
            <Bar size={14} className="mt-2 w-full max-w-[34rem]" />

            {/* Tab bar */}
            <div className="mt-5 flex gap-4 border-b border-[var(--border-subtle)] pb-3">
              <Bar size={14} className="w-16" />
              <Bar size={14} className="w-14" />
            </div>

            {/* Rows, in the same shape FeedCard renders: square thumbnail, then
                product line, title, verdict row, excerpt, byline. */}
            {Array.from({ length: 5 }, (_, i) => (
              <div
                key={i}
                className="flex gap-4 border-b border-[var(--border-subtle)] py-5 sm:gap-5"
              >
                <Block className="h-20 w-20 sm:h-24 sm:w-24" />
                <div className="flex min-w-0 flex-1 flex-col gap-2">
                  <Bar size={10} className="w-40" />
                  <Bar size={14} className="w-4/5" />
                  <div className="mt-1 flex items-center gap-3">
                    <Pill className="h-6 w-28" />
                    <Bar size={14} className="w-20" />
                  </div>
                  <Bar size={10} className="w-full" />
                  <Bar size={10} className="w-2/3" />
                </div>
              </div>
            ))}
          </div>

          {/* Right rail */}
          <div className="hidden xl:flex xl:flex-col xl:gap-3">
            <Bar size={10} className="w-32" />
            <div className="flex flex-wrap gap-2">
              {Array.from({ length: 6 }, (_, i) => (
                <Pill className="h-8 w-24" key={i} />
              ))}
            </div>
          </div>
        </div>
      </div>
    </>
  );
}
