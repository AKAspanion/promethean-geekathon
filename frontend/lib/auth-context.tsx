'use client';

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react';
import { setAuthToken, AUTH_UNAUTHORIZED_EVENT } from '@/lib/api';
import type { Oem } from '@/lib/api';

const TOKEN_KEY = 'oem_token';
const OEM_KEY = 'oem_user';

function getStored(): { token: string | null; oem: Oem | null } {
  if (typeof window === 'undefined') return { token: null, oem: null };
  try {
    const token = localStorage.getItem(TOKEN_KEY);
    const oemStr = localStorage.getItem(OEM_KEY);
    const oem = oemStr ? (JSON.parse(oemStr) as Oem) : null;
    return { token, oem };
  } catch {
    return { token: null, oem: null };
  }
}

type AuthContextValue = {
  token: string | null;
  oem: Oem | null;
  isLoggedIn: boolean;
  hydrated: boolean;
  login: (token: string, oem: Oem) => void;
  logout: () => void;
  updateOem: (oem: Oem) => void;
};

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [token, setTokenState] = useState<string | null>(null);
  const [oem, setOemState] = useState<Oem | null>(null);
  const [hydrated, setHydrated] = useState(false);

  useEffect(() => {
    const { token: t, oem: o } = getStored();
    setTokenState(t);
    setOemState(o);
    setAuthToken(t);
    setHydrated(true);
  }, []);

  useEffect(() => {
    const handleUnauthorized = () => {
      setTokenState(null);
      setOemState(null);
      setAuthToken(null);
    };
    window.addEventListener(AUTH_UNAUTHORIZED_EVENT, handleUnauthorized);
    return () => window.removeEventListener(AUTH_UNAUTHORIZED_EVENT, handleUnauthorized);
  }, []);

  const login = useCallback((newToken: string, newOem: Oem) => {
    setTokenState(newToken);
    setOemState(newOem);
    setAuthToken(newToken);
    localStorage.setItem(TOKEN_KEY, newToken);
    localStorage.setItem(OEM_KEY, JSON.stringify(newOem));
  }, []);

  const logout = useCallback(() => {
    setTokenState(null);
    setOemState(null);
    setAuthToken(null);
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(OEM_KEY);
  }, []);

  const updateOem = useCallback((updatedOem: Oem) => {
    setOemState(updatedOem);
    localStorage.setItem(OEM_KEY, JSON.stringify(updatedOem));
  }, []);

  const value = useMemo<AuthContextValue>(
    () => ({
      token,
      oem,
      isLoggedIn: hydrated && !!token,
      hydrated,
      login,
      logout,
      updateOem,
    }),
    [token, oem, hydrated, login, logout, updateOem],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used within AuthProvider');
  return ctx;
}
