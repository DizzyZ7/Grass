import { describe, expect, it } from 'vitest';
import { makeBatch, timeLeft, xpRatio } from './game';
import type { Player } from '../types';

describe('game helpers', () => {
  it('clamps time rather than going negative', () => {
    expect(timeLeft('2026-09-26T12:00:00Z', Date.parse('2026-09-26T12:01:31Z'))).toBe(0);
    expect(timeLeft('2026-09-26T12:00:00Z', Date.parse('2026-09-26T12:00:10Z'))).toBe(80);
  });
  it('caps telemetry, not awarded server XP', () => {
    const b = makeBatch(1, 900, -2, 900);
    expect(b.touches).toBe(80);
    expect(b.duration_ms).toBe(0);
    expect(b.peak_combo).toBe(300);
  });
  it('calculates level progress', () => {
    const p = { xp: 150, current_level_xp: 100, next_level_xp: 300 } as Player;
    expect(xpRatio(p)).toBe(0.25);
  });
});
