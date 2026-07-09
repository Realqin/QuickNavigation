import { App } from 'antd';
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react';
import { fetchAuthMe, login as apiLogin, logout as apiLogout } from '../api';
import type { UserInfo } from '../types/auth';
import { clearStoredSession } from '../utils/authStorage';
import { invalidateDictCache } from '../utils/dictCache';
import { clearGetCoalesce } from '../utils/getCoalesce';

const TOKEN_KEY = 'qn_access_token';
const USER_KEY = 'qn_user';

interface AuthContextValue {
  user: UserInfo | null;
  token: string | null;
  loading: boolean;
  login: (username: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  refreshUser: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

function readStoredUser(): UserInfo | null {
  if (!localStorage.getItem(TOKEN_KEY)) {
    return null;
  }
  const raw = localStorage.getItem(USER_KEY);
  if (!raw) return null;
  try {
    return JSON.parse(raw) as UserInfo;
  } catch {
    return null;
  }
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const { message } = App.useApp();
  const [user, setUser] = useState<UserInfo | null>(() => readStoredUser());
  const [token, setToken] = useState<string | null>(() => localStorage.getItem(TOKEN_KEY));
  const [loading, setLoading] = useState(true);

  const persistSession = useCallback((nextToken: string, nextUser: UserInfo) => {
    localStorage.setItem(TOKEN_KEY, nextToken);
    localStorage.setItem(USER_KEY, JSON.stringify(nextUser));
    setToken(nextToken);
    setUser(nextUser);
  }, []);

  const clearSession = useCallback(() => {
    clearStoredSession();
    invalidateDictCache();
    clearGetCoalesce();
    setToken(null);
    setUser(null);
  }, []);

  const refreshUser = useCallback(async () => {
    if (!localStorage.getItem(TOKEN_KEY)) {
      clearSession();
      return;
    }
    const me = await fetchAuthMe();
    persistSession(localStorage.getItem(TOKEN_KEY) || '', me);
  }, [clearSession, persistSession]);

  useEffect(() => {
    const bootstrap = async () => {
      const storedToken = localStorage.getItem(TOKEN_KEY);
      if (!storedToken) {
        clearSession();
        setLoading(false);
        return;
      }
      try {
        await refreshUser();
      } catch {
        clearSession();
      } finally {
        setLoading(false);
      }
    };
    void bootstrap();
  }, [clearSession, refreshUser]);

  const login = useCallback(
    async (username: string, password: string) => {
      const result = await apiLogin(username, password);
      persistSession(result.access_token, result.user);
      setLoading(false);
      message.success('登录成功');
    },
    [message, persistSession],
  );

  const logout = useCallback(async () => {
    try {
      await apiLogout();
    } catch {
      // 忽略退出接口失败，仍清理本地会话
    } finally {
      clearSession();
    }
  }, [clearSession]);

  const value = useMemo(
    () => ({
      user,
      token,
      loading,
      login,
      logout,
      refreshUser,
    }),
    [user, token, loading, login, logout, refreshUser],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    throw new Error('useAuth must be used within AuthProvider');
  }
  return ctx;
}
