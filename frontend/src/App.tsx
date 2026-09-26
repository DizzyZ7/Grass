import { useCallback, useEffect, useRef, useState } from 'react';
import type { MouseEvent } from 'react';
import GrassCanvas from './components/GrassCanvas';
import ShareCard from './components/ShareCard';
import { api, configureAuth } from './lib/api';
import { playTouch } from './lib/audio';
import { isReportStale, progressPercent } from './lib/field';
import { FLUSH_INTERVAL_MS, formatInt, makeBatch, SESSION_SECONDS, timeLeft, xpRatio } from './lib/game';
import { impact, successHaptic, telegram } from './lib/telegram';
import type { Achievement, Batch, BatchResult, DailyResponse, FieldReport, GameSession, GrassPhase, LeaderboardResponse, Player, PublicProfile, WeeklyResponse, WorldResponse } from './types';

const OUTBOX_KEY = 'touch-grass-outbox-v1';
const SOUND_KEY = 'touch-grass-sound-v1';
const TITLES = ['Grass Intern', 'Junior Leaf Operator', 'Middle Lawn Engineer', 'Senior Grass Engineer', 'Principal Botanist'];
const FIRST_JOKE = 'Мне сказали трогать траву. Я написал для этого бота.';
interface MeResponse { player: Player; active_session: GameSession | null; achievement_catalog: Record<string, Achievement>; }
interface ConfigResponse { demo_mode: boolean; bot_username: string; share_url: string; }
interface StartResponse { player: Player; session: GameSession; joke: string; }
interface DiscoveredPlant {code: string; name: string; description: string; rarity: string; color: string; duplicate: boolean;}
interface FinishResponse { player: Player; session: GameSession; joke: string; new_achievements: string[]; new_plant: DiscoveredPlant | null; }
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
  const [world, setWorld] = useState<WorldResponse | null>(null);
  const [daily, setDaily] = useState<DailyResponse | null>(null);
  const [weekly, setWeekly] = useState<WeeklyResponse | null>(null);
  const [field, setField] = useState<FieldReport | null>(null);
  const [leaders, setLeaders] = useState<LeaderboardResponse | null>(null);
  const [period, setPeriod] = useState<'day' | 'week'>('day');
  const [panel, setPanel] = useState<'locations' | 'collection' | 'daily' | 'weekly' | 'leaderboard' | 'social' | 'field' | null>(null);
  const [discovery, setDiscovery] = useState<DiscoveredPlant | null>(null);
  const [config, setConfig] = useState<ConfigResponse | null>(null);
  const [session, setSession] = useState<GameSession | null>(null);
  const [phase, setPhase] = useState<GrassPhase>('home');
  const [showAchievements, setShowAchievements] = useState(false);
  const [showShare, setShowShare] = useState(false);
  const [viewedProfile, setViewedProfile] = useState<PublicProfile | null>(null);
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

  const refreshExtras = useCallback(async (rankPeriod: 'day' | 'week' = 'day') => {
    const results = await Promise.allSettled([
      api<WorldResponse>('/api/world'), api<DailyResponse>('/api/daily'),
      api<LeaderboardResponse>(`/api/leaderboard?period=${rankPeriod}`),
      api<WeeklyResponse>('/api/weekly'),
      api<FieldReport>('/api/field-report'),
    ]);
    if (results[0].status === 'fulfilled') setWorld(results[0].value);
    if (results[1].status === 'fulfilled') setDaily(results[1].value);
    if (results[2].status === 'fulfilled') setLeaders(results[2].value);
    if (results[3].status === 'fulfilled') setWeekly(results[3].value);
    if (results[4].status === 'fulfilled') setField(results[4].value);
  }, []);

  useEffect(() => {
    // Keep the forecast and daily mission current if Telegram stays open past UTC midnight.
    if (!field) return;
    const checkDay = () => {
      if (isReportStale(field.date)) void refreshExtras(period);
    };
    const checkInterval = window.setInterval(checkDay, 60_000);
    return () => window.clearInterval(checkInterval);
  }, [field, period, refreshExtras]);

  const openPanel = useCallback((name: 'locations' | 'collection' | 'daily' | 'weekly' | 'leaderboard' | 'social' | 'field') => {
    setPanel(previous => previous === name ? null : name);
    if (name === 'leaderboard') void api<LeaderboardResponse>(`/api/leaderboard?period=${period}`)
      .then(setLeaders).catch(showError);
  }, [period, showError]);

  const chooseWorld = useCallback(async (kind: 'location' | 'grass', code: string) => {
    if (phaseRef.current === 'playing') return;
    setBusy(true); setError('');
    try {
      const result = await api<{player: Player}>(`/api/world/${kind}`, {
        method: 'POST', body: JSON.stringify({code}),
      });
      setPlayer(result.player);
      await refreshExtras(period);
      setToast(kind === 'location' ? 'Новая лужайка подключена. Пинг до природы: 0 мс.' :
        'Трава обновлена. На настоящей улице изменений не обнаружено.');
    } catch (err) { showError(err); }
    finally { setBusy(false); }
  }, [period, refreshExtras, showError]);

  const claimQuest = useCallback(async (code: string) => {
    setBusy(true);
    try {
      const result = await api<{player: Player; daily: DailyResponse; xp_granted: number}>(
        `/api/daily/claim/${code}`, {method: 'POST'});
      setPlayer(result.player); setDaily(result.daily);
      setToast(`Награда: +${result.xp_granted} XP. Мама считает, что ты погулял.`);
      successHaptic(); setError('');
      await refreshExtras(period);
    } catch (err) { showError(err); }
    finally { setBusy(false); }
  }, [period, refreshExtras, showError]);

  const claimWeekly = useCallback(async (code: string) => {
    setBusy(true);
    try {
      const result = await api<{player: Player; weekly: WeeklyResponse; xp_granted: number}>(
        `/api/weekly/claim/${code}`, { method: 'POST' });
      setPlayer(result.player); setWeekly(result.weekly);
      setToast(result.xp_granted ? `+${result.xp_granted} XP. Природа официально признала твой отпуск.` : 'Награда уже получена.');
      successHaptic(); setError('');
    } catch (err) { showError(err); }
    finally { setBusy(false); }
  }, [showError]);

  const claimField = useCallback(async () => {
    if (busy) return;
    setBusy(true);
    try {
      const result = await api<{player: Player; report: FieldReport; xp_granted: number;
        new_achievements: string[]}>('/api/field-report/claim', {method: 'POST'});
      setField(result.report); setPlayer(result.player);
      setToast(result.xp_granted ? `+${result.xp_granted} XP. Экспедиция прошла без физического присутствия.` :
        'Отчет уже подписан. Бюрократия отдыхает.');
      if (result.new_achievements.length) {
        setRecentlyUnlocked(result.new_achievements);
        void api<MeResponse>('/api/me').then(data => setCatalog(data.achievement_catalog)).catch(() => {});
      }
      successHaptic(); setError('');
    } catch (err) { showError(err); }
    finally { setBusy(false); }
  }, [busy, showError]);

  const togglePrivacy = useCallback(async () => {
    if (!player) return;
    setBusy(true);
    try {
      const result = await api<{player: Player}>('/api/profile/privacy', {
        method: 'POST', body: JSON.stringify({show_public_profile: !player.show_public_profile}),
      });
      setPlayer(result.player); setError('');
      void refreshExtras(period);
    } catch (err) { showError(err); }
    finally { setBusy(false); }
  }, [player, showError, refreshExtras, period]);

  const openProfile = useCallback(async (id: string) => {
    try { setViewedProfile(await api<PublicProfile>(`/api/players/${encodeURIComponent(id)}`)); setError(''); }
    catch (err) { showError(err); }
  }, [showError]);

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
        void api<MeResponse>('/api/me').then(value => setCatalog(value.achievement_catalog)).catch(() => {});
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
        void refreshExtras();
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
  }, [flush, showError, refreshExtras]);

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
      if (result.new_plant) {
        setDiscovery(result.new_plant); successHaptic();
      }
      void refreshExtras(period);
      if (result.new_achievements.length) {
        setRecentlyUnlocked(result.new_achievements); successHaptic();
        void api<MeResponse>('/api/me').then(value => setCatalog(value.achievement_catalog)).catch(() => {});
      }
      saveOutbox(null); setError('');
    } catch (err) { showError(err); }
    finally { finishInProgress.current = false; setBusy(false); }
  }, [flush, showError, refreshExtras, period]);

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

  const shareText = useCallback(() => {
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
  const place = world?.locations.find(p => p.code === world.selected_location);
  const plant = world?.species.find(p => p.code === world.selected_grass);
  const inviteLink = config?.bot_username && player
    ? `https://t.me/${config.bot_username}?startapp=ref_${player.id}` : '';
  const copyInvite = () => {
    if (!inviteLink) return;
    if (!navigator.clipboard) { setToast(inviteLink); return; }
    void navigator.clipboard.writeText(inviteLink)
      .then(() => setToast('Ссылка скопирована. Газон перестал быть одиноким.'))
      .catch(() => setToast(inviteLink));
  };
  const invite = () => {
    const link = inviteLink || (config?.share_url || window.location.origin);
    const text = 'Мне сказали трогать траву. Я написал для этого бота. Присоединяйся к нашему заочному пикнику 🌱';
    const url = `https://t.me/share/url?url=${encodeURIComponent(link)}&text=${encodeURIComponent(text)}`;
    if (telegram()) telegram()?.openTelegramLink(url);
    else window.open(url, '_blank', 'noopener,noreferrer');
  };
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
          <div className="eyebrow"><span className="online-dot" /> ВЫСОКОТЕХНОЛОГИЧНАЯ ПРОГУЛКА v0.4</div>
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
          <div className="game-topline"><button type="button" className="location-pill" disabled={phase === 'playing'} onClick={() => openPanel('locations')}>◉ {place?.name?.toUpperCase() || 'ПОДОКОННИК РАЗРАБОТЧИКА'} ▾</button>
            <span className="session-status"><span className="status-dot" />{phase === 'playing' ? 'LIVE' : 'ONLINE'}</span></div>
          {field && <div className="weather-bar" role="status" aria-label={`Прогноз погоды: ${field.weather.name}`}>
            <span>{field.weather.icon} {field.weather.name}</span>
            <button type="button" onClick={() => openPanel('field')}>ПОЛЕВОЙ ЖУРНАЛ ↗</button>
          </div>}
          <div className="grass-viewport">
            <GrassCanvas active={phase === 'playing'} light={light} onStroke={onStroke}
              speciesColor={plant?.color} skyColor={place?.sky} groundColor={place?.ground} motion={plant?.motion} weather={field?.weather.effect} />
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
                <button className="finish-button" type="button" onClick={() => setShowShare(true)}>Карточка PNG ↗</button></div>
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
        <nav className="garden-nav" aria-label="Другие разделы">
          <button className={panel === 'locations' ? 'selected' : ''} onClick={() => openPanel('locations')}>🗺️ Локации</button>
          <button className={panel === 'collection' ? 'selected' : ''} onClick={() => openPanel('collection')}>🌿 Гербарий</button>
          <button className={panel === 'field' ? 'selected' : ''} onClick={() => openPanel('field')}>🌦️ Экспедиция</button>
          <button className={panel === 'daily' ? 'selected' : ''} onClick={() => openPanel('daily')}>🎯 Задания</button>
          <button className={panel === 'weekly' ? 'selected' : ''} onClick={() => openPanel('weekly')}>📆 Неделя</button>
          <button className={panel === 'leaderboard' ? 'selected' : ''} onClick={() => openPanel('leaderboard')}>🏆 Топ</button>
          <button className={panel === 'social' ? 'selected' : ''} onClick={() => openPanel('social')}>🫂 Друзья</button>
        </nav>
        {panel && <section className="garden-panel" aria-label="Игровые разделы">
          <div className="panel-heading"><div><small>GRASS.OS / {panel.toUpperCase()}</small><h2>{
            panel === 'locations' ? 'Куда сегодня не выходим?' : panel === 'collection' ? 'Музей травы' :
            panel === 'daily' ? 'Планы на социализацию' : panel === 'field' ? 'Полевой журнал 2.0' :
            panel === 'weekly' ? 'Заочная экспедиция' : panel === 'social' ? 'Люди из интернета' : 'Лига ботаников'}</h2></div>
            <button type="button" className="icon-button" onClick={() => setPanel(null)} aria-label="Закрыть">×</button></div>
          {panel === 'locations' && <div className="world-list">{world?.locations.map(location =>
            <button type="button" key={location.code} className={`world-tile ${world.selected_location === location.code ? 'chosen' : ''}`}
              disabled={busy || !location.unlocked || phase === 'playing'} onClick={() => void chooseWorld('location', location.code)}>
              <span className="world-icon" style={{background: location.ground}}> {location.secret ? '✨' : location.unlocked ? '🌳' : '🔒'}</span>
              <span><b>{location.name}</b><small>{location.description}</small></span>
              <em>{world.selected_location === location.code ? 'ЗДЕСЬ' : location.unlocked ? 'ВЫБРАТЬ' : `LVL ${location.level}`}</em>
            </button>)}{!world && <p>Загрузка маршрута…</p>}</div>}
          {panel === 'collection' && <><p className="panel-note">Три находки в день за сессии от 30 засчитанных касаний. Повторы увеличивают количество, а не XP.</p>
            <div className="species-list">{world?.species.map(species =>
              <button type="button" key={species.code} className={`species-tile ${world.selected_grass === species.code ? 'chosen' : ''} rarity-${species.rarity}`}
                disabled={busy || !species.unlocked || phase === 'playing'} onClick={() => void chooseWorld('grass', species.code)}>
                <span className="species-icon" style={{color: species.unlocked ? species.color : '#778379'}}>♣</span>
                <span><b>{species.unlocked ? species.name : 'Неизвестный экземпляр'}</b><small>{species.unlocked ? species.description : 'Найди в одной из будущих сессий'}</small>
                <i>{world.rarities[species.rarity]} {species.copies ? `· ×${species.copies}` : ''}</i></span>
                <em>{world.selected_grass === species.code ? 'АКТИВНА' : species.unlocked ? 'ВЫБРАТЬ' : '🔒'}</em>
              </button>)}</div></>}
          {panel === 'field' && <div className="field-report">
            {field ? <>
              <div className={`field-weather weather-${field.weather.code}`}>
                <span className="weather-icon" aria-hidden="true">{field.weather.icon}</span>
                <div><small>ПРОГНОЗ · {place?.name?.toUpperCase() || 'ТВОЙ ГАЗОН'}</small>
                  <h3>{field.weather.name}</h3><p>{field.weather.description}</p></div>
              </div>
              <p className="panel-note">Каждый день своя погода и одна персональная экспедиция.
                Задание фиксируется при первом открытии и не меняется при смене лужайки. Сброс в 00:00 UTC.</p>
              <div className="field-mission">
                <div className="field-mission-heading"><span aria-hidden="true">{field.mission.icon}</span>
                  <div><small>ОПЕРАЦИЯ ДНЯ / {field.date}</small><h3>{field.mission.name}</h3></div></div>
                <p>{field.mission.description}</p>
                {field.mission.location_name && <div className="mission-location">📍 Цель: {field.mission.location_name}</div>}
                <div className="quest-progress"><div style={{width: `${progressPercent(field.mission.progress, field.mission.target)}%`}} /></div>
                <div className="field-mission-bottom"><span>{field.mission.progress} / {field.mission.target} · +{field.mission.xp} XP</span>
                  <button type="button" disabled={busy || !field.mission.completed || field.mission.claimed}
                    onClick={() => void claimField()}>{field.mission.claimed ? '✓ ВЫПОЛНЕНО' :
                      field.mission.completed ? 'ЗАБРАТЬ НАГРАДУ' : 'В ПРОЦЕССЕ'}</button></div>
              </div>
              <div className="field-tracker">🔬 Экспедиций завершено: <b>{field.missions_completed}</b>
                <span>· новые значки за 3 и 14 исследований</span></div>
            </> : <p className="panel-note">Связь с природой устанавливается…</p>}
          </div>}
          {panel === 'daily' && <><p className="panel-note">🔥 Серия: {daily?.streak || 0} дн. · рекорд: {daily?.best_streak || 0} дн. Один пропуск не сжигает серию. Сброс в 00:00 UTC.</p>
            <div className="quest-list">{daily?.quests.map(quest =>
              <div className="quest-tile" key={quest.code}><span className="quest-icon">{quest.icon}</span>
                <div className="quest-content"><b>{quest.name}</b><small>{quest.description}</small>
                  <div className="quest-progress"><div style={{width:`${Math.min(100, quest.progress / quest.target * 100)}%`}} /></div>
                  <small>{quest.progress} / {quest.target} · +{quest.xp} XP</small></div>
                <button type="button" disabled={busy || !quest.completed || quest.claimed} onClick={() => void claimQuest(quest.code)}>
                  {quest.claimed ? '✓' : quest.completed ? 'ЗАБРАТЬ' : '…'}</button></div>)}</div></>}
          {panel === 'weekly' && <><p className="panel-note">Недельные испытания без обязательных друзей и ежедневной повинности. Сброс по понедельникам в 00:00 UTC.</p>
            <div className="quest-list">{weekly?.quests.map(quest =>
              <div className="quest-tile" key={quest.code}><span className="quest-icon">{quest.icon}</span>
                <div className="quest-content"><b>{quest.name}</b><small>{quest.description}</small>
                  <div className="quest-progress"><div style={{width:`${Math.min(100, quest.progress / quest.target * 100)}%`}} /></div>
                  <small>{quest.progress} / {quest.target} · +{quest.xp} XP</small></div>
                <button type="button" disabled={busy || !quest.completed || quest.claimed} onClick={() => void claimWeekly(quest.code)}>
                  {quest.claimed ? '✓' : quest.completed ? 'ЗАБРАТЬ' : '…'}</button></div>)}</div></>}
          {panel === 'social' && <div className="social-card">
            <span className="social-plant" aria-hidden="true">🌱</span>
            <h3>Выходить на улицу вдвоем необязательно</h3>
            <p>Пригласи друга, если хочется. Никаких обязательных рефералов, платного доступа и накрутки рейтинга.</p>
            <div className="social-stat"><strong>{player?.invite_count || 0}</strong><span>принятых приглашений</span></div>
            <button className="main-button" type="button" onClick={invite}>ПОЗВАТЬ ДРУГА ↗</button>
            {inviteLink && <button className="copy-link" type="button" onClick={copyInvite}>Скопировать ссылку</button>}
            {!inviteLink && <p className="panel-note">Для персональных приглашений нужен публичный username бота и настроенная Main Mini App в BotFather.</p>}
            <div className="privacy-row"><div><b>Публичный профиль</b><small>Показывать имя и результат другим игрокам в рейтингах.</small></div>
              <button type="button" disabled={busy || !player} onClick={() => void togglePrivacy()}
                aria-pressed={player?.show_public_profile ?? true} className={`privacy-switch ${player?.show_public_profile ? 'enabled' : ''}`}>
                {player?.show_public_profile ? 'ВКЛ' : 'ВЫКЛ'}</button></div>
          </div>}
          {panel === 'leaderboard' && <><div className="leader-switch">
            {(['day','week'] as const).map(value => <button type="button" key={value} className={period === value ? 'chosen' : ''}
              onClick={() => {setPeriod(value); void api<LeaderboardResponse>(`/api/leaderboard?period=${value}`).then(setLeaders).catch(showError);}}>
              {value === 'day' ? 'Сегодня' : 'Эта неделя'}</button>)}</div>
            <p className="panel-note">Засчитываются только подтвержденные сервером касания. Отсчет по UTC. Можно скрыть свой профиль в разделе «Друзья».</p>
            <div className="leader-list">{leaders?.leaders.length ? leaders.leaders.map(entry =>
              <button type="button" className="leader-row leader-button" key={entry.id} onClick={() => void openProfile(entry.id)}
                aria-label={`Профиль игрока ${entry.first_name}`}><b>#{entry.rank}</b><span>{entry.first_name} {entry.id === player?.id ? ' · ТЫ' : ''}</span>
                <strong>{formatInt(entry.touches)} 🌱</strong></button>) : <p>Пока пусто. У тебя есть шанс засветиться первым.</p>}</div></>}
        </section>}
        <section className="bottom-grid"><button type="button" className="info-box clickable" onClick={() => openPanel('locations')}><span>🌱</span><b>{world?.locations.filter(p => p.unlocked).length || 1} / {world?.locations.length || 7}</b><small>открыто локаций</small></button>
          <button type="button" className="info-box clickable" onClick={() => setShowAchievements(true)}><span>🏆</span>
            <b>{player?.achievements.length || 0} / {Object.keys(catalog).length || 5}</b><small>достижений</small></button>
          <button type="button" className="info-box clickable" onClick={() => setShowShare(true)}><span>↗</span><b>PNG</b><small>отправить другу</small></button></section>
        <footer className="footer"><span>designed, grown & debugged by <b>DizZy</b></span><span>no grass was harmed™</span></footer>
      </div>
      {showShare && player && <ShareCard player={player} location={place?.name || 'Подоконник разработчика'}
        color={plant?.color} onClose={() => setShowShare(false)} shareText={shareText}/>}
      {viewedProfile && <div className="modal-backdrop" onClick={() => setViewedProfile(null)}>
        <section className="achievement-modal profile-modal" role="dialog" aria-modal="true" aria-label="Публичный профиль"
          onClick={(e: MouseEvent<HTMLDivElement>) => e.stopPropagation()}>
          <div className="modal-head"><div><small>GRASS.OS / PERSONNEL</small><h2>{viewedProfile.first_name}</h2></div>
            <button type="button" className="icon-button" onClick={() => setViewedProfile(null)} aria-label="Закрыть">×</button></div>
          <p>Уровень {viewedProfile.level} · {formatInt(viewedProfile.total_touches)} касаний</p>
          <div className="profile-facts"><span>🏅 {viewedProfile.achievements.length} достижений</span>
            <span>🌿 {viewedProfile.sessions_completed} сессий</span>
            <span>🔥 {viewedProfile.best_streak} дней подряд</span>
            <span>🫂 {viewedProfile.invite_count} друзей</span></div>
          <div className="profile-badges">{viewedProfile.achievements.map(code =>
            <span key={code} title={viewedProfile.achievement_catalog[code]?.description}>{viewedProfile.achievement_catalog[code]?.icon || '🌱'} {viewedProfile.achievement_catalog[code]?.name || 'Секрет'}</span>)}</div>
        </section>
      </div>}
      {discovery && <div className="modal-backdrop" onClick={() => setDiscovery(null)}>
        <section className="achievement-modal discovery-modal" role="dialog" aria-modal="true" aria-label="Найдена трава"
          onClick={(e: MouseEvent<HTMLDivElement>) => e.stopPropagation()}>
          <small>ОБНАРУЖЕНО · {discovery.rarity.toUpperCase()}</small>
          <div className="discovery-leaf" style={{color: discovery.color}}>❧</div>
          <h2>{discovery.name}</h2><p>{discovery.description}</p>
          <p>{discovery.duplicate ? 'У тебя уже есть такая! Еще один экземпляр в гербарий.' : 'Новый вид в коллекции. Мама будет гордиться.'}</p>
          <button type="button" className="main-button" onClick={() => {setDiscovery(null); setPanel('collection');}}>В ГЕРБАРИЙ ↗</button>
        </section>
      </div>}
      {showAchievements && <div className="modal-backdrop" onClick={() => setShowAchievements(false)}>
        <section className="achievement-modal" role="dialog" aria-modal="true" aria-label="Достижения" onClick={(e: MouseEvent<HTMLDivElement>) => e.stopPropagation()}>
          <div className="modal-head"><div><small>GRASS.OS / YOUR TROPHIES</small><h2>Музей прикосновений 🏆</h2></div>
            <button type="button" className="icon-button" onClick={() => setShowAchievements(false)} aria-label="Закрыть">×</button></div>
          <p>Эти достижения нельзя поставить на полку. Зато можно показать другу.</p>
          <div className="achievement-list">{Object.entries(catalog).map(([code, item]) => {
            const have = !!player?.achievements.includes(code);
            return <div className={`achievement-row ${have ? 'unlocked' : 'locked'}`} key={code}>
              <span className="achievement-emoji">{have ? item.icon : '🔒'}</span>
              <div><b>{item.secret && !have ? '???' : item.name}</b><small>{have ? item.description : item.secret ? 'Найди самостоятельно' : item.description}</small></div>
              {have && <strong>✓</strong>}
            </div>;
          })}</div>
          <button className="main-button" type="button" onClick={() => {setShowAchievements(false); setShowShare(true);}}>ПОХВАСТАТЬСЯ ↗</button>
        </section>
      </div>}
    </main>
  );
}
