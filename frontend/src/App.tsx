import { useCallback, useEffect, useRef, useState } from 'react';
import GrassCanvas from './components/GrassCanvas';
import { api, configureAuth } from './lib/api';
import { playTouch } from './lib/audio';
import { FLUSH_INTERVAL_MS, formatInt, makeBatch, SESSION_SECONDS, timeLeft, xpRatio } from './lib/game';
import { impact, successHaptic, telegram } from './lib/telegram';
import type { Achievement, Batch, BatchResult, GameSession, GrassPhase, Player } from './types';

const OUTBOX_KEY = 'touch-grass-outbox-v1';
const SOUND_KEY = 'touch-grass-sound-v1';
const TITLES = ['Grass Intern', 'Junior Leaf Operator', 'Middle Lawn Engineer', 'Senior Grass Engineer', 'Principal Botanist'];
const FIRST_JOKE = 'Мне сказали трогать траву. Я написал для этого бота.';
interface MeResponse { player: Player; active_session: GameSession | null; achievement_catalog: Record<string, Achievement>; }
interface ConfigResponse { demo_mode: boolean; bot_username: string; share_url: string; }
interface StartResponse { player: Player; session: GameSession; joke: string; }
interface FinishResponse { player: Player; session: GameSession; joke: string; new_achievements: string[]; }
interface StoredBatch { sessionId: string; batch: Batch; }

function readOutbox(): StoredBatch | null {
  try {
    const raw = localStorage.getItem(OUTBOX_KEY);
    if (!raw) return null;
    const value: StoredBatch = JSON.parse(raw);
    if (typeof value.sessionId === 'string' && typeof value.batch?.batch_id === 'string' &&
        Number.isInteger(value.batch.seq) && Number.isInteger(value.batch.touches)) return value;
  } catch { /* storage may be disabled; game still plays */ }
  return null;
}
function saveOutbox(value: StoredBatch | null): void {
  try { if (value) localStorage.setItem(OUTBOX_KEY, JSON.stringify(value));
        else localStorage.removeItem(OUTBOX_KEY); } catch { /* best effort */ }
}
function progressPlayer(player: Player, batch: BatchResult): Player {
  const level = batch.level;
  return { ...player, total_touches: batch.total_touches, xp: batch.xp, level,
    current_level_xp: 50 * (level - 1) * level, next_level_xp: 50 * level * (level + 1),
    achievements: [...new Set([...player.achievements, ...batch.new_achievements])] };
}

export default function App() {
  const [player, setPlayer] = useState<Player | null>(null);
  const [catalog, setCatalog] = useState<Record<string, Achievement>>({});
  const [config, setConfig] = useState<ConfigResponse | null>(null);
  const [session, setSession] = useState<GameSession | null>(null);
  const [phase, setPhase] = useState<GrassPhase>('home');
  const [showAchievements, setShowAchievements] = useState(false);
  const [sound, setSound] = useState(() => { try { return localStorage.getItem(SOUND_KEY) !== 'off'; } catch { return true; } });
  const [light, setLight] = useState(() => telegram()?.colorScheme === 'light' ||
    (!telegram() && matchMedia('(prefers-color-scheme: light)').matches));
  const [toast, setToast] = useState(FIRST_JOKE);
  const [error, setError] = useState('');
  const [ready, setReady] = useState(false);
  const [busy, setBusy] = useState(false);
  const [now, setNow] = useState(Date.now());
  const [pendingVisual, setPendingVisual] = useState(0);
  const [recentlyUnlocked, setRecentlyUnlocked] = useState<string[]>([]);
  const sessionRef = useRef<GameSession | null>(null);
  const phaseRef = useRef<GrassPhase>('home');
  const queue = useRef(0);
  const pending = useRef<Batch | null>(null);
  const inflight = useRef<Promise<void> | null>(null);
  const peakCombo = useRef(0);
  const maxCombo = useRef(0);
  const lastFlush = useRef(performance.now());
  const lastSound = useRef(true);
  const finishInProgress = useRef(false);
  const [lastResult, setLastResult] = useState(0);
  useEffect(() => { sessionRef.current = session; }, [session]);
  useEffect(() => { phaseRef.current = phase; }, [phase]);
  useEffect(() => { lastSound.current = sound; try { localStorage.setItem(SOUND_KEY, sound ? 'on' : 'off'); } catch { /* private mode */ } }, [sound]);
  useEffect(() => {
    const webApp = telegram();
    webApp?.ready(); webApp?.expand();
    const updateTheme = () => setLight(webApp?.colorScheme === 'light');
    webApp?.onEvent('themeChanged', updateTheme);
    return () => webApp?.offEvent('themeChanged', updateTheme);
  }, []);

  const showError = useCallback((err: unknown) => {
    const message = err instanceof Error ? err.message : 'Ошибка связи с газоном.';
    setError(message);
  }, []);

  const flush = useCallback(async (): Promise<void> => {
    if (inflight.current) return inflight.current;
    const active = sessionRef.current;
    if (!active) return;
    if (!pending.current && queue.current < 1) return;
    if (!pending.current) {
      const count = Math.min(80, queue.current);
      queue.current -= count;
      setPendingVisual(queue.current);
      const created = makeBatch(active.last_seq + 1, count,
        performance.now() - lastFlush.current, peakCombo.current);
      peakCombo.current = 0;
      lastFlush.current = performance.now();
      pending.current = created;
      saveOutbox({ sessionId: active.id, batch: created });
    }
    const current = pending.current;
    if (!current) return;
    const promise = (async () => {
      const result = await api<BatchResult>(`/api/sessions/${active.id}/batches`, {
        method: 'POST', body: JSON.stringify(current), keepalive: true,
      });
      const previous = sessionRef.current;
      if (previous && previous.id === active.id) {
        const next = { ...previous, awarded: result.session_touches,
                       last_seq: Math.max(previous.last_seq, result.seq) };
        sessionRef.current = next;
        setSession(next);
      }
      setPlayer(p => p ? progressPlayer(p, result) : p);
      if (result.joke) setToast(result.joke);
      if (result.new_achievements.length) {
        setRecentlyUnlocked(result.new_achievements);
        successHaptic();
      }
      pending.current = null;
      saveOutbox(null);
      if (result.granted < result.requested) {
        setError('Часть касаний не засчиталась: лимит скорости. Гладь чуть спокойнее.');
      } else setError('');
    })();
    inflight.current = promise;
    try { await promise; }
    finally { inflight.current = null; }
  }, []);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const cfg = await api<ConfigResponse>('/api/config');
        if (cancelled) return;
        setConfig(cfg);
        configureAuth(cfg.demo_mode);
        const result = await api<MeResponse>('/api/me');
        if (cancelled) return;
        setPlayer(result.player); setCatalog(result.achievement_catalog);
        if (result.active_session) {
          sessionRef.current = result.active_session;
          setSession(result.active_session);
          setPhase('playing'); phaseRef.current = 'playing';
          const outbox = readOutbox();
          if (outbox?.sessionId === result.active_session.id &&
              outbox.batch.seq > result.active_session.last_seq) pending.current = outbox.batch;
          else saveOutbox(null);
          if (pending.current) void flush().catch(showError);
        } else saveOutbox(null);
      } catch (err) { if (!cancelled) showError(err); }
      finally { if (!cancelled) setReady(true); }
    })();
    return () => { cancelled = true; };
  }, [flush, showError]);

  const start = useCallback(async () => {
    if (busy) return;
    setBusy(true); setError(''); setRecentlyUnlocked([]);
    try {
      const data = await api<StartResponse>('/api/sessions', { method: 'POST' });
      sessionRef.current = data.session;
      setSession(data.session); setPlayer(data.player);
      setPhase('playing'); phaseRef.current = 'playing';
      queue.current = 0; peakCombo.current = 0; maxCombo.current = 0;
      setPendingVisual(0); setToast(data.joke || FIRST_JOKE);
      lastFlush.current = performance.now();
    } catch (err) { showError(err); }
    finally { setBusy(false); }
  }, [busy, showError]);

  const finish = useCallback(async () => {
    if (finishInProgress.current || !sessionRef.current) return;
    finishInProgress.current = true; setBusy(true);
    try {
      // Never finish before persisting pending observations. Retry safe: UUID receipts.
      for (let i = 0; i < 12 && (pending.current || queue.current); i++) await flush();
      if (pending.current || queue.current) {
        setError('Есть несохраненные касания. Проверь соединение и повтори.');
        return;
      }
      const active = sessionRef.current;
      if (!active) return;
      const result = await api<FinishResponse>(`/api/sessions/${active.id}/finish`, { method: 'POST' });
      setLastResult(result.session.awarded); setPlayer(result.player);
      sessionRef.current = result.session; setSession(result.session);
      setPhase('complete'); phaseRef.current = 'complete';
      setToast(result.joke);
      if (result.new_achievements.length) {
        setRecentlyUnlocked(result.new_achievements); successHaptic();
      }
      saveOutbox(null); setError('');
    } catch (err) { showError(err); }
    finally { finishInProgress.current = false; setBusy(false); }
  }, [flush, showError]);

  useEffect(() => {
    if (phase !== 'playing') return;
    const interval = window.setInterval(() => {
      setNow(Date.now());
      if (sessionRef.current && timeLeft(sessionRef.current.started_at) <= 0) void finish();
    }, 1000);
    const batchInterval = window.setInterval(() => void flush().catch(showError), FLUSH_INTERVAL_MS);
    const visibility = () => { if (document.hidden) void flush().catch(showError); };
    document.addEventListener('visibilitychange', visibility);
    return () => {
      clearInterval(interval); clearInterval(batchInterval);
      document.removeEventListener('visibilitychange', visibility);
    };
  }, [phase, finish, flush, showError]);

  const onStroke = useCallback((count: number, combo: number) => {
    if (phaseRef.current !== 'playing' || finishInProgress.current) return;
    queue.current += count;
    setPendingVisual(queue.current);
    peakCombo.current = Math.max(peakCombo.current, combo);
    maxCombo.current = Math.max(maxCombo.current, combo);
    if (lastSound.current) playTouch();
    impact();
    if (maxCombo.current === count && count > 0) setToast('Первая травинка в шоке. Продолжай.');
  }, []);

  const share = useCallback(() => {
    const link = config?.share_url || window.location.origin;
    const count = player?.total_touches || 0;
    const text = `🌱 Я потрогал траву ${formatInt(count)} раз. Настоящую — 0.\nTOUCH GRASS.exe · by DizZy\nБрат, это надо видеть.`;
    const url = `https://t.me/share/url?url=${encodeURIComponent(link)}&text=${encodeURIComponent(text)}`;
    if (telegram()) telegram()?.openTelegramLink(url);
    else window.open(url, '_blank', 'noopener,noreferrer');
  }, [config, player]);

  const seconds = session && phase === 'playing' ? timeLeft(session.started_at, now) : SESSION_SECONDS;
  const shownTouches = (session?.awarded || 0) + pendingVisual + (pending.current?.touches || 0);
  const appClass = `app ${light ? 'light' : 'dark'}`;
  return (
    <main className={appClass}>
      <div className="page-shell">
        <header className="topbar">
          <div className="brand"><span className="brand-icon">🌱</span><div>
            <strong>TOUCH GRASS<span className="extension">.exe</span></strong>
            <small>est. 2026 · handmade by <b>DizZy</b></small>
          </div></div>
          <div className="header-actions">
            {config?.demo_mode && <span className="tiny-pill demo">DEMO</span>}
            <button type="button" className="icon-button" aria-label={sound ? 'Выключить звуки' : 'Включить звуки'}
              title={sound ? 'Выключить звуки' : 'Включить звуки'} onClick={() => setSound(s => !s)}>
              {sound ? '♫' : '♪̸'}
            </button>
            <button type="button" className="icon-button" aria-label="Коллекция достижений" title="Коллекция достижений"
              onClick={() => setShowAchievements(v => !v)}>🏆</button>
          </div>
        </header>
        <section className="hero-text" aria-label="Название игры">
          <div className="eyebrow"><span className="online-dot" /> ВЫСОКОТЕХНОЛОГИЧНАЯ ПРОГУЛКА v0.1</div>
          <h1>Социализация?<br/><span>Нет, спасибо.</span></h1>
          <p>Мне сказали трогать траву. Я написал для этого бота.</p>
        </section>
        <section className="profile-strip" aria-label="Ваш прогресс">
          <div className="profile-avatar">{player?.first_name?.[0]?.toUpperCase() || 'D'}</div>
          <div className="profile-data">
            <div className="profile-identity"><strong>{player?.first_name || 'Подключение...'}</strong>
              <span>LVL {player?.level || 1} · {TITLES[Math.min(Math.max(0, (player?.level || 1) - 1), TITLES.length - 1)]}</span></div>
            <div className="xp-track"><div style={{ width: `${player ? xpRatio(player) * 100 : 0}%` }} /></div>
            <small>{player ? `${formatInt(player.xp - player.current_level_xp)} / ${formatInt(player.next_level_xp - player.current_level_xp)} XP` : 'Загружаем прогресс...'}</small>
          </div>
          <div className="profile-total"><strong>{formatInt(player?.total_touches || 0)}</strong><span>всего касаний</span></div>
        </section>
        <section className="game-card" aria-label="Игровая лужайка">
          <div className="game-topline"><span className="location-pill">◉ 01 / ПОДОКОННИК РАЗРАБОТЧИКА</span>
            <span className="session-status"><span className="status-dot" />{phase === 'playing' ? 'LIVE' : 'ONLINE'}</span></div>
          <div className="grass-viewport">
            <GrassCanvas active={phase === 'playing'} light={light} onStroke={onStroke} />
            {phase === 'playing' ? (
              <div className="canvas-upper"><div className="floating-count"><small>ПОГЛАЖЕНО ЗА СЕССИЮ</small>
                <strong>{formatInt(shownTouches)}</strong><span>🌿 продолжай в том же духе</span></div>
                <div className="timer">{`${Math.floor(seconds / 60).toString().padStart(2, '0')}:${(seconds % 60).toString().padStart(2, '0')}`}</div>
              </div>
            ) : phase === 'complete' ? (
              <div className="canvas-complete"><div className="completion-medal">🏅</div>
                <b>ВЫ СОЦИАЛИЗИРОВАЛИСЬ</b><strong>+{formatInt(lastResult)}</strong>
                <span>касания без выхода на улицу</span></div>
            ) : (
              <div className="canvas-welcome"><span className="floating-sun">☀</span>
                <div className="terminal-box"><span className="terminal-dots"><i/><i/><i/></span>
                  <span className="terminal-line">$ sudo touch /grass</span>
                  <span className="terminal-success">✓ permission granted</span></div>
              </div>
            )}
            <div className="canvas-bottom">{phase === 'playing' ? '↝ ПРОВОДИ ПАЛЬЦЕМ ПО ТРАВЕ ↜' : '100% ОРГАНИКА · 0% УЛИЦЫ'}</div>
          </div>
          <div className="game-control">
            {phase === 'home' ? (
              <button className="main-button" type="button" disabled={!ready || !player || busy} onClick={start}>
                <span className="button-spark">✳</span>{busy ? 'ЗАПУСКАЕМ ГАЗОН...' : 'НАЧАТЬ СОЦИАЛИЗАЦИЮ'}<span>↗</span>
              </button>
            ) : phase === 'playing' ? (
              <div className="playing-controls"><span className="touch-hint">👆 Гладь траву. Не нажимай на нее как на кнопку.</span>
                <button type="button" disabled={busy} className="finish-button" onClick={() => void finish()}>{busy ? 'Сохраняем...' : 'Завершить ✓'}</button></div>
            ) : (
              <div className="playing-controls"><button className="main-button" type="button" onClick={() => {
                setPhase('home'); phaseRef.current = 'home'; setSession(null); sessionRef.current = null;
                setRecentlyUnlocked([]); setPendingVisual(0); }}>ЕЩЕ РАЗ ↗</button>
                <button className="finish-button" type="button" onClick={share}>Поделиться ↗</button></div>
            )}
            <div className="caption-muted">Симулятор социализации для тех, у кого открыт VS Code.</div>
          </div>
        </section>
        <section className="quips" aria-live="polite" aria-atomic="true">
          <div className="quips-avatar">✦</div><div><small>СОВЕТ ОТ МАТУШКИ ПРИРОДЫ</small><p>{toast}</p></div>
        </section>
        {recentlyUnlocked.length > 0 && <section className="unlocks" aria-live="polite">
          <span>🏆 НОВОЕ ДОСТИЖЕНИЕ!</span>
          {recentlyUnlocked.map(code => <b key={code}>{catalog[code]?.icon} {catalog[code]?.name || code}</b>)}
          <button type="button" onClick={() => setRecentlyUnlocked([])} aria-label="Скрыть достижения">×</button>
        </section>}
        {error && <div className="error-box" role="alert">⚠ {error}{error.includes('сохраненн') &&
          <button type="button" onClick={() => void flush().catch(showError)}>Повторить</button>}</div>}
        <section className="bottom-grid"><div className="info-box"><span>🌱</span><b>1 / 7</b><small>открыто локаций</small></div>
          <button type="button" className="info-box clickable" onClick={() => setShowAchievements(true)}><span>🏆</span>
            <b>{player?.achievements.length || 0} / {Object.keys(catalog).length || 5}</b><small>достижений</small></button>
          <button type="button" className="info-box clickable" onClick={share}><span>↗</span><b>SHARE</b><small>отправить другу</small></button></section>
        <footer className="footer"><span>designed, grown & debugged by <b>DizZy</b></span><span>no grass was harmed™</span></footer>
      </div>
      {showAchievements && <div className="modal-backdrop" onClick={() => setShowAchievements(false)}>
        <section className="achievement-modal" role="dialog" aria-modal="true" aria-label="Достижения" onClick={e => e.stopPropagation()}>
          <div className="modal-head"><div><small>GRASS.OS / YOUR TROPHIES</small><h2>Музей прикосновений 🏆</h2></div>
            <button type="button" className="icon-button" onClick={() => setShowAchievements(false)} aria-label="Закрыть">×</button></div>
          <p>Эти достижения нельзя поставить на полку. Зато можно показать другу.</p>
          <div className="achievement-list">{Object.entries(catalog).map(([code, item]) => {
            const have = !!player?.achievements.includes(code);
            return <div className={`achievement-row ${have ? 'unlocked' : 'locked'}`} key={code}>
              <span className="achievement-emoji">{have ? item.icon : '🔒'}</span>
              <div><b>{item.name}</b><small>{have ? item.description : 'Секрет пока не раскрыт'}</small></div>
              {have && <strong>✓</strong>}
            </div>;
          })}</div>
          <button className="main-button" type="button" onClick={share}>ПОХВАСТАТЬСЯ ↗</button>
        </section>
      </div>}
    </main>
  );
}
