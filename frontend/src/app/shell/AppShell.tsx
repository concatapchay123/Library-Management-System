import React, { useState } from 'react';
import { useTokens } from '../../shared/tokens';
import { AppHeader } from './AppHeader';

export interface AppShellProps {
  children: React.ReactNode;
  pageTitle?: string;
  pageSubtitle?: string;
  activeNavigationId?: string;
  onNavigate?: (id: string) => void;
  operatorDeskName?: string;
  accessToken?: string | null;
  onLogout?: () => void;
}

/**
 * Accessible Application Shell for OpenLibraryOS.
 *
 * Adheres strictly to design invariants:
 * - Semantic landmark ordering: Skip Link -> Banner (Header) -> Navigation -> Main Content
 * - Keyboard accessibility: Skip link moves focus directly to main landmark
 * - Clear page heading region with h1
 * - Predictable, single-primary-action layout hierarchy
 * - Anti-glare calibrated surface colors
 */
export function AppShell({
  children,
  pageTitle = 'Circulation Desk',
  pageSubtitle = 'Fast-track book checkout, returns, and patron service',
  activeNavigationId = 'circulation',
  onNavigate,
  operatorDeskName = 'Librarian Desk',
  accessToken,
  onLogout,
}: AppShellProps) {
  const tokens = useTokens();
  const [isSkipLinkFocused, setIsSkipLinkFocused] = useState(false);

  const skipLinkStyle: React.CSSProperties = {
    position: 'absolute',
    left: isSkipLinkFocused ? tokens.spacing.md : '-9999px',
    top: isSkipLinkFocused ? tokens.spacing.md : '-9999px',
    zIndex: 100,
    padding: `${tokens.buttonSpacing.sm.py} ${tokens.buttonSpacing.sm.px}`,
    backgroundColor: tokens.colors.primary,
    color: tokens.colors.primaryContrastText,
    fontFamily: tokens.typography.fontFamily,
    fontSize: tokens.typography.fontSizes.sm,
    fontWeight: tokens.typography.fontWeights.semibold,
    borderRadius: tokens.radius.md,
    border: `2px solid ${tokens.colors.surface}`,
    outline: tokens.focus.cssString,
    textDecoration: 'none',
  };

  return (
    <div
      style={{
        minHeight: '100vh',
        backgroundColor: tokens.colors.surface,
        color: tokens.colors.textPrimary,
        fontFamily: tokens.typography.fontFamily,
        display: 'flex',
        flexDirection: 'column',
      }}
    >
      {/* 1. Skip to Main Content Link for screen readers and keyboard users */}
      <a
        href="#main-content"
        style={skipLinkStyle}
        onFocus={() => setIsSkipLinkFocused(true)}
        onBlur={() => setIsSkipLinkFocused(false)}
      >
        Skip to main content
      </a>

      {/* 2. Banner Landmark */}
      <AppHeader
        activeNavigationId={activeNavigationId}
        onNavigate={onNavigate}
        operatorDeskName={operatorDeskName}
        accessToken={accessToken}
        onLogout={onLogout}
      />

      {/* 3. Main Landmark */}
      <main
        id="main-content"
        role="main"
        tabIndex={-1}
        style={{
          flex: 1,
          maxWidth: '1280px',
          width: '100%',
          margin: '0 auto',
          paddingLeft: tokens.spacing.lg,
          paddingRight: tokens.spacing.lg,
          paddingTop: tokens.spacing.xl,
          paddingBottom: tokens.spacing['2xl'],
          boxSizing: 'border-box',
          outline: 'none',
        }}
      >
        {/* Page Heading Region */}
        <section
          aria-labelledby="page-title-heading"
          style={{
            marginBottom: tokens.spacing.xl,
            borderBottom: `1px solid ${tokens.colors.borderMuted}`,
            paddingBottom: tokens.spacing.lg,
          }}
        >
          <h1
            id="page-title-heading"
            style={{
              margin: 0,
              fontFamily: tokens.typography.fontFamily,
              fontSize: tokens.typography.fontSizes['2xl'],
              fontWeight: tokens.typography.fontWeights.bold,
              lineHeight: tokens.typography.lineHeights.tight,
              color: tokens.colors.textPrimary,
            }}
          >
            {pageTitle}
          </h1>
          {pageSubtitle && (
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
              {pageSubtitle}
            </p>
          )}
        </section>

        {/* Content Workspace */}
        {children}
      </main>
    </div>
  );
}

export default AppShell;
