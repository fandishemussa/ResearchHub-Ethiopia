export interface AuthTokens {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_at: string;
}

export interface AuthUser {
  id: string;
  email: string;
  username: string;
  full_name: string;
  is_active: boolean;
  is_verified: boolean;
  is_suspended: boolean;
  university_id: string | null;
  faculty_id: string | null;
  department_id: string | null;
  last_login_at: string | null;
  created_at: string;
  roles: string[];
  permissions: string[];
}

const sessionKey = "researchhub.auth";
export const authChangedEvent = "researchhub:auth-changed";

export function readAuthTokens(): AuthTokens | null {
  if (typeof window === "undefined") return null;
  const raw = window.sessionStorage.getItem(sessionKey);
  if (!raw) return null;
  try {
    const parsed = JSON.parse(raw) as Partial<AuthTokens>;
    if (
      typeof parsed.access_token !== "string" ||
      typeof parsed.refresh_token !== "string" ||
      typeof parsed.expires_at !== "string"
    ) {
      clearAuthTokens();
      return null;
    }
    return parsed as AuthTokens;
  } catch {
    clearAuthTokens();
    return null;
  }
}

export function storeAuthTokens(tokens: AuthTokens): void {
  if (typeof window === "undefined") return;
  window.sessionStorage.setItem(sessionKey, JSON.stringify(tokens));
  window.dispatchEvent(new Event(authChangedEvent));
}

export function clearAuthTokens(): void {
  if (typeof window === "undefined") return;
  window.sessionStorage.removeItem(sessionKey);
  window.dispatchEvent(new Event(authChangedEvent));
}

export function authorizationHeader(): Record<string, string> {
  const tokens = readAuthTokens();
  return tokens ? { Authorization: `Bearer ${tokens.access_token}` } : {};
}
