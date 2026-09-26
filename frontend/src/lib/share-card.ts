/** Original art drawn locally: no image downloads, tracking, or third-party assets. */
import type { Player } from '../types';

export const SHARE_SIZE = { width: 1080, height: 1350 } as const;

export function cardFacts(player: Pick<Player, 'first_name' | 'level' | 'total_touches' | 'best_streak' | 'achievements'>) {
  const name = player.first_name.trim().slice(0, 48) || 'Анонимный ботаник';
  return {
    name,
    touches: new Intl.NumberFormat('ru-RU').format(Math.max(0, player.total_touches)),
    level: Math.max(1, player.level),
    achievements: player.achievements.length,
    streak: player.best_streak,
  };
}

function roundRect(ctx: CanvasRenderingContext2D, x: number, y: number, w: number, h: number, r: number) {
  ctx.beginPath(); ctx.roundRect(x, y, w, h, r);
}

function grassBlade(ctx: CanvasRenderingContext2D, x: number, y: number, len: number, bend: number, color: string) {
  ctx.fillStyle = color;
  ctx.beginPath(); ctx.moveTo(x - 10, y);
  ctx.quadraticCurveTo(x + bend * .2 - 10, y - len * .6, x + bend, y - len);
  ctx.quadraticCurveTo(x + bend * .7 + 13, y - len * .38, x + 11, y);
  ctx.closePath(); ctx.fill();
}

export function paintShareCard(canvas: HTMLCanvasElement, player: Player, location: string, speciesColor = '#b4ff85'): void {
  const ctx = canvas.getContext('2d');
  if (!ctx) throw new Error('Ваш браузер не поддерживает Canvas.');
  const { width: w, height: h } = SHARE_SIZE;
  canvas.width = w; canvas.height = h;
  const facts = cardFacts(player);
  const bg = ctx.createLinearGradient(0, 0, w, h);
  bg.addColorStop(0, '#0d1d20'); bg.addColorStop(.65, '#102922'); bg.addColorStop(1, '#224326');
  ctx.fillStyle = bg; ctx.fillRect(0, 0, w, h);
  ctx.strokeStyle = '#d6ffa11a'; ctx.lineWidth = 2;
  for (let x = 0; x < w; x += 72) { ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, h); ctx.stroke(); }
  for (let y = 0; y < h; y += 72) { ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(w, y); ctx.stroke(); }
  ctx.shadowBlur = 50; ctx.shadowColor = '#a8fd7060';
  roundRect(ctx, 52, 55, w - 104, h - 110, 52); ctx.fillStyle = '#142c25'; ctx.fill(); ctx.shadowBlur = 0;
  ctx.strokeStyle = '#9edc815e'; ctx.lineWidth = 3; ctx.stroke();

  ctx.fillStyle = '#d2ffa7'; ctx.font = '800 67px system-ui,sans-serif';
  ctx.fillText('TOUCH GRASS.exe', 106, 160);
  ctx.fillStyle = '#99b6a8'; ctx.font = '500 29px ui-monospace,monospace';
  ctx.fillText('СИМУЛЯТОР СОЦИАЛИЗАЦИИ • BY DIZZY', 108, 210);

  roundRect(ctx, 101, 258, w - 202, 94, 22); ctx.fillStyle = '#213c2b'; ctx.fill();
  ctx.fillStyle = '#e0f9df'; ctx.font = 'bold 41px system-ui,sans-serif';
  let title = facts.name;
  while (ctx.measureText(title).width > w - 268 && title.length > 2) title = title.slice(0, -2) + '…';
  ctx.fillText(title, 134, 323);
  ctx.fillStyle = '#b4e69b'; ctx.textAlign = 'right';
  ctx.font = 'bold 30px ui-monospace,monospace'; ctx.fillText(`LVL ${facts.level}`, w - 135, 320);
  ctx.textAlign = 'left';

  ctx.font = '900 143px system-ui,sans-serif'; ctx.fillStyle = '#d5ff8e';
  ctx.fillText(facts.touches, 105, 537, w - 210);
  ctx.font = '600 38px system-ui,sans-serif'; ctx.fillStyle = '#f0ffdb';
  ctx.fillText('РАЗ ПОТРОГАЛ ТРАВУ', 110, 601);
  ctx.fillStyle = '#a6c0ab'; ctx.font = '34px system-ui,sans-serif';
  ctx.fillText('Настоящую — 0. Пока что.', 110, 657);

  // A quiet field of distinct vector blades. Every card is self-contained PNG.
  const field = ctx.createLinearGradient(0, 710, 0, 1040);
  field.addColorStop(0, '#17392f'); field.addColorStop(1, '#0a271a');
  roundRect(ctx, 101, 710, w - 202, 345, 35); ctx.fillStyle = field; ctx.fill();
  ctx.save(); ctx.beginPath(); ctx.roundRect(102, 711, w - 204, 343, 34); ctx.clip();
  for (let i = 0; i < 105; i++) {
    const x = 85 + i * 9.1;
    const len = 82 + ((i * 73) % 165);
    const bend = Math.sin(i * 2.3) * 32;
    grassBlade(ctx, x, 1056 + (i * 19) % 32, len, bend, i % 5 === 0 ? '#e7ffad' : i % 3 === 0 ? speciesColor : '#75c47a');
  }
  ctx.restore();
  ctx.fillStyle = '#eaffd5'; ctx.font = 'bold 35px system-ui,sans-serif';
  ctx.fillText(location.slice(0, 34), 124, 772);

  ctx.fillStyle = '#b4d2ba'; ctx.font = '27px ui-monospace,monospace';
  ctx.fillText(`ДОСТИЖЕНИЙ ${facts.achievements}    СЕРИЯ ${facts.streak} ДН.`, 115, 1123);
  ctx.fillStyle = '#e5ffd3'; ctx.font = 'bold 38px system-ui,sans-serif';
  ctx.fillText('Мне сказали трогать траву.', 115, 1194);
  ctx.fillStyle = '#a8e87e'; ctx.fillText('Я написал для этого бота.', 115, 1240);
}

export async function makeSharePng(player: Player, location: string, color?: string): Promise<Blob> {
  const canvas = document.createElement('canvas');
  paintShareCard(canvas, player, location, color);
  return new Promise((resolve, reject) => canvas.toBlob(
    blob => blob ? resolve(blob) : reject(new Error('Не удалось создать PNG.')),
    'image/png', 1));
}
