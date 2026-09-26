import { useState, useEffect, useRef } from 'react';
import { useTokens } from '../../shared/tokens';
import { coreNavigationItems, editionNavigationItems } from '../navigation/navigationModel';
import { ChangePasswordModal } from '../../features/auth/ChangePasswordModal';
import { UserProfileModal } from '../../features/auth/UserProfileModal';

export interface AppHeaderProps {
  activeNavigationId?: string;
  onNavigate?: (id: string) => void;
  operatorDeskName?: string;
  accessToken?: string | null;
  onLogout?: () => void;
}

/**
 * Accessible Application Header and Navigation Landmark for OpenLibraryOS.
 *
 * Adheres strictly to design invariants:
 * - Semantic landmark: <header role="banner">
 * - Jakob's Law: Logo at top-left links to home; Account/Desk profile at top-right
 * - Primary navigation landmark with bilingual product language labels (Vietnamese & English)
 * - Active page highlighted via aria-current="page"
 * - Responsive navigation: clean single-row on desktop; slide-out drawer on compact/mobile screens
 * - 2:1 button whitespace ratio and Title Case formatting
 * - Visual focus indicators and WCAG contrast compliance
 */
export function AppHeader({
  activeNavigationId = 'circulation',
  onNavigate,
  operatorDeskName = 'Librarian Desk',
  accessToken,
  onLogout,
}: AppHeaderProps) {
  const tokens = useTokens();
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false);
  const [isPasswordModalOpen, setIsPasswordModalOpen] = useState(false);
  const [isProfileModalOpen, setIsProfileModalOpen] = useState(false);
  const mobileToggleRef = useRef<HTMLButtonElement>(null);
  const mobileDrawerRef = useRef<HTMLDivElement>(null);

  // Focus management and keyboard navigation for mobile drawer
  useEffect(() => {
    if (!isMobileMenuOpen) return;

    // Auto-focus first focusable element when drawer opens
    const timer = setTimeout(() => {
      if (mobileDrawerRef.current) {
        const firstFocusable = mobileDrawerRef.current.querySelector<HTMLElement>(
          'button:not([disabled]), [href], input:not([disabled])'
        );
        firstFocusable?.focus();
      }
    }, 50);

    function handleKeyDown(e: KeyboardEvent) {
      if (e.key === 'Escape') {
        setIsMobileMenuOpen(false);
        mobileToggleRef.current?.focus();
        return;
      }

      if (e.key === 'Tab' || e.code === 'Tab') {
        if (!mobileDrawerRef.current) return;
        const focusables = Array.from(
          mobileDrawerRef.current.querySelectorAll<HTMLElement>(
            'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'
          )
        ).filter((el) => el.getAttribute('tabindex') !== '-1');

        if (focusables.length === 0) {
          e.preventDefault();
          return;
        }

        const firstElement = focusables[0];
        const lastElement = focusables[focusables.length - 1];
        if (!firstElement || !lastElement) return;

        if (e.shiftKey) {
          if (document.activeElement === firstElement || document.activeElement === mobileDrawerRef.current) {
            e.preventDefault();
            lastElement.focus();
          }
        } else {
          if (document.activeElement === lastElement) {
            e.preventDefault();
            firstElement.focus();
          }
        }
      }
    }

    window.addEventListener('keydown', handleKeyDown);
    return () => {
      clearTimeout(timer);
      window.removeEventListener('keydown', handleKeyDown);
    };
  }, [isMobileMenuOpen]);

  return (
    <>
      {/* Responsive layout styles */}
      <style>{`
        @media (max-width: 1024px) {
          .openlibrary-desktop-nav {
            display: none !important;
          }
          .openlibrary-desktop-account {
            display: none !important;
          }
          .openlibrary-mobile-toggle {
            display: inline-flex !important;
          }
        }
        @media (min-width: 1025px) {
          .openlibrary-desktop-nav {
            display: flex !important;
          }
          .openlibrary-desktop-account {
            display: flex !important;
          }
          .openlibrary-mobile-toggle {
            display: none !important;
          }
        }
      `}</style>

      <header
        role="banner"
        style={{
          backgroundColor: tokens.colors.surface,
          borderBottom: `1px solid ${tokens.colors.border}`,
          paddingLeft: tokens.spacing.md,
          paddingRight: tokens.spacing.md,
          paddingTop: tokens.spacing.sm,
          paddingBottom: tokens.spacing.sm,
          boxSizing: 'border-box',
          width: '100%',
          maxWidth: '100vw',
          overflow: 'hidden',
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
            flexWrap: 'nowrap',
          }}
        >
          {/* Brand & Logo to Home */}
          <div style={{ display: 'flex', alignItems: 'center', gap: tokens.spacing.md, flexShrink: 0 }}>
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
                  width: '34px',
                  height: '34px',
                  borderRadius: tokens.radius.md,
                  backgroundColor: tokens.colors.primary,
                  color: tokens.colors.primaryContrastText,
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  fontWeight: tokens.typography.fontWeights.bold,
                  fontSize: tokens.typography.fontSizes.lg,
                  fontFamily: tokens.typography.fontFamily,
                  flexShrink: 0,
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
                  Thư Viện Số · Core Operate
                </span>
              </div>
            </a>
          </div>

          {/* Desktop Primary Navigation Landmark (Single-row, no multi-row wrap) */}
          <nav
            aria-label="Primary navigation"
            className="openlibrary-desktop-nav"
            style={{
              display: 'flex',
              flexDirection: 'row',
              alignItems: 'center',
              gap: tokens.spacing.xs,
              flexWrap: 'nowrap',
            }}
          >
            {coreNavigationItems.map((item) => {
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
                    color: isActive ? tokens.colors.primary : tokens.colors.textSecondary,
                    backgroundColor: isActive ? tokens.colors.surfaceElevated : 'transparent',
                    border: `1px solid ${isActive ? tokens.colors.primary : 'transparent'}`,
                    textDecoration: 'none',
                    whiteSpace: 'nowrap',
                    transition: 'background-color 150ms ease, color 150ms ease',
                  }}
                >
                  <span
                    style={{
                      fontWeight: isActive
                        ? tokens.typography.fontWeights.semibold
                        : tokens.typography.fontWeights.medium,
                    }}
                  >
                    {item.labelVi}
                  </span>
                  <span
                    style={{
                      fontSize: '11px',
                      opacity: 0.75,
                      marginLeft: tokens.spacing.xs,
                      fontFamily: tokens.typography.fontFamily,
                    }}
                  >
                    ({item.label})
                  </span>
                </a>
              );
            })}

            {/* Subtle Divider between Core Operations and Editions */}
            <div
              aria-hidden="true"
              style={{
                width: '1px',
                height: '18px',
                backgroundColor: tokens.colors.border,
                margin: `0 ${tokens.spacing.xs}`,
              }}
            />

            {editionNavigationItems.map((item) => {
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
                    color: isActive ? tokens.colors.primary : tokens.colors.textSecondary,
                    backgroundColor: isActive ? tokens.colors.surfaceElevated : 'transparent',
                    border: `1px solid ${isActive ? tokens.colors.primary : 'transparent'}`,
                    textDecoration: 'none',
                    whiteSpace: 'nowrap',
                    transition: 'background-color 150ms ease, color 150ms ease',
                  }}
                >
                  <span
                    style={{
                      fontWeight: isActive
                        ? tokens.typography.fontWeights.semibold
                        : tokens.typography.fontWeights.medium,
                    }}
                  >
                    {item.labelVi}
                  </span>
                  <span
                    style={{
                      fontSize: '11px',
                      opacity: 0.75,
                      marginLeft: tokens.spacing.xs,
                      fontFamily: tokens.typography.fontFamily,
                    }}
                  >
                    ({item.label})
                  </span>
                </a>
              );
            })}
          </nav>

          {/* Right Actions: Mobile Toggle & Account / Operator Desk */}
          <div style={{ display: 'flex', alignItems: 'center', gap: tokens.spacing.sm, flexShrink: 0 }}>
            {/* Mobile menu toggle button */}
            <button
              ref={mobileToggleRef}
              type="button"
              className="openlibrary-mobile-toggle"
              aria-label="Toggle navigation menu"
              aria-controls="mobile-navigation-drawer"
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

            {/* Operator Desk Context & Quick Profile (Desktop Only) */}
            <div
              role="region"
              aria-label="Account"
              className="openlibrary-desktop-account"
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
                  flexShrink: 0,
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

              {/* Profile inspection shortcut button */}
              <button
                type="button"
                onClick={() => setIsProfileModalOpen(true)}
                title="Hồ sơ cán bộ / Operator profile"
                aria-label="Hồ sơ cán bộ / Operator Profile"
                style={{
                  padding: `4px 8px`,
                  backgroundColor: 'transparent',
                  border: `1px solid ${tokens.colors.border}`,
                  borderRadius: tokens.radius.sm,
                  color: tokens.colors.textSecondary,
                  fontSize: '11px',
                  cursor: 'pointer',
                  fontFamily: tokens.typography.fontFamily,
                  marginLeft: tokens.spacing.xs,
                }}
              >
                👤
              </button>

              {/* Password change shortcut button */}
              <button
                type="button"
                onClick={() => setIsPasswordModalOpen(true)}
                title="Đổi mật khẩu / Change password"
                aria-label="Đổi mật khẩu / Change Password"
                style={{
                  padding: `4px 8px`,
                  backgroundColor: 'transparent',
                  border: `1px solid ${tokens.colors.border}`,
                  borderRadius: tokens.radius.sm,
                  color: tokens.colors.textSecondary,
                  fontSize: '11px',
                  cursor: 'pointer',
                  fontFamily: tokens.typography.fontFamily,
                  marginLeft: tokens.spacing.xs,
                }}
              >
                🔑
              </button>
            </div>
          </div>
        </div>
      </header>

      {/* Mobile Slide-Out Navigation Drawer */}
      {isMobileMenuOpen && (
        <div
          role="presentation"
          onClick={() => setIsMobileMenuOpen(false)}
          style={{
            position: 'fixed',
            top: 0,
            left: 0,
            right: 0,
            bottom: 0,
            backgroundColor: 'rgba(18, 18, 18, 0.6)',
            zIndex: 999,
            display: 'flex',
            justifyContent: 'flex-start',
          }}
        >
          <div
            id="mobile-navigation-drawer"
            ref={mobileDrawerRef}
            role="dialog"
            aria-modal="true"
            aria-label="Mobile Navigation Menu"
            onClick={(e) => e.stopPropagation()}
            style={{
              width: '85%',
              maxWidth: '360px',
              height: '100%',
              backgroundColor: tokens.colors.surface,
              boxShadow: '4px 0 24px rgba(0, 0, 0, 0.15)',
              display: 'flex',
              flexDirection: 'column',
              boxSizing: 'border-box',
            }}
          >
            {/* Drawer Header */}
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                padding: tokens.spacing.lg,
                borderBottom: `1px solid ${tokens.colors.border}`,
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: tokens.spacing.sm }}>
                <div
                  style={{
                    width: '28px',
                    height: '28px',
                    borderRadius: tokens.radius.md,
                    backgroundColor: tokens.colors.primary,
                    color: tokens.colors.primaryContrastText,
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    fontWeight: tokens.typography.fontWeights.bold,
                    fontSize: tokens.typography.fontSizes.sm,
                  }}
                >
                  OL
                </div>
                <span
                  style={{
                    fontFamily: tokens.typography.fontFamily,
                    fontSize: tokens.typography.fontSizes.md,
                    fontWeight: tokens.typography.fontWeights.bold,
                    color: tokens.colors.textPrimary,
                  }}
                >
                  Danh Mục (Menu)
                </span>
              </div>
              <button
                type="button"
                aria-label="Đóng menu / Close menu"
                onClick={() => {
                  setIsMobileMenuOpen(false);
                  mobileToggleRef.current?.focus();
                }}
                style={{
                  background: 'none',
                  border: 'none',
                  fontSize: '20px',
                  color: tokens.colors.textMuted,
                  cursor: 'pointer',
                  padding: tokens.spacing.xs,
                  lineHeight: 1,
                }}
              >
                ✕
              </button>
            </div>

            {/* Operator Desk Context Inside Drawer for Mobile */}
            <div
              role="region"
              aria-label="Account details"
              style={{
                margin: `${tokens.spacing.md} ${tokens.spacing.md} 0 ${tokens.spacing.md}`,
                padding: tokens.spacing.md,
                backgroundColor: tokens.colors.surfaceAlt,
                borderRadius: tokens.radius.md,
                border: `1px solid ${tokens.colors.borderMuted}`,
                display: 'flex',
                alignItems: 'center',
                gap: tokens.spacing.sm,
              }}
            >
              <div
                aria-hidden="true"
                style={{
                  width: '10px',
                  height: '10px',
                  borderRadius: tokens.radius.full,
                  backgroundColor: tokens.colors.status.success.color,
                  flexShrink: 0,
                }}
              />
              <div style={{ display: 'flex', flexDirection: 'column' }}>
                <span
                  style={{
                    fontFamily: tokens.typography.fontFamily,
                    fontSize: tokens.typography.fontSizes.sm,
                    fontWeight: tokens.typography.fontWeights.semibold,
                    color: tokens.colors.textPrimary,
                  }}
                >
                  {operatorDeskName}
                </span>
                <span
                  style={{
                    fontFamily: tokens.typography.fontFamily,
                    fontSize: tokens.typography.fontSizes.xs,
                    color: tokens.colors.textMuted,
                  }}
                >
                  Core Edition (Operate)
                </span>
              </div>
            </div>

            {/* Drawer Nav Items List - Categorized by Core vs Editions */}
            <nav
              aria-label="Mobile navigation"
              style={{
                flex: 1,
                overflowY: 'auto',
                padding: tokens.spacing.md,
                display: 'flex',
                flexDirection: 'column',
                gap: tokens.spacing.md,
              }}
            >
              {/* Core Operations Section */}
              <div>
                <span
                  style={{
                    display: 'block',
                    fontFamily: tokens.typography.fontFamily,
                    fontSize: '11px',
                    fontWeight: tokens.typography.fontWeights.bold,
                    color: tokens.colors.textMuted,
                    letterSpacing: '0.05em',
                    marginBottom: tokens.spacing.xs,
                    paddingLeft: tokens.spacing.xs,
                  }}
                >
                  VẬN HÀNH CỐT LÕI (CORE)
                </span>
                <div style={{ display: 'flex', flexDirection: 'column', gap: tokens.spacing.xs }}>
                  {coreNavigationItems.map((item) => {
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
                          setIsMobileMenuOpen(false);
                          mobileToggleRef.current?.focus();
                        }}
                        style={{
                          display: 'flex',
                          flexDirection: 'column',
                          justifyContent: 'center',
                          minHeight: '48px',
                          padding: `${tokens.spacing.sm} ${tokens.spacing.md}`,
                          borderRadius: tokens.radius.md,
                          backgroundColor: isActive ? tokens.colors.surfaceElevated : tokens.colors.surfaceAlt,
                          border: `1px solid ${isActive ? tokens.colors.primary : tokens.colors.borderMuted}`,
                          textDecoration: 'none',
                          transition: 'background-color 150ms ease',
                        }}
                      >
                        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                          <span
                            style={{
                              fontFamily: tokens.typography.fontFamily,
                              fontSize: tokens.typography.fontSizes.sm,
                              fontWeight: isActive
                                ? tokens.typography.fontWeights.bold
                                : tokens.typography.fontWeights.semibold,
                              color: isActive ? tokens.colors.primary : tokens.colors.textPrimary,
                            }}
                          >
                            {item.labelVi}
                          </span>
                          <span
                            style={{
                              fontSize: '11px',
                              color: tokens.colors.textMuted,
                              fontFamily: tokens.typography.fontFamily,
                            }}
                          >
                            {item.label}
                          </span>
                        </div>
                        <span
                          style={{
                            fontFamily: tokens.typography.fontFamily,
                            fontSize: tokens.typography.fontSizes.xs,
                            color: tokens.colors.textSecondary,
                            marginTop: '2px',
                            lineHeight: 1.3,
                          }}
                        >
                          {item.descriptionVi}
                        </span>
                      </a>
                    );
                  })}
                </div>
              </div>

              {/* Editions Section */}
              <div>
                <span
                  style={{
                    display: 'block',
                    fontFamily: tokens.typography.fontFamily,
                    fontSize: '11px',
                    fontWeight: tokens.typography.fontWeights.bold,
                    color: tokens.colors.textMuted,
                    letterSpacing: '0.05em',
                    marginBottom: tokens.spacing.xs,
                    paddingLeft: tokens.spacing.xs,
                  }}
                >
                  MỞ RỘNG PHÂN HỆ (EDITIONS)
                </span>
                <div style={{ display: 'flex', flexDirection: 'column', gap: tokens.spacing.xs }}>
                  {editionNavigationItems.map((item) => {
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
                          setIsMobileMenuOpen(false);
                          mobileToggleRef.current?.focus();
                        }}
                        style={{
                          display: 'flex',
                          flexDirection: 'column',
                          justifyContent: 'center',
                          minHeight: '48px',
                          padding: `${tokens.spacing.sm} ${tokens.spacing.md}`,
                          borderRadius: tokens.radius.md,
                          backgroundColor: isActive ? tokens.colors.surfaceElevated : tokens.colors.surfaceAlt,
                          border: `1px solid ${isActive ? tokens.colors.primary : tokens.colors.borderMuted}`,
                          textDecoration: 'none',
                          transition: 'background-color 150ms ease',
                        }}
                      >
                        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                          <span
                            style={{
                              fontFamily: tokens.typography.fontFamily,
                              fontSize: tokens.typography.fontSizes.sm,
                              fontWeight: isActive
                                ? tokens.typography.fontWeights.bold
                                : tokens.typography.fontWeights.semibold,
                              color: isActive ? tokens.colors.primary : tokens.colors.textPrimary,
                            }}
                          >
                            {item.labelVi}
                          </span>
                          <span
                            style={{
                              fontSize: '11px',
                              color: tokens.colors.textMuted,
                              fontFamily: tokens.typography.fontFamily,
                            }}
                          >
                            {item.label}
                          </span>
                        </div>
                        <span
                          style={{
                            fontFamily: tokens.typography.fontFamily,
                            fontSize: tokens.typography.fontSizes.xs,
                            color: tokens.colors.textSecondary,
                            marginTop: '2px',
                            lineHeight: 1.3,
                          }}
                        >
                          {item.descriptionVi}
                        </span>
                      </a>
                    );
                  })}
                </div>
              </div>
            </nav>

            {/* Drawer Footer Actions */}
            <div
              style={{
                padding: tokens.spacing.lg,
                borderTop: `1px solid ${tokens.colors.border}`,
                display: 'flex',
                flexDirection: 'column',
                gap: tokens.spacing.sm,
              }}
            >
              <button
                type="button"
                onClick={() => {
                  setIsMobileMenuOpen(false);
                  setIsProfileModalOpen(true);
                }}
                style={{
                  padding: `${tokens.buttonSpacing.md.py} ${tokens.buttonSpacing.md.px}`,
                  borderRadius: tokens.radius.md,
                  border: `1px solid ${tokens.colors.border}`,
                  backgroundColor: tokens.colors.surfaceAlt,
                  color: tokens.colors.textPrimary,
                  fontFamily: tokens.typography.fontFamily,
                  fontSize: tokens.typography.fontSizes.sm,
                  fontWeight: tokens.typography.fontWeights.medium,
                  cursor: 'pointer',
                  textAlign: 'center',
                }}
              >
                👤 Hồ Sơ Cán Bộ (Profile)
              </button>
              <button
                type="button"
                onClick={() => {
                  setIsMobileMenuOpen(false);
                  setIsPasswordModalOpen(true);
                }}
                style={{
                  padding: `${tokens.buttonSpacing.md.py} ${tokens.buttonSpacing.md.px}`,
                  borderRadius: tokens.radius.md,
                  border: `1px solid ${tokens.colors.border}`,
                  backgroundColor: tokens.colors.surfaceAlt,
                  color: tokens.colors.textPrimary,
                  fontFamily: tokens.typography.fontFamily,
                  fontSize: tokens.typography.fontSizes.sm,
                  fontWeight: tokens.typography.fontWeights.medium,
                  cursor: 'pointer',
                  textAlign: 'center',
                }}
              >
                🔑 Đổi Mật Khẩu (Change Password)
              </button>
              {onLogout && (
                <button
                  type="button"
                  onClick={() => {
                    setIsMobileMenuOpen(false);
                    onLogout();
                  }}
                  style={{
                    padding: `${tokens.buttonSpacing.md.py} ${tokens.buttonSpacing.md.px}`,
                    borderRadius: tokens.radius.md,
                    border: `1px solid ${tokens.colors.status.danger.border}`,
                    backgroundColor: tokens.colors.status.danger.bg,
                    color: tokens.colors.status.danger.color,
                    fontFamily: tokens.typography.fontFamily,
                    fontSize: tokens.typography.fontSizes.sm,
                    fontWeight: tokens.typography.fontWeights.medium,
                    cursor: 'pointer',
                    textAlign: 'center',
                  }}
                >
                  Đăng Xuất (Log Out)
                </button>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Change Password Modal */}
      <ChangePasswordModal
        isOpen={isPasswordModalOpen}
        onClose={() => setIsPasswordModalOpen(false)}
        accessToken={accessToken}
      />

      {/* Operator User Profile Modal (M-05) */}
      <UserProfileModal
        isOpen={isProfileModalOpen}
        onClose={() => setIsProfileModalOpen(false)}
        accessToken={accessToken}
      />
    </>
  );
}

export default AppHeader;
