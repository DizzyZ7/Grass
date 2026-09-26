import { describe, it, expect } from 'vitest';
import { isReportStale, progressPercent } from './field';

describe('personal field report presentation', () => {
  it('clamps untrusted or incomplete progress to safe display values', () => {
    expect(progressPercent(40, 80)).toBe(50);
    expect(progressPercent(200, 80)).toBe(100);
    expect(progressPercent(-3, 80)).toBe(0);
    expect(progressPercent(Number.NaN, 0)).toBe(0);
  });
  it('rolls reports on UTC date, not the phone local date', () => {
    expect(isReportStale('2026-09-26', new Date('2026-09-26T23:59:58Z'))).toBe(false);
    expect(isReportStale('2026-09-26', new Date('2026-09-27T00:00:00Z'))).toBe(true);
  });
});
