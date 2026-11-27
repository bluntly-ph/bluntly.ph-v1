import { Bar, Block, Pill, SkeletonRegion } from "@/components/ui/Skeleton";

/**
 * A member's report while it is computed, in ReportFrame's order: the back
 * link, the title with its period and "Generated" lines beside the download
 * buttons, the period form, the figure cards, then the sections.
 */
export function ReportLoading({ label, figures = 4, sections = 2 }: { label: string; figures?: number; sections?: number }) {
  return (
    <SkeletonRegion label={`Loading ${label}`} className="flex flex-col gap-4">
      <Bar size={10} className="w-24" />
      <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
        <span className="flex flex-col gap-2">
          <Bar size={18} className="w-64 max-w-full" />
          <Bar size={10} className="w-48" />
          <Bar size={8} className="w-56" />
        </span>
        <span className="flex flex-wrap gap-2">
          <Pill className="h-9 w-28" />
          <Pill className="h-9 w-28" />
          <Pill className="h-9 w-24" />
        </span>
      </div>
      <div className="flex flex-wrap items-end gap-2 rounded-[var(--radius-md)] bg-[var(--surface-card)] p-3 shadow-[var(--shadow-hairline-inset)]">
        {["w-28", "w-20"].map((w, i) => (
          <span key={i} className="flex flex-col gap-2">
            <Bar size={8} className="w-12" />
            <Block className={`h-8 ${w}`} />
          </span>
        ))}
        <Pill className="h-8 w-16" />
      </div>
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        {Array.from({ length: figures }, (_, i) => (
          <div key={i} className="flex flex-col gap-2.5 rounded-[var(--radius-md)] bg-[var(--surface-card)] px-4 py-3 shadow-[var(--shadow-card)]">
            <Bar size={10} className="w-24" />
            <Bar size={18} className="w-16" />
          </div>
        ))}
      </div>
      {Array.from({ length: sections }, (_, s) => (
        <div key={s} className="flex flex-col gap-3 rounded-[var(--radius-md)] bg-[var(--surface-card)] px-4 py-3 shadow-[var(--shadow-card)]">
          <Bar size={14} className="w-36" />
          <Bar size={10} className="w-56 max-w-full" />
        </div>
      ))}
    </SkeletonRegion>
  );
}
