import { telegram } from './telegram';

let demoMode = false;
export function configureAuth(allowDemo: boolean): void {
  demoMode = allowDemo;
  if (!telegram()?.initData && !demoMode) {
    throw new Error('Откройте игру из Telegram, чтобы подтвердить профиль.');
  }
}
export class ApiError extends Error {
  constructor(public status: number, message: string) { super(message); }
}
export async function api<T>(url: string, init: RequestInit = {}): Promise<T> {
  const initData = telegram()?.initData || '';
  const headers = new Headers(init.headers);
  if (initData) headers.set('X-Telegram-Init-Data', initData);
  else if (demoMode) headers.set('X-Demo-User', '777001');
  if (init.body) headers.set('Content-Type', 'application/json');
  const res = await fetch(url, { ...init, headers });
  if (!res.ok) {
    let message = `Ошибка сервера: ${res.status}`;
    try { const payload: { detail?: string } = await res.json(); message = payload.detail || message; }
    catch { /* server might not have returned JSON */ }
    throw new ApiError(res.status, message);
  }
  return res.json() as Promise<T>;
}
