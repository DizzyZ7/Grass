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
  selected_location: string;
  selected_grass: string;
  streak: number;
  best_streak: number;
  show_public_profile: boolean;
  invite_count: number;
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
  secret?: boolean;
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

export interface Location {
  code: string; name: string; description: string; level: number;
  sky: string; ground: string; secret: boolean; unlocked: boolean;
}
export interface GrassSpecies {
  code: string; name: string; description: string; rarity: string;
  color: string; motion: string; copies: number; unlocked: boolean;
}
export interface WorldResponse {
  locations: Location[]; selected_location: string; selected_grass: string;
  rarities: Record<string, string>; species: GrassSpecies[];
}
export interface Quest {
  code: string; name: string; description: string; target: number;
  progress: number; xp: number; icon: string; completed: boolean; claimed: boolean;
}
export interface DailyResponse {
  date: string; resets_at: string; streak: number; best_streak: number;
  quests: Quest[];
}
export interface LeaderboardResponse {
  period: 'day' | 'week'; starts_at: string; ends_at: string;
  leaders: {rank: number; id: string; first_name: string; username: string | null; touches: number}[];
}

export interface WeeklyResponse {
  starts_at: string; resets_at: string; quests: Quest[];
}
export interface PublicProfile {
  id: string; first_name: string; username: string | null; total_touches: number;
  level: number; sessions_completed: number; achievements: string[];
  best_streak: number; invite_count: number;
  achievement_catalog: Record<string, Achievement>;
}

/** Shared daily forecast and immutable personal field assignment, issued server-side. */
export type WeatherEffect = 'sunny' | 'breezy' | 'rainy' | 'fireflies' | 'aurora';
export interface Weather {
  code: WeatherEffect; effect: WeatherEffect; name: string; icon: string;
  description: string; date: string; location: string;
}
export interface FieldMission {
  code: string; name: string; description: string; icon: string;
  target: number; progress: number; xp: number; completed: boolean; claimed: boolean;
  location_code: string | null; location_name: string | null;
}
export interface FieldReport {
  date: string; resets_at: string; weather: Weather;
  missions_completed: number; mission: FieldMission;
}
