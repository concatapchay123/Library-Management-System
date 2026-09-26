import { useState, useEffect } from 'react';
import { useTokens } from '../../shared/tokens';
import { apiClient, AccessPrincipal } from '../../shared/api';
import { Dialog } from '../../shared/components';

export interface UserProfileModalProps {
  isOpen: boolean;
  onClose: () => void;
  accessToken?: string | null;
}

/**
 * User Profile & Session Inspection Modal (M-05).
 *
 * Implements accessible modal dialog for inspecting current authenticated
 * operator principal, organization tenant, session identifier, and granted permissions.
 *
 * Design Invariants:
 * - Jakob's Law: Accessible modal dialog with close button and Esc dismissal
 * - Single-column structured metadata view
 * - WCAG AA contrast compliance with design tokens
 * - Button whitespace ratio (2:1)
 */
export function UserProfileModal({
  isOpen,
  onClose,
  accessToken,
}: UserProfileModalProps) {
  const tokens = useTokens();
  const [profile, setProfile] = useState<AccessPrincipal | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  useEffect(() => {
    let isMounted = true;
    if (isOpen) {
      setIsLoading(true);
      setErrorMessage(null);
      apiClient.auth
        .getCurrentPrincipal(accessToken ?? undefined)
        .then((data) => {
          if (isMounted) {
            setProfile(data);
            setIsLoading(false);
          }
        })
        .catch((err) => {
          if (isMounted) {
            setErrorMessage(err instanceof Error ? err.message : 'Không thể tải thông tin hồ sơ.');
            setIsLoading(false);
          }
        });
    }
    return () => {
      isMounted = false;
    };
  }, [isOpen, accessToken]);

  return (
    <Dialog
      isOpen={isOpen}
      onClose={onClose}
      title="Hồ Sơ Cán Bộ Thư Viện"
      description="Operator Profile & Session Context"
      maxWidth="520px"
    >

        {/* Content Body */}
        <div
          style={{
            padding: `${tokens.spacing.xl} ${tokens.spacing.xl}`,
            display: 'flex',
            flexDirection: 'column',
            gap: tokens.spacing.lg,
          }}
        >
          {isLoading && (
            <div
              role="status"
              style={{
                padding: tokens.spacing.lg,
                textAlign: 'center',
                color: tokens.colors.textSecondary,
                fontFamily: tokens.typography.fontFamily,
                fontSize: tokens.typography.fontSizes.sm,
              }}
            >
              Đang tải thông tin phiên làm việc...
            </div>
          )}

          {errorMessage && (
            <div
              role="alert"
              style={{
                padding: tokens.spacing.md,
                backgroundColor: '#fef2f2',
                border: '1px solid #f87171',
                borderRadius: tokens.radius.md,
                color: '#b91c1c',
                fontSize: tokens.typography.fontSizes.sm,
                fontFamily: tokens.typography.fontFamily,
              }}
            >
              {errorMessage}
            </div>
          )}

          {!isLoading && profile && (
            <div
              style={{
                display: 'flex',
                flexDirection: 'column',
                gap: tokens.spacing.md,
              }}
            >
              {/* User ID */}
              <div>
                <label
                  style={{
                    display: 'block',
                    fontSize: tokens.typography.fontSizes.xs,
                    fontWeight: tokens.typography.fontWeights.medium,
                    color: tokens.colors.textMuted,
                    marginBottom: tokens.spacing.xs,
                    fontFamily: tokens.typography.fontFamily,
                    textTransform: 'uppercase',
                    letterSpacing: '0.05em',
                  }}
                >
                  Mã Người Dùng (User ID)
                </label>
                <div
                  style={{
                    padding: `${tokens.spacing.sm} ${tokens.spacing.md}`,
                    backgroundColor: tokens.colors.surfaceAlt,
                    border: `1px solid ${tokens.colors.border}`,
                    borderRadius: tokens.radius.sm,
                    fontFamily: 'monospace',
                    fontSize: tokens.typography.fontSizes.xs,
                    color: tokens.colors.textPrimary,
                    wordBreak: 'break-all',
                  }}
                >
                  {profile.user_id}
                </div>
              </div>

              {/* Organization ID */}
              <div>
                <label
                  style={{
                    display: 'block',
                    fontSize: tokens.typography.fontSizes.xs,
                    fontWeight: tokens.typography.fontWeights.medium,
                    color: tokens.colors.textMuted,
                    marginBottom: tokens.spacing.xs,
                    fontFamily: tokens.typography.fontFamily,
                    textTransform: 'uppercase',
                    letterSpacing: '0.05em',
                  }}
                >
                  Mã Đơn Vị (Organization ID)
                </label>
                <div
                  style={{
                    padding: `${tokens.spacing.sm} ${tokens.spacing.md}`,
                    backgroundColor: tokens.colors.surfaceAlt,
                    border: `1px solid ${tokens.colors.border}`,
                    borderRadius: tokens.radius.sm,
                    fontFamily: 'monospace',
                    fontSize: tokens.typography.fontSizes.xs,
                    color: tokens.colors.textPrimary,
                    wordBreak: 'break-all',
                  }}
                >
                  {profile.organization_id}
                </div>
              </div>

              {/* Session ID */}
              <div>
                <label
                  style={{
                    display: 'block',
                    fontSize: tokens.typography.fontSizes.xs,
                    fontWeight: tokens.typography.fontWeights.medium,
                    color: tokens.colors.textMuted,
                    marginBottom: tokens.spacing.xs,
                    fontFamily: tokens.typography.fontFamily,
                    textTransform: 'uppercase',
                    letterSpacing: '0.05em',
                  }}
                >
                  Mã Phiên (Session ID)
                </label>
                <div
                  style={{
                    padding: `${tokens.spacing.sm} ${tokens.spacing.md}`,
                    backgroundColor: tokens.colors.surfaceAlt,
                    border: `1px solid ${tokens.colors.border}`,
                    borderRadius: tokens.radius.sm,
                    fontFamily: 'monospace',
                    fontSize: tokens.typography.fontSizes.xs,
                    color: tokens.colors.textPrimary,
                    wordBreak: 'break-all',
                  }}
                >
                  {profile.session_id ? String(profile.session_id) : '—'}
                </div>
              </div>

              {/* Permissions */}
              <div>
                <label
                  style={{
                    display: 'block',
                    fontSize: tokens.typography.fontSizes.xs,
                    fontWeight: tokens.typography.fontWeights.medium,
                    color: tokens.colors.textMuted,
                    marginBottom: tokens.spacing.xs,
                    fontFamily: tokens.typography.fontFamily,
                    textTransform: 'uppercase',
                    letterSpacing: '0.05em',
                  }}
                >
                  Quyền Hạn (Permissions)
                </label>
                <div
                  style={{
                    display: 'flex',
                    flexWrap: 'wrap',
                    gap: tokens.spacing.xs,
                    padding: `${tokens.spacing.sm} ${tokens.spacing.md}`,
                    backgroundColor: tokens.colors.surfaceAlt,
                    border: `1px solid ${tokens.colors.border}`,
                    borderRadius: tokens.radius.sm,
                    minHeight: '38px',
                    alignItems: 'center',
                  }}
                >
                  {profile.permissions && profile.permissions.length > 0 ? (
                    profile.permissions.map((perm) => (
                      <span
                        key={perm}
                        style={{
                          display: 'inline-flex',
                          alignItems: 'center',
                          padding: '2px 8px',
                          backgroundColor: '#eff6ff',
                          color: '#1d4ed8',
                          border: '1px solid #bfdbfe',
                          borderRadius: tokens.radius.full,
                          fontSize: '11px',
                          fontFamily: 'monospace',
                          fontWeight: tokens.typography.fontWeights.medium,
                        }}
                      >
                        {perm}
                      </span>
                    ))
                  ) : (
                    <span
                      style={{
                        fontSize: tokens.typography.fontSizes.xs,
                        color: tokens.colors.textMuted,
                        fontFamily: tokens.typography.fontFamily,
                      }}
                    >
                      Toàn quyền vận hành tiêu chuẩn
                    </span>
                  )}
                </div>
              </div>
            </div>
          )}
        </div>

        {/* Footer */}
        <div
          style={{
            display: 'flex',
            justifyContent: 'flex-end',
            padding: `${tokens.spacing.md} ${tokens.spacing.xl}`,
            borderTop: `1px solid ${tokens.colors.border}`,
            backgroundColor: tokens.colors.surfaceAlt,
          }}
        >
          <button
            type="button"
            onClick={onClose}
            style={{
              padding: `${tokens.buttonSpacing.sm.py} ${tokens.buttonSpacing.sm.px}`,
              backgroundColor: tokens.colors.surface,
              border: `1px solid ${tokens.colors.border}`,
              borderRadius: tokens.radius.sm,
              color: tokens.colors.textPrimary,
              fontFamily: tokens.typography.fontFamily,
              fontSize: tokens.typography.fontSizes.sm,
              fontWeight: tokens.typography.fontWeights.medium,
              cursor: 'pointer',
            }}
          >
            Đóng
          </button>
        </div>
    </Dialog>
  );
}
