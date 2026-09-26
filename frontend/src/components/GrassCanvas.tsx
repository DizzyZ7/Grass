import { useEffect, useRef } from 'react';

interface Props {
  active: boolean;
  light: boolean;
  speciesColor?: string;
  skyColor?: string;
  groundColor?: string;
  motion?: string;
  weather?: 'sunny' | 'breezy' | 'rainy' | 'fireflies' | 'aurora';
  onStroke: (touches: number, combo: number) => void;
}
interface Blade {
  x: number; bottom: number; length: number; width: number;
  bend: number; velocity: number; phase: number; shade: number; lastTouch: number;
}
interface Particle { x: number; y: number; vx: number; vy: number; life: number; size: number; }
function makePalette(hex: string): string[] {
  const raw = hex.match(/^#[0-9a-fA-F]{6}$/) ? hex : '#80e077';
  const rgb = [1, 3, 5].map(offset => parseInt(raw.slice(offset, offset + 2), 16));
  return [.55, .7, .85, 1, 1.15, 1.3].map(factor => '#'+rgb.map(channel =>
    Math.max(0, Math.min(255, Math.round(channel * factor))).toString(16).padStart(2, '0')).join(''));
}

function seeded(seed: number): () => number {
  let s = seed | 0;
  return () => {
    s ^= s << 13; s ^= s >>> 17; s ^= s << 5;
    return (s >>> 0) / 4294967296;
  };
}

export default function GrassCanvas({ active, light, speciesColor = '#80e077', skyColor = '#1b4040',
  groundColor = '#4f9361', motion = 'breeze', weather = 'sunny', onStroke }: Props) {
  const ref = useRef<HTMLCanvasElement | null>(null);
  const activeRef = useRef(active);
  const lightRef = useRef(light);
  const strokeRef = useRef(onStroke);
  const appearance = useRef({ palette: makePalette(speciesColor), skyColor, groundColor, motion, weather });
  useEffect(() => { activeRef.current = active; }, [active]);
  useEffect(() => { lightRef.current = light; }, [light]);
  useEffect(() => { strokeRef.current = onStroke; }, [onStroke]);
  useEffect(() => { appearance.current = { palette: makePalette(speciesColor), skyColor, groundColor, motion, weather }; },
    [speciesColor, skyColor, groundColor, motion, weather]);

  useEffect(() => {
    const canvas = ref.current;
    if (!canvas) return;
    const g = canvas.getContext('2d', { alpha: false });
    if (!g) return;
    let w = 360; let h = 360; let raf = 0;
    let last = 0; let lastStroke = 0; let activePointer: number | null = null; let prevX = 0; let prevY = 0;
    let combo = 0; let comboAt = 0;
    const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    const slowDevice = (navigator.hardwareConcurrency || 6) <= 4;
    let blades: Blade[] = [];
    const particles: Particle[] = [];
    const r = seeded(2077);
    const resize = () => {
      const rect = canvas.getBoundingClientRect();
      w = Math.max(240, rect.width); h = Math.max(240, rect.height);
      const dpr = Math.min(window.devicePixelRatio || 1, slowDevice ? 1.25 : 1.65);
      canvas.width = Math.round(w * dpr); canvas.height = Math.round(h * dpr);
      g.setTransform(dpr, 0, 0, dpr, 0, 0);
      const number = Math.min(slowDevice ? 115 : 170, Math.round(w * (slowDevice ? 0.30 : 0.42)));
      blades = Array.from({ length: number }, (_, i) => {
        const near = r();
        return { x: (i + r() * 0.7) / number * w, bottom: h - 15 + r() * 24 - near * 30,
          length: 43 + r() * 95, width: 3 + r() * 5.5, bend: 0, velocity: 0,
          phase: r() * 6.28, shade: Math.floor(r() * 6), lastTouch: 0 };
      }).sort((a, b) => a.length - b.length);
    };
    const onResize = new ResizeObserver(resize);
    onResize.observe(canvas);
    resize();

    const draw = (t: number) => {
      if (document.hidden) { raf = 0; return; }
      const reduced = reducedMotion;
      const rate = reduced ? 18 : slowDevice ? 30 : 45;
      raf = requestAnimationFrame(draw);
      if (t - last < 1000 / rate) return;
      const step = Math.min(2, Math.max(0.5, (t - last) / 22));
      last = t;
      const scene = appearance.current;
      const sky = g.createLinearGradient(0, 0, 0, h);
      if (lightRef.current) {
        sky.addColorStop(0, scene.skyColor); sky.addColorStop(0.60, '#c8f3cc'); sky.addColorStop(1, scene.groundColor);
      } else {
        sky.addColorStop(0, '#101e27'); sky.addColorStop(0.60, scene.skyColor); sky.addColorStop(1, scene.groundColor);
      }
      g.fillStyle = sky; g.fillRect(0, 0, w, h);
      // Golden low sun and drifting dust, painted rather than loaded as licensed art.
      const sunX = w * 0.77; const sunY = h * 0.23;
      const aura = g.createRadialGradient(sunX, sunY, 0, sunX, sunY, w * 0.47);
      aura.addColorStop(0, lightRef.current ? '#fff1a65e' : '#dfefa138');
      aura.addColorStop(1, '#fff2a000');
      g.fillStyle = aura; g.fillRect(0, 0, w, h);
      g.beginPath(); g.arc(sunX, sunY, 22, 0, Math.PI * 2);
      g.fillStyle = lightRef.current ? '#fffcda' : '#d5eeb1'; g.fill();
      for (let i = 0; i < 14; i++) {
        const xx = (i * 107 + 21) % w; const yy = (i * 59 + 18) % (h * 0.62);
        g.fillStyle = lightRef.current ? '#ffffff77' : '#caffb65a';
        g.beginPath(); g.arc(xx, yy + Math.sin(t / 1600 + i) * 3, i % 4 === 0 ? 2 : 1.1, 0, Math.PI * 2); g.fill();
      }
      // Procedural micro-weather: the entire forecast lives in one deterministic
      // server response. No location permissions, image assets, or weather APIs.
      if (scene.weather === 'aurora') {
        const ribbon = g.createLinearGradient(0, 0, w, h * .47);
        ribbon.addColorStop(0, '#79f2d000');
        ribbon.addColorStop(.45, '#98fccc33');
        ribbon.addColorStop(.7, '#bb8bff4d');
        ribbon.addColorStop(1, '#a5c0ff00');
        g.fillStyle = ribbon;
        g.beginPath(); g.moveTo(0, h * .26);
        for (let i = 0; i <= 12; i++) {
          const xx = w * i / 12;
          g.lineTo(xx, h * (.20 + (reduced ? 0 : Math.sin(t * .00042 + i * .7) * .045)));
        }
        g.lineTo(w, h * .55); g.lineTo(0, h * .51); g.fill();
      }
      if (scene.weather === 'rainy') {
        g.strokeStyle = lightRef.current ? '#e7fcff77' : '#b9e9ff66';
        g.lineWidth = 1.15;
        g.beginPath();
        const drops = slowDevice ? 17 : 29;
        for (let i = 0; i < drops; i++) {
          const shift = reduced ? 0 : t * .21;
          const xx = (i * 83 + 11 + shift * .26) % w;
          const yy = (i * 127 + shift) % (h * .86);
          g.moveTo(xx, yy); g.lineTo(xx - 4, yy + 12);
        }
        g.stroke();
      }
      if (scene.weather === 'fireflies') {
        for (let i = 0; i < (slowDevice ? 7 : 13); i++) {
          const fx = (i * 89 + 39 + (reduced ? 0 : Math.sin(t * .00036 + i) * 15)) % w;
          const fy = h * (.14 + (i % 6) * .115) + (reduced ? 0 : Math.sin(t * .00091 + i * 2) * 11);
          const glow = g.createRadialGradient(fx, fy, 0, fx, fy, 10);
          glow.addColorStop(0, '#ecffbecc'); glow.addColorStop(1, '#b7ff8900');
          g.fillStyle = glow; g.fillRect(fx - 10, fy - 10, 20, 20);
        }
      }
      g.fillStyle = scene.groundColor;
      g.beginPath(); g.moveTo(0, h * 0.76);
      g.bezierCurveTo(w * .25, h * .69, w * .38, h * .79, w * .63, h * .70);
      g.bezierCurveTo(w * .83, h * .64, w * .92, h * .71, w, h * .68);
      g.lineTo(w, h); g.lineTo(0, h); g.fill();
      g.fillStyle = lightRef.current ? '#599c58' : scene.palette[0];
      g.beginPath(); g.moveTo(0, h * .90);
      g.quadraticCurveTo(w * .28, h * .79, w * .48, h * .88);
      g.quadraticCurveTo(w * .71, h * .78, w, h * .82); g.lineTo(w, h); g.lineTo(0, h); g.fill();
      // Each blade has spring damping, its own phase, color and width.
      for (const b of blades) {
        b.velocity += (-b.bend * .018 - b.velocity * .115) * step;
        b.bend += b.velocity * step;
        b.bend = Math.max(-39, Math.min(39, b.bend));
        const pace = scene.motion === 'pulse' ? 2.1 : scene.motion === 'shy' ? .65 : 1.0;
        const sway = reduced ? 0 : Math.sin(t * .0013 * pace + b.phase) * (scene.motion === 'pulse' ? 5 : scene.weather === 'breezy' ? 4 : 2);
        const tipX = b.x + b.bend + sway;
        const tipY = b.bottom - b.length;
        g.beginPath();
        g.moveTo(b.x - b.width * .55, b.bottom);
        if (scene.motion === 'pixel') {
          g.lineTo(b.x + b.bend * .35 - b.width, b.bottom - b.length * .52); g.lineTo(tipX, tipY);
        } else {
          g.quadraticCurveTo(b.x + b.bend * .30 - b.width * .35, b.bottom - b.length * .61, tipX, tipY);
        }
        g.quadraticCurveTo(b.x + b.bend * .55 + b.width, b.bottom - b.length * .55, b.x + b.width * .48, b.bottom);
        g.closePath();
        g.fillStyle = scene.palette[b.shade];
        g.fill();
        if (b.shade >= 3) {
          g.strokeStyle = '#eeffbd46'; g.lineWidth = .55; g.beginPath();
          g.moveTo(b.x, b.bottom - 3); g.quadraticCurveTo(b.x + b.bend * .45, b.bottom - b.length * .54,
            tipX, tipY + 3); g.stroke();
        }
      }
      // Two quiet decorative flowers: foreground detail without external assets.
      for (const [x, y, color] of [[w * .19, h - 45, '#fff5c4'], [w * .86, h - 27, '#ffcee3']] as const) {
        const bob = reduced ? 0 : Math.sin(t * .001 + x) * 2;
        g.strokeStyle = '#8dcd7c'; g.lineWidth = 2; g.beginPath();
        g.moveTo(x, y + 18); g.quadraticCurveTo(x + 6 + bob, y + 8, x + bob, y - 6); g.stroke();
        for (let i = 0; i < 5; i++) {
          const a = i * Math.PI * 2 / 5;
          g.fillStyle = color; g.beginPath();
          g.ellipse(x + bob + Math.cos(a) * 5, y - 6 + Math.sin(a) * 5, 4.2, 3.6, a, 0, 6.29); g.fill();
        }
        g.fillStyle = '#f2c85b'; g.beginPath(); g.arc(x + bob, y - 6, 3.8, 0, 6.29); g.fill();
      }
      for (let i = particles.length - 1; i >= 0; i--) {
        const p = particles[i];
        p.x += p.vx * step; p.y += p.vy * step; p.vy += .09 * step; p.life -= .027 * step;
        if (p.life <= 0) { particles.splice(i, 1); continue; }
        g.globalAlpha = Math.min(1, p.life);
        g.fillStyle = scene.palette[5]; g.beginPath(); g.ellipse(p.x, p.y, p.size, p.size / 2, p.vy, 0, 6.29); g.fill();
      }
      g.globalAlpha = 1;
      const shadow = g.createLinearGradient(0, h - 50, 0, h);
      shadow.addColorStop(0, '#0d301700'); shadow.addColorStop(1, '#122f18bb');
      g.fillStyle = shadow; g.fillRect(0, h - 50, w, 50);
    };
    raf = requestAnimationFrame(draw);

    const coords = (event: PointerEvent) => {
      const b = canvas.getBoundingClientRect();
      return { x: event.clientX - b.left, y: event.clientY - b.top };
    };
    const brush = (e: PointerEvent, first: boolean) => {
      if (!activeRef.current) return;
      const { x, y } = coords(e);
      const now = performance.now();
      const dx = first ? 0 : x - prevX;
      const dy = first ? 0 : y - prevY;
      prevX = x; prevY = y;
      if (!first && now - lastStroke < 35) return;
      lastStroke = now;
      let contacts = 0;
      for (const b of blades) {
        const tipY = b.bottom - b.length;
        // Blade segment, not only its center: scratching horizontal & vertical feels natural.
        const along = Math.max(0, Math.min(1, (b.bottom - y) / b.length));
        const nearX = b.x + b.bend * along + Math.sin(now * .0013 + b.phase) * 2;
        if (Math.abs(x - nearX) > 18 || y < tipY - 15 || y > b.bottom + 5) continue;
        b.velocity += Math.max(-16, Math.min(16, dx * .55 + (x - nearX) * .095)) * (1 + Math.min(1, Math.abs(dy) / 35));
        if (now - b.lastTouch < 240) continue;
        b.lastTouch = now;
        contacts++;
        if (!reducedMotion && particles.length < 38 && r() > .54) {
          particles.push({ x: nearX, y, vx: (r() - .5) * 3, vy: -r() * 3 - 1,
            life: .8 + r() * .6, size: r() * 2 + 1.2 });
        }
      }
      if (contacts) {
        combo = now - comboAt > 1500 ? contacts : combo + contacts;
        comboAt = now;
        strokeRef.current(contacts, combo);
      }
    };
    const down = (e: PointerEvent) => {
      if (!activeRef.current) return;
      if (activePointer !== null) return;
      activePointer = e.pointerId;
      canvas.setPointerCapture(e.pointerId);
      brush(e, true);
    };
    const move = (e: PointerEvent) => {
      if (activePointer === e.pointerId) brush(e, false);
    };
    const up = (event: PointerEvent) => { if (activePointer === event.pointerId) activePointer = null; };
    canvas.addEventListener('pointerdown', down);
    canvas.addEventListener('pointermove', move);
    canvas.addEventListener('pointerup', up);
    canvas.addEventListener('pointercancel', up);
    const wake = () => { if (!document.hidden) { last = 0; if (!raf) raf = requestAnimationFrame(draw); } };
    document.addEventListener('visibilitychange', wake);
    return () => {
      cancelAnimationFrame(raf);
      onResize.disconnect();
      canvas.removeEventListener('pointerdown', down);
      canvas.removeEventListener('pointermove', move);
      canvas.removeEventListener('pointerup', up);
      canvas.removeEventListener('pointercancel', up);
      document.removeEventListener('visibilitychange', wake);
    };
  }, []);

  return <canvas className={`grass-canvas ${active ? 'grass-active' : ''}`}
                 ref={ref} aria-label="Интерактивная лужайка — проведите пальцем по траве"
                 role="img" />;
}
