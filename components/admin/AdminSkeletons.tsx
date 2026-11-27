import {
  Bar,
  Block,
  Circle,
  type ColumnSpec,
  IconButtonsSkeleton,
  MetricRowSkeleton,
  PaginationSkeleton,
  Pill,
  SegmentedSkeleton,
  SkeletonRegion,
  TableSkeleton,
} from "@/components/ui/Skeleton";

/**
 * The Admin console's loading states, one family per screen shape.
 *
 * `loading.tsx` renders INSIDE app/admin/layout.tsx (Next.js nests it in the
 * segment's layout), so the shell — rail, top bar, the page title and the
 * Reports section tabs — is already real while these show. They draw the
 * workspace only, with the loaded screen's geometry: its toolbar, figure cards,
 * table columns (as wide as the real ones), and pager. Tables keep their
 * `min-w` and are clipped below it, as the real ones scroll sideways.
 *
 * Built only from the shared primitives (components/ui/Skeleton.tsx).
 */

const CARD = "rounded-[16px] border border-[var(--border-subtle)] bg-[var(--surface-card)]";

/** A list screen's toolbar: tabs, then (right-aligned) icon buttons and actions. */
function Toolbar({ tabs, icons = 0, round = false, actions = [] }: {
  tabs: number;
  icons?: number;
  round?: boolean;
  actions?: string[];
}) {
  return (
    <div className="flex flex-wrap items-center gap-2">
      {tabs ? <SegmentedSkeleton count={tabs} /> : null}
      <span className="flex-1" />
      {icons ? <IconButtonsSkeleton count={icons} round={round} /> : null}
      {actions.map((w, i) => (
        <Pill key={i} className={`h-8 ${w}`} />
      ))}
    </div>
  );
}

/** A card's heading: a 16 px title and, optionally, its 12 px subtitle. */
function CardHead({ title = "w-36", sub }: { title?: string; sub?: string }) {
  return (
    <span className="flex flex-col gap-2">
      <Bar size={14} className={title} />
      {sub ? <Bar size={8} className={sub} /> : null}
    </span>
  );
}

// ---------------------------------------------------------------- list screens

export type AdminListSpec = {
  label: string;
  /** Segmented-control tabs (0 = none). */
  tabs: number;
  icons?: number;
  round?: boolean;
  /** Width classes of the toolbar's action pills, left to right. */
  actions?: string[];
  /** Figure cards above the table, and their grid. */
  stats?: number;
  /** The Affiliate ledger: three columns of labelled rows above the table. */
  ledger?: boolean;
  statsGrid?: string;
  columns: ColumnSpec[];
  minWidth?: number;
  rows?: number;
  pager?: boolean;
};

/**
 * Products, People, Sellers, Payouts, Honesty Fund, Special routing, Affiliate:
 * a toolbar, maybe figure cards, a table, the pager.
 */
export function AdminListSkeleton({ spec }: { spec: AdminListSpec }) {
  return (
    <SkeletonRegion label={spec.label} className="flex flex-col gap-4">
      <Toolbar tabs={spec.tabs} icons={spec.icons} round={spec.round} actions={spec.actions} />
      {spec.stats ? <MetricRowSkeleton count={spec.stats} className={spec.statsGrid ?? "gap-4 md:grid-cols-3"} /> : null}
      {spec.ledger ? (
        <div className={`${CARD} grid gap-6 p-4 md:grid-cols-3`}>
          {Array.from({ length: 3 }, (_, c) => (
            <span key={c} className="flex flex-col gap-3">
              <Bar size={8} className="w-16" />
              {Array.from({ length: 4 }, (_, i) => (
                <span key={i} className="flex items-center gap-3">
                  <Bar size={10} className="w-20" />
                  <Bar size={8} className="flex-1" />
                  <Bar size={10} className="w-8" />
                </span>
              ))}
            </span>
          ))}
        </div>
      ) : null}
      <TableSkeleton columns={spec.columns} minWidth={spec.minWidth} rows={spec.rows ?? 10} />
      {spec.pager === false ? null : <PaginationSkeleton />}
    </SkeletonRegion>
  );
}

const thumb = (track?: string): ColumnSpec => ({ kind: "thumb", track });
const person = (track?: string): ColumnSpec => ({ kind: "avatar", track });
const text = (track?: string): ColumnSpec => ({ kind: "text", track });
const lines = (track?: string): ColumnSpec => ({ kind: "lines", track });
const chip = (track?: string): ColumnSpec => ({ kind: "chip", track });
const action = (track = "120px"): ColumnSpec => ({ kind: "action", track });
const figure = (track?: string): ColumnSpec => ({ kind: "figure", track });

/** The screens that are a toolbar and a table (survey of the loaded screens, 2026-10-04). */
export const ADMIN_LISTS = {
  products: {
    label: "Loading products",
    tabs: 2, icons: 3, round: true, actions: ["w-20", "w-28"],
    columns: [thumb("minmax(0,2.4fr)"), text(), person(), figure("90px"), text("110px"), action()],
  },
  people: {
    label: "Loading people",
    tabs: 4, icons: 3, round: true,
    columns: [person("minmax(0,1.6fr)"), lines("minmax(0,1.4fr)"), chip(), figure("90px"), chip(),
      text("110px"), action()],
  },
  sellers: {
    label: "Loading sellers",
    tabs: 3, icons: 3, minWidth: 960,
    columns: [thumb("minmax(0,1.8fr)"), lines(), text(), person(), text("110px"), action()],
  },
  payouts: {
    label: "Loading payouts",
    tabs: 5, icons: 3, actions: ["w-36"], stats: 3,
    columns: [person("minmax(0,1.6fr)"), figure("110px"), lines(), text(), text(), action()],
  },
  honestyFund: {
    label: "Loading the Honesty Fund",
    tabs: 5, icons: 2, stats: 3, minWidth: 720, pager: false,
    columns: [thumb("minmax(0,1.6fr)"), figure(), figure(), figure(), figure(), chip()],
  },
  specialRouting: {
    label: "Loading special routing",
    tabs: 1, stats: 3, statsGrid: "gap-3 sm:grid-cols-3", minWidth: 880,
    columns: [thumb("minmax(0,2fr)"), chip(), figure("80px"), text("100px"), lines(), action()],
  },
  affiliate: {
    label: "Loading affiliate transactions",
    tabs: 4, icons: 3, round: true, actions: ["w-32"], ledger: true,
    columns: [thumb("minmax(0,1.6fr)"), person(), chip(), chip(), figure(), text("110px")],
  },
} satisfies Record<string, AdminListSpec>;

// ---------------------------------------------------------------- the queue

/** Review queue (Reviews tab): tabs, the Queue switch, icons, the 7-column table, pager. */
export function AdminQueueSkeleton() {
  return (
    <SkeletonRegion label="Loading the queue" className="flex flex-col">
      <div className="flex flex-wrap items-center gap-2 pb-4">
        <SegmentedSkeleton count={4} />
        <span className="flex-1" />
        <Pill className="h-[18px] w-[30px]" />
        <Bar size={14} className="mr-2 w-12" />
        <IconButtonsSkeleton count={4} />
      </div>
      <Bar size={10} className="mb-[13px] w-[640px] max-w-full" />
      <TableSkeleton
        minWidth={960}
        rows={10}
        columns={[thumb("31%"), text("15%"), figure("8%"), text("14%"), figure("9%"), text("13%"), text("10%")]}
      />
      <PaginationSkeleton className="mt-4" />
    </SkeletonRegion>
  );
}

// ---------------------------------------------------------------- overview

/** /admin: Review queue + Needs attention, then Affiliate earnings. */
export function AdminOverviewSkeleton() {
  return (
    <SkeletonRegion label="Loading the overview" className="flex flex-col gap-4">
      <div className="grid gap-4 xl:grid-cols-[394px_minmax(0,1fr)]">
        <div className={`${CARD} flex min-w-0 flex-col gap-[10px] p-5`}>
          <CardHead title="w-28" />
          <div className="flex justify-between gap-2 border-b border-[var(--border-subtle)] pb-[9px] pt-1">
            {Array.from({ length: 4 }, (_, i) => (
              <Bar key={i} size={10} className="w-14" />
            ))}
          </div>
          <div className="flex flex-col">
            {Array.from({ length: 5 }, (_, i) => (
              <div key={i} className="flex items-center gap-3 border-t border-[var(--border-subtle)] py-[7px] first:border-t-0">
                <Block className="size-9" />
                <span className="flex min-w-0 flex-1 flex-col gap-2">
                  <Bar size={10} className="w-4/5" />
                  <Bar size={8} className="w-1/2" />
                </span>
                <Bar size={8} className="w-8" />
              </div>
            ))}
          </div>
        </div>
        <div className={`${CARD} flex min-w-0 flex-col gap-4 p-5`}>
          <div className="flex items-center justify-between">
            <CardHead title="w-36" />
            <Bar size={8} className="w-12" />
          </div>
          <div className="grid flex-1 gap-x-7 gap-y-5 sm:grid-cols-2">
            {[4, 4, 2, 2].map((rows, g) => (
              <div key={g} className="flex flex-col">
                <Bar size={8} className="mb-[10px] w-20" />
                {Array.from({ length: rows }, (_, i) => (
                  <div key={i} className="flex items-center gap-[10px] border-t border-[var(--border-subtle)] py-[9px]">
                    <Circle size={18} />
                    <Bar size={10} className="flex-1" />
                    <Bar size={10} className="w-6" />
                  </div>
                ))}
              </div>
            ))}
          </div>
        </div>
      </div>
      <div className="grid gap-4 xl:grid-cols-[394px_minmax(0,1fr)]">
        {[3, 5].map((rows, c) => (
          <div key={c} className={`${CARD} flex min-w-0 flex-col gap-[10px] p-5`}>
            <div className="flex items-center justify-between">
              <CardHead title={c ? "w-44" : "w-16"} />
              <Bar size={8} className="w-20" />
            </div>
            {Array.from({ length: rows }, (_, i) => (
              <div key={i} className={`flex items-center gap-3 ${c ? "py-[7px]" : "py-2"}`}>
                <Circle size={c ? 28 : 36} />
                <span className="flex min-w-0 flex-1 flex-col gap-2">
                  <Bar size={10} className="w-3/4" />
                  {c ? null : <Bar size={8} className="w-1/2" />}
                </span>
                <Bar size={8} className="w-8" />
              </div>
            ))}
          </div>
        ))}
      </div>
      <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_300px]">
      <div className={`${CARD} flex min-w-0 flex-col gap-[14px] p-5`}>
        <div className="flex items-center justify-between">
          <CardHead title="w-40" />
          <Pill className="h-7 w-40" />
        </div>
        <div className="flex flex-col gap-6 md:flex-row">
          <div className="flex flex-col gap-3 md:w-[273px]">
            <Bar size={8} className="w-16" />
            <Bar size={18} className="my-[5px] w-36" />
            <Bar size={8} className="w-48" />
            {[2, 2].map((rows, g) => (
              <div key={g} className="mt-2 flex flex-col gap-3 border-t border-[var(--border-subtle)] pt-4">
                <Bar size={10} className="w-24" />
                {Array.from({ length: rows }, (_, i) => (
                  <div key={i} className="flex items-center gap-3">
                    <Bar size={8} className="flex-1" />
                    <Bar size={8} className="w-14" />
                  </div>
                ))}
              </div>
            ))}
          </div>
          <Block className="h-[248px] flex-1" />
        </div>
      </div>
        <div className={`${CARD} flex min-w-0 flex-col gap-3 p-5`}>
          <CardHead title="w-36" />
          <Bar size={8} className="w-24" />
          <Bar size={18} className="my-[9px] w-40" />
          {Array.from({ length: 3 }, (_, i) => (
            <div key={i} className="flex items-center gap-2">
              <Bar size={10} className="flex-1" />
              <Bar size={10} className="w-6" />
            </div>
          ))}
          <div className="border-t border-[var(--border-subtle)] pt-3">
            <Bar size={10} className="w-32" />
          </div>
        </div>
      </div>
    </SkeletonRegion>
  );
}

// ---------------------------------------------------------------- activity

/** Activity log: subtitle + Export, the filter row, day cards beside the side panel. */
export function AdminActivitySkeleton() {
  return (
    <SkeletonRegion label="Loading the activity log" className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center gap-3">
        <Bar size={14} className="w-72 max-w-full" />
        <span className="flex-1" />
        <Pill className="h-8 w-20" />
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <Block className="h-8 w-[256px]" />
        {["w-24", "w-28", "w-28", "w-28"].map((w, i) => (
          <Pill key={i} className={`h-8 ${w}`} />
        ))}
      </div>
      <div className="grid grid-cols-[minmax(0,1fr)] gap-4 lg:grid-cols-[minmax(0,1fr)_328px]">
        <div className="flex min-w-0 flex-col gap-4">
          {[5, 3].map((entries, d) => (
            <div key={d} className={`${CARD} overflow-hidden`}>
              <div className="flex justify-between bg-[var(--surface-app)] px-4 py-3">
                <Bar size={14} className="w-24" />
                <Bar size={10} className="w-16" />
              </div>
              {Array.from({ length: entries }, (_, i) => (
                <div key={i} className="flex gap-3 border-t border-[var(--border-subtle)] px-4 py-3">
                  <Circle size={32} />
                  <span className="flex min-w-0 flex-1 flex-col gap-3 py-1.5">
                    <Bar size={10} className="w-4/5" />
                    <Bar size={8} className="w-2/5" />
                  </span>
                  <Bar size={8} className="mt-1.5 w-12" />
                </div>
              ))}
            </div>
          ))}
        </div>
        <div className="flex flex-col gap-4">
          {[4, 5, 3, 3].map((rows, c) => (
            <div key={c} className={`${CARD} p-4`}>
              <CardHead title="w-32" sub="w-40" />
              <div className="mt-3 flex flex-col gap-3">
                {Array.from({ length: rows }, (_, i) => (
                  <Bar key={i} size={10} className={i % 2 ? "w-3/4" : "w-full"} />
                ))}
              </div>
            </div>
          ))}
        </div>
      </div>
    </SkeletonRegion>
  );
}

// ---------------------------------------------------------------- analytics

const SMALL_CARD = `${CARD} p-4`;

/** Analytics: range control, five KPIs, then the chart, funnel and breakdown cards. */
export function AdminAnalyticsSkeleton() {
  return (
    <SkeletonRegion label="Loading analytics" className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center gap-3">
        <Bar size={14} className="w-64 max-w-full" />
        <span className="flex-1" />
        <Pill className="h-8 w-20" />
        <Block className="h-[30px] w-56" />
      </div>
      <div className="grid grid-cols-2 gap-3 md:grid-cols-5">
        {Array.from({ length: 5 }, (_, i) => (
          <div key={i} className={`${SMALL_CARD} flex flex-col gap-2.5`}>
            <Bar size={10} className="w-20" />
            <Bar size={18} className="w-16" />
            <Bar size={8} className="w-24" />
          </div>
        ))}
      </div>
      <div className="grid gap-4 lg:grid-cols-[minmax(0,1.6fr)_minmax(0,1fr)]">
        <div className={SMALL_CARD}>
          <CardHead title="w-32" sub="w-48" />
          <Block className="mt-4 h-[250px] w-full" />
        </div>
        <div className={SMALL_CARD}>
          <CardHead title="w-24" sub="w-40" />
          <div className="mt-4 flex flex-col gap-5">
            {Array.from({ length: 4 }, (_, i) => (
              <span key={i} className="flex flex-col gap-2">
                <Bar size={10} className="w-1/2" />
                <Bar size={8} className="w-full" />
              </span>
            ))}
          </div>
        </div>
      </div>
      <div className="grid gap-4 lg:grid-cols-2">
        {[0, 1].map((c) => (
          <div key={c} className={SMALL_CARD}>
            <CardHead title="w-28" sub="w-44" />
            <div className="mt-4 grid grid-cols-3 gap-3">
              {Array.from({ length: 3 }, (_, i) => (
                <span key={i} className="flex flex-col gap-2.5">
                  <Bar size={8} className="w-20" />
                  <Bar size={18} className="w-14" />
                  <Bar size={8} className="w-24" />
                </span>
              ))}
            </div>
            <Bar size={8} className="mt-6 w-full" />
            <Bar size={10} className="mt-3 w-1/2" />
            <span className="mt-4 block border-t border-[var(--border-subtle)] pt-4">
              <Bar size={10} className="w-3/4" />
            </span>
          </div>
        ))}
      </div>
      <div className="grid gap-4 lg:grid-cols-[minmax(0,1.6fr)_minmax(0,1fr)]">
        <div className={SMALL_CARD}>
          <CardHead title="w-28" />
          <div className="mt-4 flex flex-col gap-4">
            {Array.from({ length: 5 }, (_, i) => (
              <div key={i} className="flex items-center gap-4">
                <Bar size={10} className="flex-1" />
                <Bar size={10} className="w-10" />
                <Bar size={10} className="w-10" />
                <Bar size={10} className="w-12" />
              </div>
            ))}
          </div>
        </div>
        <div className={SMALL_CARD}>
          <CardHead title="w-36" />
          <div className="mt-4 flex flex-col gap-4">
            {Array.from({ length: 5 }, (_, i) => (
              <span key={i} className="flex flex-col gap-2">
                <Bar size={10} className="w-1/3" />
                <Bar size={8} className={["w-full", "w-4/5", "w-3/5", "w-2/5", "w-1/4"][i]} />
              </span>
            ))}
          </div>
        </div>
      </div>
    </SkeletonRegion>
  );
}

// ---------------------------------------------------------------- settings

/** Settings: the section links beside the section cards. */
export function AdminSettingsSkeleton() {
  return (
    <SkeletonRegion label="Loading settings" className="flex flex-col gap-4">
      <Bar size={14} className="w-80 max-w-full" />
      <div className="grid gap-4 lg:grid-cols-[180px_minmax(0,1fr)]">
        <div className="flex flex-wrap gap-1 lg:flex-col">
          {["w-12", "w-24", "w-16", "w-24", "w-20", "w-24"].map((w, i) => (
            <span key={i} className="flex h-9 items-center px-3">
              <Bar size={14} className={w} />
            </span>
          ))}
        </div>
        <div className="flex min-w-0 flex-col gap-4">
          <div className={`${CARD} p-5`}>
            <CardHead title="w-20" sub="w-56" />
            <div className="mt-4 flex flex-col">
              {Array.from({ length: 4 }, (_, i) => (
                <div key={i} className="flex items-center gap-4 border-t border-[var(--border-subtle)] py-[9px] first:border-t-0">
                  <Circle size={28} />
                  <Bar size={10} className="flex-1" />
                  <Bar size={10} className="w-24" />
                  <Pill className="h-8 w-20" />
                </div>
              ))}
            </div>
          </div>
          {[4, 3].map((fields, s) => (
            <div key={s} className={`${CARD} p-5`}>
              <CardHead title="w-32" sub="w-64" />
              <div className="mt-4 grid gap-3 sm:grid-cols-2">
                {Array.from({ length: fields }, (_, i) => (
                  <span key={i} className="flex flex-col gap-2">
                    <Bar size={8} className="w-24" />
                    <Block className="h-12 w-full" />
                  </span>
                ))}
              </div>
            </div>
          ))}
        </div>
      </div>
    </SkeletonRegion>
  );
}

// ---------------------------------------------------------------- investigation

/** A person's investigation page: the header, the five tabs, the Overview cards. */
export function AdminPersonSkeleton() {
  return (
    <SkeletonRegion label="Loading this person" className="flex flex-col gap-5">
      <div className="flex flex-wrap items-center gap-4">
        <Circle size={64} />
        <span className="flex min-w-0 flex-1 flex-col gap-3">
          <Bar size={18} className="w-56 max-w-full" />
          <Bar size={10} className="w-72 max-w-full" />
        </span>
        <Pill className="h-9 w-32" />
        <Pill className="h-9 w-24" />
      </div>
      <SegmentedSkeleton count={5} />
      <div className="grid gap-4 xl:grid-cols-2">
        <div className={`${CARD} flex flex-col gap-4 p-5`}>
          <CardHead title="w-16" />
          <Bar size={18} className="w-20" />
          <Bar size={8} className="w-full" />
          <Block className="h-[110px] w-full" />
        </div>
        {[5, 6, 6].map((rows, c) => (
          <div key={c} className={`${CARD} flex flex-col gap-4 p-5`}>
            <CardHead title="w-32" />
            <div className="flex flex-col">
              {Array.from({ length: rows }, (_, i) => (
                <div key={i} className="flex items-center gap-3 border-t border-[var(--border-subtle)] py-2 first:border-t-0">
                  {c === 0 ? <Circle size={28} /> : null}
                  <Bar size={10} className="flex-1" />
                  <Bar size={10} className="w-12" />
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>
    </SkeletonRegion>
  );
}

// ---------------------------------------------------------------- reports

/** Reports: month and Generate, the split, the three flows, the reports table. */
export function AdminReportsSkeleton() {
  return (
    <SkeletonRegion label="Loading reports" className="flex flex-col gap-4">
      <div className="flex items-center gap-2">
        <Pill className="h-8 w-40" />
        <span className="flex-1" />
        <Pill className="h-8 w-36" />
      </div>
      <div className={`${CARD} flex flex-col gap-4 p-5`}>
        <Bar size={10} className="w-32" />
        <Bar size={18} className="w-28" />
        <Block className="h-3 w-full" />
        <div className="flex flex-wrap gap-x-8 gap-y-2">
          {Array.from({ length: 4 }, (_, i) => (
            <Bar key={i} size={10} className="w-24" />
          ))}
        </div>
      </div>
      <div className="flex flex-col gap-4 md:flex-row">
        {Array.from({ length: 3 }, (_, i) => (
          <div key={i} className={`${CARD} flex flex-1 flex-col gap-2.5 px-5 py-4`}>
            <Bar size={10} className="w-24" />
            <Bar size={18} className="w-20" />
            <Bar size={10} className="w-32" />
            <span className="mt-1 border-t border-[var(--border-subtle)] pt-2">
              <Bar size={8} className="w-28" />
            </span>
          </div>
        ))}
      </div>
      <TableSkeleton
        minWidth={860}
        rows={5}
        columns={[thumb("380px"), text("180px"), text("160px"), text("140px"), action("130px")]}
      />
    </SkeletonRegion>
  );
}

/**
 * A generated report (Commissions, Honesty Fund) and Seller ratings: its own
 * heading with downloads, the period form, the figure cards, the tables.
 */
export function AdminReportFrameSkeleton({ figures = 4, tables = 2, label = "Loading the report" }: {
  figures?: number;
  tables?: number;
  label?: string;
}) {
  return (
    <SkeletonRegion label={label} className="flex flex-col gap-4">
      <div className="flex flex-col gap-3 md:flex-row md:justify-between">
        <span className="flex flex-col gap-2">
          <Bar size={18} className="w-56" />
          <Bar size={10} className="w-40" />
        </span>
        <span className="flex flex-wrap gap-2">
          <Pill className="h-9 w-24" />
          <Pill className="h-9 w-24" />
          <Pill className="h-9 w-16" />
        </span>
      </div>
      <div className={`${CARD} flex flex-wrap items-end gap-2 p-3`}>
        {Array.from({ length: 2 }, (_, i) => (
          <span key={i} className="flex flex-col gap-2">
            <Bar size={8} className="w-12" />
            <Block className="h-8 w-28" />
          </span>
        ))}
        <Pill className="h-9 w-20" />
      </div>
      {figures ? (
        <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
          {Array.from({ length: figures }, (_, i) => (
            <div key={i} className={`${CARD} flex flex-col gap-2.5 px-4 py-3`}>
              <Bar size={10} className="w-24" />
              <Bar size={18} className="w-20" />
            </div>
          ))}
        </div>
      ) : null}
      {Array.from({ length: tables }, (_, t) => (
        <div key={t} className={`${CARD} overflow-hidden`}>
          <Bar size={14} className="mx-4 mb-1 mt-3 w-40" />
          {Array.from({ length: 6 }, (_, r) => (
            <div key={r} className="flex gap-6 border-t border-[var(--border-subtle)] px-4 py-2.5 first-of-type:border-t-0">
              {Array.from({ length: 6 }, (_, c) => (
                <Bar key={c} size={10} className={c === 0 ? "w-32" : "w-16"} />
              ))}
            </div>
          ))}
        </div>
      ))}
    </SkeletonRegion>
  );
}

// ---------------------------------------------------------------- small screens

/** Price observations: the explanation, then the decision table — each row ends in a note field and
 * Approve / Reject, so rows are about 96 px. */
export function AdminPricesSkeleton() {
  const grid = { display: "grid", gridTemplateColumns: "minmax(0,1.3fr) 110px 90px 100px minmax(0,1.6fr) 180px", minWidth: 832 };
  return (
    <SkeletonRegion label="Loading price observations" className="flex flex-col gap-3">
      {/* The explanation beside Sort / Filters / Search, as loaded (MQA-007/042). */}
      <span className="flex flex-wrap items-start gap-3">
        <span className="flex min-w-0 max-w-[52rem] flex-1 flex-col gap-2">
          <Bar size={10} className="w-full" />
          <Bar size={10} className="w-full" />
          <Bar size={10} className="w-3/5" />
        </span>
        <IconButtonsSkeleton count={3} />
      </span>
      <div className={`${CARD} overflow-hidden`}>
        <div style={grid} className="h-10 items-center gap-0 bg-[var(--surface-app)]">
          {Array.from({ length: 6 }, (_, i) => (
            <span key={i} className="px-4">
              <Bar size={8} className="w-14" />
            </span>
          ))}
        </div>
        {Array.from({ length: 6 }, (_, r) => (
          <div key={r} style={grid} className="items-start border-t border-[var(--border-subtle)] py-3">
            {[["w-28", "w-0"], ["w-14", "w-24"], ["w-12", "w-0"], ["w-14", "w-0"], ["w-4/5", "w-20"]].map(([a, b], c) => (
              <span key={c} className="flex flex-col gap-2 px-4">
                <Bar size={10} className={a} />
                {b !== "w-0" ? <Bar size={8} className={b} /> : null}
              </span>
            ))}
            <span className="flex flex-col gap-2 px-4">
              <Block className="h-8 w-full" />
              <span className="flex gap-2">
                <Pill className="h-7 w-20" />
                <Pill className="h-7 w-16" />
              </span>
            </span>
          </div>
        ))}
      </div>
      <PaginationSkeleton />
    </SkeletonRegion>
  );
}

/** User management: the explanation, the search card, the results. */
export function AdminUsersSkeleton() {
  return (
    <SkeletonRegion label="Loading user management" className="flex flex-col gap-4">
      <span className="flex max-w-[55rem] flex-col gap-2">
        <Bar size={10} className="w-full" />
        <Bar size={10} className="w-2/3" />
      </span>
      <div className={`${CARD} flex flex-col gap-2 p-4 sm:flex-row`}>
        <Pill className="h-11 flex-1" />
        <Pill className="h-11 w-28" />
      </div>
      <Block className="h-48 w-full" />
    </SkeletonRegion>
  );
}

/** QA sandbox: heading and note, the testers form, a card per tester. */
export function AdminQaSandboxSkeleton() {
  return (
    <SkeletonRegion label="Loading the QA sandbox" className="flex flex-col gap-4">
      <span className="flex max-w-[52rem] flex-col gap-2">
        <Bar size={18} className="w-40" />
        <Bar size={10} className="w-full" />
        <Bar size={10} className="w-3/5" />
      </span>
      <div className={`${CARD} p-4`}>
        <CardHead title="w-24" sub="w-72" />
        <div className="mt-3 flex flex-wrap items-end gap-2">
          <Block className="h-8 w-64" />
          <Pill className="h-8 w-24" />
        </div>
      </div>
      {[3, 2].map((rows, c) => (
        <div key={c} className={`${CARD} p-4`}>
          <div className="flex items-center gap-3">
            <CardHead title="w-32" sub="w-48" />
            <span className="flex-1" />
            <Pill className="h-8 w-20" />
          </div>
          <div className="mt-2 flex flex-col">
            {Array.from({ length: rows }, (_, i) => (
              <div key={i} className="flex items-center gap-3 border-t border-[var(--border-subtle)] py-2.5">
                <Bar size={10} className="flex-1" />
                <Block className="h-8 w-20" />
                <Pill className="h-8 w-20" />
              </div>
            ))}
          </div>
        </div>
      ))}
    </SkeletonRegion>
  );
}

/** Inbox (Screen/Admin/Inbox/Loading, Figma 8314:31910): tabs, the list, the thread. */
export function AdminInboxSkeleton() {
  return (
    <SkeletonRegion label="Loading the inbox" className="flex h-[calc(100%-40px)] min-h-[520px] flex-col gap-4">
      <Toolbar tabs={4} icons={3} />
      <div className={`${CARD} flex min-h-0 flex-1 overflow-hidden`}>
        <div className="flex w-full flex-col gap-1 p-2 lg:w-[340px] lg:border-r lg:border-[var(--border-subtle)]">
          {Array.from({ length: 7 }, (_, i) => (
            <div key={i} className="flex gap-3 px-3 py-3">
              <Circle size={32} />
              <span className="flex flex-1 flex-col gap-2 pt-1">
                <Bar size={10} className="w-3/5" />
                <Bar size={8} className="w-4/5" />
              </span>
            </div>
          ))}
        </div>
        <div className="hidden flex-1 flex-col lg:flex">
          <div className="flex items-center gap-3 border-b border-[var(--border-subtle)] px-5 py-3">
            <Circle size={32} />
            <span className="flex flex-1 flex-col gap-2">
              <Bar size={14} className="w-32" />
              <Bar size={8} className="w-48" />
            </span>
            <Pill className="h-9 w-28" />
            <Pill className="h-9 w-20" />
            <Block className="size-8" />
          </div>
          <div className="flex flex-1 flex-col gap-4 px-5 py-4">
            <Block className="h-16 w-2/5" />
            <Block className="ml-auto h-20 w-2/5" />
            <Block className="h-12 w-1/3" />
          </div>
          <div className="border-t border-[var(--border-subtle)] px-5 py-4">
            <Block className="h-11 w-full" />
          </div>
        </div>
      </div>
    </SkeletonRegion>
  );
}
