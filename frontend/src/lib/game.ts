import type { Batch, Player } from '../types';

export const SESSION_SECONDS = 90;
export const FLUSH_INTERVAL_MS = 2800;
export const MAX_CLIENT_BATCH = 80;

export function timeLeft(startedAt: string, now = Date.now()): number {
  const passed = Math.max(0, Math.floor((now - Date.parse(startedAt)) / 1000));
  return Math.max(0, SESSION_SECONDS - passed);
}

export function xpRatio(player: Player): number {
  const needed = player.next_level_xp - player.current_level_xp;
  return needed ? Math.min(1, Math.max(0, (player.xp - player.current_level_xp) / needed)) : 0;
}

export function makeBatch(seq: number, touches: number, durationMs: number, combo: number): Batch {
  return { batch_id: crypto.randomUUID(), seq, touches: Math.min(MAX_CLIENT_BATCH, touches),
           duration_ms: Math.min(30000, Math.max(0, durationMs)), peak_combo: Math.min(300, combo) };
}

export function formatInt(value: number): string {
  return new Intl.NumberFormat('ru-RU').format(value);
}
