import React, { useState } from 'react';
import { useTokens } from '../../shared/tokens';
import { Button, Input, StatusMessage } from '../../shared/components';
import { useSession } from './context';

export interface LoginFormProps {
  onSuccess?: () => void;
  initialSlug?: string;
}

/**
 * Accessible Login Form for OpenLibraryOS (FE-003).
 *
 * Adheres strictly to design invariants:
 * - Jakob's Law: Familiar field order (Organization Slug -> Email -> Password -> Sign In)
 * - Hick's Law: Strictly 1 visually primary action (Sign In)
 * - Single-column vertical form stacking
 * - Semantic spacing tokens (24px group-to-group, 32px form-to-submit)
 * - Uniform safe authentication message (zero account enumeration)
 * - WCAG AA contrast compliance and anti-glare surfaces
 */
export function LoginForm({ onSuccess, initialSlug = '' }: LoginFormProps) {
  const tokens = useTokens();
  const { login, error, isLoading, clearError } = useSession();

  const [organizationSlug, setOrganizationSlug] = useState(initialSlug);
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    clearError();
    setIsSubmitting(true);
    try {
      await login({
        organization_slug: organizationSlug.trim(),
        email: email.trim(),
        password,
      });
      if (onSuccess) {
        onSuccess();
      }
    } catch {
      // Safe error is set in session provider state
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        width: '100%',
        minHeight: '70vh',
        boxSizing: 'border-box',
        padding: tokens.spacing.md,
      }}
    >
      <div
        style={{
          width: '100%',
          maxWidth: '440px',
          backgroundColor: tokens.colors.surfaceAlt,
          border: `1px solid ${tokens.colors.border}`,
          borderRadius: tokens.radius.xl,
          padding: tokens.spacing.xl,
          boxSizing: 'border-box',
        }}
      >
        {/* Heading region */}
        <div style={{ marginBottom: tokens.spacing.lg }}>
          <h2
            style={{
              margin: 0,
              fontFamily: tokens.typography.fontFamily,
              fontSize: tokens.typography.fontSizes['2xl'],
              fontWeight: tokens.typography.fontWeights.bold,
              color: tokens.colors.textPrimary,
              lineHeight: tokens.typography.lineHeights.tight,
            }}
          >
            Sign In to OpenLibraryOS
          </h2>
          <p
            style={{
              margin: 0,
              marginTop: tokens.spacing.xs,
              fontFamily: tokens.typography.fontFamily,
              fontSize: tokens.typography.fontSizes.sm,
              color: tokens.colors.textSecondary,
              lineHeight: tokens.typography.lineHeights.normal,
            }}
          >
            Enter your organization credentials to access the library desk.
          </p>
        </div>

        {/* Safe Error Alert */}
        {error && (
          <div style={{ marginBottom: tokens.spacing.lg }}>
            <StatusMessage status="danger" title="Authentication failed">
              {error}
            </StatusMessage>
          </div>
        )}

        {/* Single-column vertical form */}
        <form
          onSubmit={handleSubmit}
          style={{
            display: 'flex',
            flexDirection: 'column',
            gap: tokens.spacing.semantic.groupToGroup,
          }}
        >
          {/* Field 1: Organization Slug */}
          <Input
            id="organization-slug"
            name="organization_slug"
            label="Organization Slug"
            description="Your library system workspace identifier."
            placeholder="e.g. campus-central"
            required
            value={organizationSlug}
            disabled={isSubmitting || isLoading}
            onChange={(e) => setOrganizationSlug(e.target.value)}
          />

          {/* Field 2: Email Address */}
          <Input
            id="email"
            name="email"
            type="email"
            label="Email Address"
            description="Registered staff or patron email."
            placeholder="e.g. librarian@example.test"
            required
            autoComplete="username"
            value={email}
            disabled={isSubmitting || isLoading}
            onChange={(e) => setEmail(e.target.value)}
          />

          {/* Field 3: Password */}
          <Input
            id="password"
            name="password"
            type="password"
            label="Password"
            description="Account credential."
            placeholder="Enter your password"
            required
            autoComplete="current-password"
            value={password}
            disabled={isSubmitting || isLoading}
            onChange={(e) => setPassword(e.target.value)}
          />

          {/* Action region: exactly 1 visually primary action */}
          <div
            style={{
              marginTop: tokens.spacing.md,
              paddingTop: tokens.spacing.md,
              borderTop: `1px solid ${tokens.colors.borderMuted}`,
            }}
          >
            <Button
              type="submit"
              variant="primary"
              size="md"
              isFullWidth
              disabled={isSubmitting || isLoading}
            >
              {isSubmitting || isLoading ? 'Signing In...' : 'Sign In'}
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
}

export default LoginForm;
