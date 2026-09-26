/** Small pure view helpers. The server remains authoritative for progress and rewards. */
export function progressPercent(progress: number, target: number): number {
  if (!Number.isFinite(progress) || !Number.isFinite(target) || target <= 0) return 0;
  return Math.round(Math.max(0, Math.min(100, progress / target * 100)));
}

export function isReportStale(reportDate: string, now: Date = new Date()): boolean {
  // A forecast belongs to the UTC day, independent of the phone's local timezone.
  return reportDate !== now.toISOString().slice(0, 10);
}
