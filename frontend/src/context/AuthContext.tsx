import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import {
  SESSION_EXPIRED_EVENT,
  api,
  clearTokens,
  getAccessToken,
  getRefreshToken,
  setTokens,
  type TokenPair,
} from "../lib/api";
import type { ConsentRequirement, User } from "../lib/types";

type AuthContextValue = {
  user: User | null;
  loading: boolean;
  consentRequirements: ConsentRequirement[];
  register: (email: string, password: string, consents: ConsentRequirement[]) => Promise<void>;
  loginWithPassword: (email: string, password: string) => Promise<void>;
  requestCode: (email: string) => Promise<{ expires_in: number; dev_code?: string | null }>;
  verifyCode: (email: string, code: string) => Promise<void>;
  changePassword: (currentPassword: string | null, newPassword: string) => Promise<void>;
  requestPasswordReset: (email: string) => Promise<{ expires_in: number; dev_code?: string | null }>;
  confirmPasswordReset: (email: string, code: string, newPassword: string) => Promise<void>;
  acceptConsents: (consents: ConsentRequirement[]) => Promise<void>;
  logout: () => Promise<void>;
};

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const [consentRequirements, setConsentRequirements] = useState<ConsentRequirement[]>([]);

  useEffect(() => {
    api<ConsentRequirement[]>("/auth/consents/required")
      .then(setConsentRequirements)
      .catch(() => setConsentRequirements([]));
  }, []);

  useEffect(() => {
    let cancelled = false;

    const bootstrap = async () => {
      if (!getAccessToken() && !getRefreshToken()) {
        setLoading(false);
        return;
      }
      try {
        const me = await api<User>("/auth/me");
        if (!cancelled) setUser(me);
      } catch {
        clearTokens();
      } finally {
        if (!cancelled) setLoading(false);
      }
    };

    bootstrap().catch(() => setLoading(false));

    const handleExpired = () => setUser(null);
    window.addEventListener(SESSION_EXPIRED_EVENT, handleExpired);
    return () => {
      cancelled = true;
      window.removeEventListener(SESSION_EXPIRED_EVENT, handleExpired);
    };
  }, []);

  const storeSession = useCallback((tokens: TokenPair & { user: User }) => {
    setTokens(tokens);
    setUser(tokens.user);
  }, []);

  const register = useCallback(
    async (email: string, password: string, consents: ConsentRequirement[]) => {
      const tokens = await api<TokenPair & { user: User }>("/auth/register", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password, consents }),
      });
      storeSession(tokens);
    },
    [storeSession],
  );

  const loginWithPassword = useCallback(
    async (email: string, password: string) => {
      const tokens = await api<TokenPair & { user: User }>("/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password }),
      });
      storeSession(tokens);
    },
    [storeSession],
  );

  const requestCode = useCallback(async (email: string) => {
    return api<{ expires_in: number; dev_code?: string | null; message: string }>("/auth/otp/request", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email }),
    });
  }, []);

  const verifyCode = useCallback(
    async (email: string, code: string) => {
      const tokens = await api<TokenPair & { user: User }>("/auth/otp/verify", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, code }),
      });
      storeSession(tokens);
    },
    [storeSession],
  );

  const changePassword = useCallback(
    async (currentPassword: string | null, newPassword: string) => {
      const tokens = await api<TokenPair & { user: User }>("/auth/password", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ current_password: currentPassword, new_password: newPassword }),
      });
      storeSession(tokens);
    },
    [storeSession],
  );

  const requestPasswordReset = useCallback(async (email: string) => {
    return api<{ expires_in: number; dev_code?: string | null; message: string }>("/auth/password/reset/request", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email }),
    });
  }, []);

  const confirmPasswordReset = useCallback(
    async (email: string, code: string, newPassword: string) => {
      const tokens = await api<TokenPair & { user: User }>("/auth/password/reset/confirm", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, code, new_password: newPassword }),
      });
      storeSession(tokens);
    },
    [storeSession],
  );

  const acceptConsents = useCallback(async (consents: ConsentRequirement[]) => {
    const updated = await api<User>("/auth/consents", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ consents }),
    });
    setUser(updated);
  }, []);

  const logout = useCallback(async () => {
    const refreshToken = getRefreshToken();
    if (refreshToken) {
      await api<void>("/auth/logout", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ refresh_token: refreshToken }),
      }).catch(() => undefined);
    }
    clearTokens();
    setUser(null);
  }, []);

  const value = useMemo(
    () => ({
      user,
      loading,
      consentRequirements,
      register,
      loginWithPassword,
      requestCode,
      verifyCode,
      changePassword,
      requestPasswordReset,
      confirmPasswordReset,
      acceptConsents,
      logout,
    }),
    [
      user,
      loading,
      consentRequirements,
      register,
      loginWithPassword,
      requestCode,
      verifyCode,
      changePassword,
      requestPasswordReset,
      confirmPasswordReset,
      acceptConsents,
      logout,
    ],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const value = useContext(AuthContext);
  if (!value) throw new Error("useAuth must be used inside AuthProvider");
  return value;
}
