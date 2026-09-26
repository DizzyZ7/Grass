/** Tiny procedural sound, zero external assets and no autoplay. */
let audio: AudioContext | null = null;
let lastPlay = 0;
export function playTouch(): void {
  const now = performance.now();
  if (now - lastPlay < 200) return;
  lastPlay = now;
  try {
    audio ??= new AudioContext();
    if (audio.state === 'suspended') void audio.resume();
    const osc = audio.createOscillator();
    const gain = audio.createGain();
    osc.type = 'sine';
    osc.frequency.setValueAtTime(470, audio.currentTime);
    osc.frequency.exponentialRampToValueAtTime(180, audio.currentTime + 0.085);
    gain.gain.setValueAtTime(0.0001, audio.currentTime);
    gain.gain.exponentialRampToValueAtTime(0.038, audio.currentTime + 0.01);
    gain.gain.exponentialRampToValueAtTime(0.0001, audio.currentTime + 0.10);
    osc.connect(gain).connect(audio.destination);
    osc.start();
    osc.stop(audio.currentTime + 0.11);
    osc.onended = () => { osc.disconnect(); gain.disconnect(); };
  } catch { /* sound is optional and never blocks the game */ }
}
