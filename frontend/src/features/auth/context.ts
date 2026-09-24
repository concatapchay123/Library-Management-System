import { createContext, useContext } from 'react';
import { AuthContextValue } from './types';

export const AuthContext = createContext<AuthContextValue | undefined>(undefined);

/**
 * Hook to access current in-memory authentication and session state.
 */
export function useSession(): AuthContextValue {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useSession must be used within a SessionProvider');
  }
  return context;
}
