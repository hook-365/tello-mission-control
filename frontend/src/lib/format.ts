export type BatteryLevel = 'critical' | 'low' | 'ok';

export function getBatteryLevel(battery: number): BatteryLevel {
  if (battery <= 20) return 'critical';
  if (battery <= 50) return 'low';
  return 'ok';
}

export function batteryTextColor(battery: number): string {
  const level = getBatteryLevel(battery);
  return level === 'critical' ? 'text-danger' : level === 'low' ? 'text-caution' : 'text-ok';
}

export function batteryBarColor(battery: number): string {
  const level = getBatteryLevel(battery);
  return level === 'critical'
    ? 'bg-danger animate-pulse-glow'
    : level === 'low'
      ? 'bg-caution'
      : 'bg-ok';
}

export function pad(n: number): string {
  return String(n).padStart(2, '0');
}

export function formatFlightTime(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return `${m}:${pad(s)}`;
}

/** Whole seconds between two ISO timestamps (0 if either is missing or out of order). */
export function secondsBetween(startIso: string, endIso: string | null | undefined): number {
  if (!endIso) return 0;
  const ms = new Date(endIso).getTime() - new Date(startIso).getTime();
  return Number.isFinite(ms) && ms > 0 ? Math.round(ms / 1000) : 0;
}
