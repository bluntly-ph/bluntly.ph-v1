import { Bar, Block, Circle, SkeletonRegion } from "@/components/ui/Skeleton";

/**
 * /profile and /u/[id] while they load: ProfileLayout's grid (the 22rem card at
 * the left from `lg`), the profile card — its brand-gradient banner is static
 * chrome, so it is drawn for real — with the avatar, name, meta line and the
 * stats, then the section tabs and a grid of review cards.
 */
export function ProfilePageSkeleton({ label, tabs = 4 }: { label: string; tabs?: number }) {
  return (
    <SkeletonRegion
      label={label}
      className="mx-auto w-full max-w-[42rem] flex-1 pb-16 md:px-6 md:pt-6 lg:grid lg:max-w-[72rem] lg:grid-cols-[22rem_minmax(0,1fr)] lg:items-start lg:gap-10 lg:px-10 lg:pt-10"
    >
      <div>
        <div aria-hidden="true" className="h-[116px] bg-[image:var(--brand-gradient)] md:rounded-t-[16px]" />
        <div className="relative bg-[var(--surface-card)] px-8 pb-[38px] md:rounded-b-[16px] md:shadow-[var(--shadow-card)]">
          <Circle size={80} className="absolute -top-[34px] left-8 ring-4 ring-[var(--surface-card)]" />
          <div className="pt-[62px]">
            <Bar size={18} className="w-52 max-w-full" />
            <Bar size={8} className="mt-3 w-56 max-w-full" />
            <Bar size={8} className="mt-2 w-24" />
            <div className="-mx-4 mt-[46px] grid grid-cols-3 gap-x-3 gap-y-6">
              {Array.from({ length: 3 }, (_, i) => (
                <span key={i} className="flex flex-col items-center gap-3">
                  <Bar size={14} className="w-8" />
                  <Bar size={8} className="w-16" />
                </span>
              ))}
            </div>
          </div>
        </div>
      </div>
      <div>
        <div className="flex justify-center gap-6 border-b border-[var(--line-hairline-10)] pb-[23px] pt-4 sm:gap-8 lg:justify-start lg:gap-10 lg:pt-1">
          {/* 4 x 64 + 3 x 32 overran a 320px screen; the real labels are 35-80px. */}
          {Array.from({ length: tabs }, (_, i) => (
            <Bar key={i} size={14} className="w-12 sm:w-16" />
          ))}
        </div>
        <ul className="md:mt-6 md:grid md:grid-cols-2 md:gap-4 lg:gap-5">
          {Array.from({ length: 4 }, (_, i) => (
            <li key={i} className="flex flex-col gap-3 border-b border-[var(--line-hairline-10)] bg-[var(--surface-card)] p-4 md:rounded-[16px] md:border-0 md:shadow-[var(--shadow-card)]">
              <span className="flex items-center gap-2">
                <Circle size={24} />
                <Bar size={8} className="w-40" />
              </span>
              <Block className="h-44 w-full" />
              <Bar size={14} className="w-3/4" />
              <Bar size={8} className="w-24" />
            </li>
          ))}
        </ul>
      </div>
    </SkeletonRegion>
  );
}
