export interface Player {
  id: string;
  first_name: string;
  username: string | null;
  total_touches: number;
  xp: number;
  level: number;
  current_level_xp: number;
  next_level_xp: number;
  sessions_completed: number;
  achievements: string[];
}
export interface GameSession {
  id: string;
  started_at: string;
  awarded: number;
  last_seq: number;
  finished: boolean;
}
export interface Achievement {
  name: string;
  description: string;
  icon: string;
}
export interface Batch {
  batch_id: string;
  seq: number;
  touches: number;
  duration_ms: number;
  peak_combo: number;
}
export interface BatchResult {
  batch_id: string;
  seq: number;
  granted: number;
  requested: number;
  total_touches: number;
  xp: number;
  level: number;
  session_touches: number;
  joke: string;
  new_achievements: string[];
  duplicate: boolean;
}
export type GrassPhase = 'home' | 'playing' | 'complete';
