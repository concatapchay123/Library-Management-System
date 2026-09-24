import React from 'react';
import { useSession } from './context';
import { LoginForm } from './LoginForm';
import { useTokens } from '../../shared/tokens';

export interface ProtectedRouteProps {
  children: React.ReactNode;
  fallback?: React.ReactNode;
}

/**
 * Protected Route Guard for OpenLibraryOS (FE-003).
 *
 * CRITICAL ARCHITECTURAL INVARIANT:
 * The client-side route guard is a user-experience routing convenience and
 * session indicator ONLY. It MUST NEVER be treated as a security or authorization
 * boundary.
 * Authoritative access control, permission evaluation, and tenant isolation
 * are enforced exclusively by the backend application/domain services and
 * database policies on every authenticated API request.
 */
export function ProtectedRoute({ children, fallback }: ProtectedRouteProps) {
  const { isAuthenticated, isLoading } = useSession();
  const tokens = useTokens();

  if (isLoading) {
    return (
      <div
        role="status"
        aria-live="polite"
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          padding: tokens.spacing['2xl'],
          fontFamily: tokens.typography.fontFamily,
          fontSize: tokens.typography.fontSizes.md,
          color: tokens.colors.textSecondary,
        }}
      >
        <span>Checking session status...</span>
      </div>
    );
  }

  if (!isAuthenticated) {
    return fallback ? <>{fallback}</> : <LoginForm />;
  }

  return <>{children}</>;
}

export default ProtectedRoute;
