import { describe, expect, it } from 'vitest';
import { cardFacts, SHARE_SIZE } from './share-card';
import type { Player } from '../types';

describe('share card facts', () => {
  it('uses sanitized display stats without inventing real-life touches', () => {
    const facts = cardFacts({first_name: '  DizZy   ', level: 12, total_touches: 10482,
      best_streak: 7, achievements: ['FIRST_TOUCH', 'ERROR_404']} as Player);
    expect(facts.name).toBe('DizZy');
    expect(facts.touches.replace(/\D/g, '')).toBe('10482');
    expect(facts.achievements).toBe(2);
    expect(facts.streak).toBe(7);
    expect(SHARE_SIZE.height).toBeGreaterThan(SHARE_SIZE.width);
  });
});
