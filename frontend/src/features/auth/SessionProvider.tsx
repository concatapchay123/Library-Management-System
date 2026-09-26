import React, { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import { AuthContextValue, LoginCredentials } from './types';
import { AuthContext } from './context';
import * as authApi from './authApi';

export interface SessionProviderProps {
  children: React.ReactNode;
  initialAccessToken?: string | null;
  autoRefreshOnMount?: boolean;
}

/**
 * In-memory Session Provider for OpenLibraryOS.
 *
 * CRITICAL ARCHITECTURAL INVARIANT:
 * Access tokens are held STRICTLY IN MEMORY (React component state).
 * Access tokens MUST NEVER be stored in localStorage, sessionStorage, or
 * any other persistent browser storage mechanism to prevent persistent
 * credential exposure or cross-session leakage.
 */
export function SessionProvider({
  children,
  initialAccessToken = null,
  autoRefreshOnMount = false,
}: SessionProviderProps) {
  const [accessToken, setAccessToken] = useState<string | null>(initialAccessToken);
  const [isLoading, setIsLoading] = useState<boolean>(autoRefreshOnMount);
  const [error, setError] = useState<string | null>(null);
  const accessTokenRef = useRef<string | null>(initialAccessToken);
  accessTokenRef.current = accessToken;

  const clearError = useCallback(() => {
    setError(null);
  }, []);

  const login = useCallback(async (credentials: LoginCredentials) => {
    setIsLoading(true);
    setError(null);
    try {
      const response = await authApi.login(credentials);
      setAccessToken(response.access_token);
    } catch (err) {
      const message = err instanceof Error ? err.message : authApi.AUTH_SAFE_ERROR_MESSAGE;
      setError(message);
      throw err;
    } finally {
      setIsLoading(false);
    }
  }, []);

  const refresh = useCallback(async (): Promise<boolean> => {
    setIsLoading(true);
    try {
      const response = await authApi.refreshToken();
      setAccessToken(response.access_token);
      setError(null);
      return true;
    } catch {
      const hadPreviousSession = accessTokenRef.current !== null;
      setAccessToken(null);

      // Silent refresh for unauthenticated/guest users on initial mount MUST NOT render a credential error (P2-01)
      if (!hadPreviousSession) {
        setError(null);
      } else {
        // Truthful notice when an active session has expired
        setError(authApi.SESSION_EXPIRED_MESSAGE);
      }
      return false;
    } finally {
      setIsLoading(false);
    }
  }, []);

  const logout = useCallback(async () => {
    setIsLoading(true);
    try {
      await authApi.logout(accessToken);
    } finally {
      setAccessToken(null);
      setError(null);
      setIsLoading(false);
    }
  }, [accessToken]);

  useEffect(() => {
    if (autoRefreshOnMount) {
      void refresh();
    }
  }, [autoRefreshOnMount, refresh]);

  const value = useMemo<AuthContextValue>(
    () => ({
      accessToken,
      isAuthenticated: accessToken !== null,
      isLoading,
      error,
      login,
      refresh,
      logout,
      clearError,
    }),
    [accessToken, isLoading, error, login, refresh, logout, clearError],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export default SessionProvider;
