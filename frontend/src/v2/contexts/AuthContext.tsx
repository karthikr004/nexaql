import { createContext, useContext, useState, useEffect, useCallback, type ReactNode } from 'react';
import type { AuthUser, AuthMode } from '../types/auth';

interface AuthContextValue {
  user: AuthUser | null;
  loading: boolean;
  authMode: AuthMode;
  providers: string[];
  isAdmin: boolean;
  login: (provider: string) => void;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue>({
  user: null,
  loading: true,
  authMode: 'dev',
  providers: [],
  isAdmin: false,
  login: () => {},
  logout: async () => {},
});

const DEV_USER: AuthUser = {
  id: 0,
  email: 'dev@localhost',
  name: 'Developer',
  avatarUrl: null,
  roles: ['admin'],
};

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [loading, setLoading] = useState(true);
  const [authMode, setAuthMode] = useState<AuthMode>('dev');
  const [providers, setProviders] = useState<string[]>([]);

  const loadSession = useCallback(async () => {
    try {
      const [modeRes, sessionRes] = await Promise.all([
        fetch('/api/auth/mode'),
        fetch('/api/auth/session', { credentials: 'include' }),
      ]);

      if (modeRes.ok) {
        const modeData = await modeRes.json();
        const mode: AuthMode = modeData.mode === 'oauth' ? 'oauth' : 'dev';
        setAuthMode(mode);

        if (mode === 'dev') {
          setUser(DEV_USER);
          setLoading(false);
          return;
        }

        const providersRes = await fetch('/api/auth/providers');
        if (providersRes.ok) {
          const pData = await providersRes.json();
          setProviders(pData.providers ?? []);
        }
      }

      if (sessionRes.ok) {
        const sessionData = await sessionRes.json();
        if (sessionData.authenticated && sessionData.user) {
          const u = sessionData.user;
          setUser({
            id: u.id,
            email: u.email,
            name: u.name ?? null,
            avatarUrl: u.avatar_url ?? null,
            roles: u.roles ?? [],
          });
        }
      }
    } catch {
      // API not ready yet
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadSession();
  }, [loadSession]);

  const login = useCallback((provider: string) => {
    window.location.href = `/api/auth/login/${provider}`;
  }, []);

  const logout = useCallback(async () => {
    try {
      await fetch('/api/auth/logout', { method: 'POST', credentials: 'include' });
    } catch {
      // best-effort
    }
    setUser(null);
  }, []);

  const isAdmin = user?.roles.includes('admin') || user?.roles.includes('*') || false;

  return (
    <AuthContext.Provider value={{ user, loading, authMode, providers, isAdmin, login, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  return useContext(AuthContext);
}
