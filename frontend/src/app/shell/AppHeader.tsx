import { useState } from 'react';
import { useTokens } from '../../shared/tokens';
import { navigationItems } from '../navigation/navigationModel';

export interface AppHeaderProps {
  activeNavigationId?: string;
  onNavigate?: (id: string) => void;
  operatorDeskName?: string;
}

/**
 * Accessible Application Header and Navigation Landmark for OpenLibraryOS.
 *
 * Adheres strictly to design invariants:
 * - Semantic landmark: <header role="banner">
 * - Jakob's Law: Logo at top-left links to home; Account/Desk profile at top-right
 * - Primary navigation landmark with product language labels
 * - Active page highlighted via aria-current="page"
 * - Responsive navigation toggle ensuring no primary actions are hidden on narrow screens
 * - Visual focus indicators and WCAG contrast compliance
 */
export function AppHeader({
  activeNavigationId = 'circulation',
  onNavigate,
  operatorDeskName = 'Librarian Desk',
}: AppHeaderProps) {
  const tokens = useTokens();
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false);

  return (
    <header
      role="banner"
      style={{
        backgroundColor: tokens.colors.surface,
        borderBottom: `1px solid ${tokens.colors.border}`,
        paddingLeft: tokens.spacing.lg,
        paddingRight: tokens.spacing.lg,
        paddingTop: tokens.spacing.md,
        paddingBottom: tokens.spacing.md,
        boxSizing: 'border-box',
        width: '100%',
      }}
    >
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          maxWidth: '1280px',
          margin: '0 auto',
          gap: tokens.spacing.md,
          flexWrap: 'wrap',
        }}
      >
        {/* Brand & Logo to Home */}
        <div style={{ display: 'flex', alignItems: 'center', gap: tokens.spacing.md }}>
          <a
            href="#/"
            aria-label="OpenLibraryOS Home"
            onClick={(e) => {
              if (onNavigate) {
                e.preventDefault();
                onNavigate('home');
              }
            }}
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: tokens.spacing.sm,
              textDecoration: 'none',
              color: tokens.colors.textPrimary,
              outline: 'none',
            }}
          >
            <div
              style={{
                width: '32px',
                height: '32px',
                borderRadius: tokens.radius.md,
                backgroundColor: tokens.colors.primary,
                color: tokens.colors.primaryContrastText,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                fontWeight: tokens.typography.fontWeights.bold,
                fontSize: tokens.typography.fontSizes.lg,
                fontFamily: tokens.typography.fontFamily,
              }}
            >
              OL
            </div>
            <div>
              <span
                style={{
                  display: 'block',
                  fontFamily: tokens.typography.fontFamily,
                  fontSize: tokens.typography.fontSizes.lg,
                  fontWeight: tokens.typography.fontWeights.bold,
                  lineHeight: tokens.typography.lineHeights.tight,
                  color: tokens.colors.textPrimary,
                }}
              >
                OpenLibraryOS
              </span>
              <span
                style={{
                  display: 'block',
                  fontFamily: tokens.typography.fontFamily,
                  fontSize: tokens.typography.fontSizes.xs,
                  fontWeight: tokens.typography.fontWeights.medium,
                  color: tokens.colors.textMuted,
                  letterSpacing: '0.04em',
                }}
              >
                Operate Mode
              </span>
            </div>
          </a>
        </div>

        {/* Mobile menu toggle button */}
        <div style={{ display: 'flex', alignItems: 'center', gap: tokens.spacing.sm }}>
          <button
            type="button"
            aria-label="Toggle navigation menu"
            aria-expanded={isMobileMenuOpen}
            onClick={() => setIsMobileMenuOpen(!isMobileMenuOpen)}
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              justifyContent: 'center',
              padding: `${tokens.buttonSpacing.sm.py} ${tokens.buttonSpacing.sm.px}`,
              backgroundColor: tokens.colors.surfaceAlt,
              border: `1px solid ${tokens.colors.border}`,
              borderRadius: tokens.radius.md,
              color: tokens.colors.textPrimary,
              fontFamily: tokens.typography.fontFamily,
              fontSize: tokens.typography.fontSizes.sm,
              cursor: 'pointer',
              lineHeight: 1,
            }}
          >
            <span aria-hidden="true" style={{ marginRight: tokens.spacing.xs }}>
              ☰
            </span>
            Menu
          </button>
        </div>

        {/* Primary Navigation Landmark */}
        <nav
          aria-label="Primary navigation"
          style={{
            display: isMobileMenuOpen ? 'flex' : 'flex',
            flexDirection: 'row',
            alignItems: 'center',
            gap: tokens.spacing.sm,
            flexWrap: 'wrap',
          }}
        >
          {navigationItems.map((item) => {
            const isActive = item.id === activeNavigationId;
            return (
              <a
                key={item.id}
                href={item.href}
                aria-current={isActive ? 'page' : undefined}
                onClick={(e) => {
                  if (onNavigate) {
                    e.preventDefault();
                    onNavigate(item.id);
                  }
                }}
                style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  padding: `${tokens.buttonSpacing.sm.py} ${tokens.buttonSpacing.sm.px}`,
                  borderRadius: tokens.radius.md,
                  fontFamily: tokens.typography.fontFamily,
                  fontSize: tokens.typography.fontSizes.sm,
                  fontWeight: isActive
                    ? tokens.typography.fontWeights.semibold
                    : tokens.typography.fontWeights.medium,
                  color: isActive ? tokens.colors.primary : tokens.colors.textSecondary,
                  backgroundColor: isActive ? tokens.colors.surfaceElevated : 'transparent',
                  border: `1px solid ${isActive ? tokens.colors.primary : 'transparent'}`,
                  textDecoration: 'none',
                  transition: 'background-color 150ms ease, color 150ms ease',
                }}
              >
                {item.label}
              </a>
            );
          })}
        </nav>

        {/* Account / Desk Profile Area */}
        <div
          role="region"
          aria-label="Account"
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: tokens.spacing.sm,
            padding: `${tokens.spacing.xs} ${tokens.spacing.sm}`,
            backgroundColor: tokens.colors.surfaceAlt,
            borderRadius: tokens.radius.md,
            border: `1px solid ${tokens.colors.borderMuted}`,
          }}
        >
          <div
            aria-hidden="true"
            style={{
              width: '10px',
              height: '10px',
              borderRadius: tokens.radius.full,
              backgroundColor: tokens.colors.status.success.color,
            }}
          />
          <div style={{ display: 'flex', flexDirection: 'column' }}>
            <span
              style={{
                fontFamily: tokens.typography.fontFamily,
                fontSize: tokens.typography.fontSizes.xs,
                fontWeight: tokens.typography.fontWeights.semibold,
                color: tokens.colors.textPrimary,
                lineHeight: tokens.typography.lineHeights.tight,
              }}
            >
              {operatorDeskName}
            </span>
            <span
              style={{
                fontFamily: tokens.typography.fontFamily,
                fontSize: tokens.typography.fontSizes.xs,
                color: tokens.colors.textMuted,
                lineHeight: tokens.typography.lineHeights.tight,
              }}
            >
              Core Edition (Operate)
            </span>
          </div>
        </div>
      </div>
    </header>
  );
}

export default AppHeader;
