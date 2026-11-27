/** Admin Analytics' formatters (Figma Screen/Admin/Analytics 8071:16115). Pure. */

/** "5h 20m", "7h 05m", "45m", "under 1m" — the frame's Median decision time. */
export function hoursMinutes(hours: number | null | undefined): string {
  if (hours == null || !Number.isFinite(hours)) return "—";
  const minutes = Math.round(hours * 60);
  if (minutes < 1) return "under 1m";
  const h = Math.floor(minutes / 60);
  const m = minutes % 60;
  return h === 0 ? `${m}m` : `${h}h ${String(m).padStart(2, "0")}m`;
}

/** "Oldest waiting 3 days" / "… 5 h" / "… under an hour"; null with nothing waiting. */
export function oldestWaiting(iso: string | null | undefined, now: number): string | null {
  if (!iso) return null;
  const ms = now - new Date(iso).getTime();
  if (!Number.isFinite(ms)) return null;
  const hours = Math.floor(ms / 3_600_000);
  if (hours < 1) return "Oldest waiting under an hour";
  if (hours < 48) return `Oldest waiting ${hours} h`;
  return `Oldest waiting ${Math.floor(hours / 24)} days`;
}
