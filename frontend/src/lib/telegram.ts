interface Haptic {
  impactOccurred(style: 'light' | 'medium' | 'heavy'): void;
  notificationOccurred(type: 'success' | 'warning' | 'error'): void;
}
export interface TelegramApp {
  initData: string;
  colorScheme: 'dark' | 'light';
  HapticFeedback?: Haptic;
  ready(): void;
  expand(): void;
  openTelegramLink(url: string): void;
  onEvent(event: 'themeChanged', callback: () => void): void;
  offEvent(event: 'themeChanged', callback: () => void): void;
}
declare global {
  interface Window {
    Telegram?: { WebApp?: TelegramApp };
  }
}
export function telegram(): TelegramApp | undefined {
  return window.Telegram?.WebApp;
}

let lastHaptic = 0;
export function impact(): void {
  const now = performance.now();
  if (now - lastHaptic > 140) {
    telegram()?.HapticFeedback?.impactOccurred('light');
    lastHaptic = now;
  }
}
export function successHaptic(): void {
  telegram()?.HapticFeedback?.notificationOccurred('success');
}
