import type { TokenResponse, User } from "./types";

const TOKEN_KEY = "fa_token";
const USER_KEY  = "fa_user";

export function saveSession(token: TokenResponse): void {
  if (typeof window === "undefined") return;
  localStorage.setItem(TOKEN_KEY, token.access_token);
  localStorage.setItem(
    USER_KEY,
    JSON.stringify({ id: token.user_id, username: token.username })
  );
}

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(TOKEN_KEY);
}

export function getUser(): Pick<User, "id" | "username"> | null {
  if (typeof window === "undefined") return null;
  const raw = localStorage.getItem(USER_KEY);
  if (!raw) return null;
  try { return JSON.parse(raw); } catch { return null; }
}

export function clearSession(): void {
  if (typeof window === "undefined") return;
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(USER_KEY);
}

export function isLoggedIn(): boolean {
  return Boolean(getToken());
}
