/**
 * Overlay/Admin/Export (Figma 8237:25470): what the admin export can hold, how
 * many files each part makes, and the download URL. Pure, so tests/frontend can
 * check it.
 */

export type AdminExportKey = "activity" | "moderation" | "earnings" | "analytics";

export const ADMIN_EXPORT_SECTIONS: { key: AdminExportKey; label: string; what: string; files: number }[] = [
  { key: "activity", label: "Activity log", what: "Every moderator and system action", files: 1 },
  { key: "moderation", label: "Reviews and moderation", what: "Decisions, reports, escalations", files: 1 },
  // Commissions, payout readiness, remittances; Honesty Fund reviews and cycles.
  { key: "earnings", label: "Earnings and payouts", what: "Commissions, payouts, Honesty Fund", files: 5 },
  { key: "analytics", label: "Analytics summary", what: "The numbers on the Analytics page", files: 1 },
];

/** The Analytics page's ranges, so the export matches what it shows. */
export const ADMIN_EXPORT_PERIODS: { key: string; label: string }[] = [
  { key: "7d", label: "Last 7 days" },
  { key: "30d", label: "Last 30 days" },
  { key: "90d", label: "Last 90 days" },
  { key: "12m", label: "Last 12 months" },
];

export const exportPeriodLabel = (key: string) => (ADMIN_EXPORT_PERIODS.find((p) => p.key === key) ?? ADMIN_EXPORT_PERIODS[1]).label;

export function adminExportFiles(chosen: AdminExportKey[]): string {
  const n = ADMIN_EXPORT_SECTIONS.filter((s) => chosen.includes(s.key)).reduce((sum, s) => sum + s.files, 0);
  return `${n} file${n === 1 ? "" : "s"}`;
}

export function adminExportHref(chosen: AdminExportKey[], period: string): string {
  const order = ADMIN_EXPORT_SECTIONS.map((s) => s.key).filter((k) => chosen.includes(k));
  return `/api/bff/api/v1/admin/export?include=${order.join(",")}&period=${encodeURIComponent(period)}`;
}
