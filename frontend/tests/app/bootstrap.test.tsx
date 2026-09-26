import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { App } from '../../src/app/App';
import {
  TokenProvider,
  useTokens,
  calcNestedRadius,
  defaultTokens,
} from '../../src/shared/tokens';

describe('Frontend Bootstrap & Token Layer (FE-001)', () => {
  beforeEach(() => {
    vi.spyOn(globalThis, 'fetch');
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  describe('Root Application Bootstrap', () => {
    it('renders the root application cleanly in operate mode without network requests when authenticated', () => {
      render(<App initialAuthenticated={true} autoRefreshOnMount={false} />);

      // Acceptance criterion: The application can render without a network request
      expect(globalThis.fetch).not.toHaveBeenCalled();

      // Verify operate-mode heading and landmark presence
      const heading = screen.getByRole('heading', { level: 1 });
      expect(heading).toBeInTheDocument();
      expect(heading).toHaveTextContent(/OpenLibraryOS/i);
      expect(heading).toHaveTextContent(/Operate Mode/i);

      // Verify main landmark
      const mainLandmark = screen.getByRole('main');
      expect(mainLandmark).toBeInTheDocument();
    });

    it('renders durable Operate-mode status and guidance indicators when authenticated', () => {
      render(<App initialAuthenticated={true} autoRefreshOnMount={false} />);

      expect(
        screen.getByText(/Low-Cognitive-Overhead Library Operations/i),
      ).toBeInTheDocument();
      expect(
        screen.getByRole('heading', { level: 2, name: /circulation desk/i }),
      ).toBeInTheDocument();
      // Does NOT fabricate unevidenced "Ready" status
      expect(
        screen.queryByText(/Operational Status: Ready/i),
      ).not.toBeInTheDocument();
    });

    it('does not grant authenticated operate session when ?demo=1 query string is in URL', () => {
      window.history.pushState({}, '', '/?demo=1');

      render(<App autoRefreshOnMount={false} />);

      // Must show login form, NOT circulation desk
      expect(screen.getByRole('heading', { level: 2, name: /sign in to openlibraryos/i })).toBeInTheDocument();
      expect(screen.queryByTestId('circulation-desk')).not.toBeInTheDocument();

      window.history.pushState({}, '', '/');
    });

    it('defaults to unauthenticated entrypoint and triggers auto-refresh on mount (H-01)', async () => {
      vi.mocked(globalThis.fetch).mockResolvedValueOnce({
        ok: false,
        status: 401,
        headers: new Headers({ 'Content-Type': 'application/problem+json' }),
        json: async () => ({ status: 401 }),
      } as Response);

      render(<App />);
      await waitFor(() => {
        expect(globalThis.fetch).toHaveBeenCalledWith(
          '/api/v1/auth/refresh',
          expect.objectContaining({ method: 'POST', credentials: 'same-origin' }),
        );
      });
      await waitFor(() => {
        expect(screen.getByRole('heading', { level: 2, name: /sign in|log in/i })).toBeInTheDocument();
      });
      // Verifies silent refresh failure does NOT display a false credential error alert banner (P2-01)
      expect(screen.queryByRole('alert')).not.toBeInTheDocument();
    });
  });

  describe('Design Token System', () => {
    function TokenInspector() {
      const tokens = useTokens();
      return (
        <div data-testid="token-inspector">
          <span data-testid="spacing-xs">{tokens.spacing.xs}</span>
          <span data-testid="spacing-sm">{tokens.spacing.sm}</span>
          <span data-testid="spacing-md">{tokens.spacing.md}</span>
          <span data-testid="spacing-lg">{tokens.spacing.lg}</span>
          <span data-testid="spacing-xl">{tokens.spacing.xl}</span>
          <span data-testid="spacing-2xl">{tokens.spacing['2xl']}</span>
          <span data-testid="semantic-label-to-input">
            {tokens.spacing.semantic.labelToInput}
          </span>
          <span data-testid="semantic-group-to-group">
            {tokens.spacing.semantic.groupToGroup}
          </span>
          <span data-testid="semantic-form-to-submit">
            {tokens.spacing.semantic.formToSubmit}
          </span>
          <span data-testid="color-surface">{tokens.colors.surface}</span>
          <span data-testid="color-text-primary">
            {tokens.colors.textPrimary}
          </span>
          <span data-testid="status-success-label">
            {tokens.colors.status.success.label}
          </span>
          <span data-testid="status-success-icon">{tokens.colors.status.success.icon}</span>
          <span data-testid="status-danger-label">
            {tokens.colors.status.danger.label}
          </span>
          <span data-testid="status-danger-icon">{tokens.colors.status.danger.icon}</span>
          <span data-testid="focus-outline">{tokens.focus.cssString}</span>
        </div>
      );
    }

    it('provides spacing tokens adhering to semantic Gestalt progression', () => {
      render(
        <TokenProvider>
          <TokenInspector />
        </TokenProvider>,
      );

      expect(screen.getByTestId('spacing-xs')).toHaveTextContent('4px');
      expect(screen.getByTestId('spacing-sm')).toHaveTextContent('8px');
      expect(screen.getByTestId('spacing-md')).toHaveTextContent('12px');
      expect(screen.getByTestId('spacing-lg')).toHaveTextContent('16px');
      expect(screen.getByTestId('spacing-xl')).toHaveTextContent('24px');
      expect(screen.getByTestId('spacing-2xl')).toHaveTextContent('32px');

      // Semantic spacing invariants
      expect(screen.getByTestId('semantic-label-to-input')).toHaveTextContent(
        '12px',
      );
      expect(screen.getByTestId('semantic-group-to-group')).toHaveTextContent(
        '24px',
      );
      expect(screen.getByTestId('semantic-form-to-submit')).toHaveTextContent(
        '32px',
      );
    });

    it('strictly forbids pure black (#000000) and pure white (#ffffff) to prevent eye strain', () => {
      render(
        <TokenProvider>
          <TokenInspector />
        </TokenProvider>,
      );

      const surface = screen.getByTestId('color-surface').textContent;
      const textPrimary = screen.getByTestId('color-text-primary').textContent;

      expect(surface?.toLowerCase()).not.toBe('#ffffff');
      expect(textPrimary?.toLowerCase()).not.toBe('#000000');
    });

    it('enforces non-color cues for all status states (combining icons and text labels)', () => {
      render(
        <TokenProvider>
          <TokenInspector />
        </TokenProvider>,
      );

      expect(screen.getByTestId('status-success-label')).toHaveTextContent(
        'Success',
      );
      expect(screen.getByTestId('status-success-icon')).not.toBe('');

      expect(screen.getByTestId('status-danger-label')).toHaveTextContent(
        'Danger',
      );
      expect(screen.getByTestId('status-danger-icon')).not.toBe('');
    });

    it('provides high-contrast visible keyboard focus token', () => {
      render(
        <TokenProvider>
          <TokenInspector />
        </TokenProvider>,
      );

      const focusOutline = screen.getByTestId('focus-outline').textContent;
      expect(focusOutline).toContain('2px solid');
      expect(defaultTokens.focus.outlineWidth).toBe('2px');
      expect(defaultTokens.focus.outlineOffset).toBe('2px');
    });

    it('maintains a 2:1 horizontal to vertical button whitespace ratio', () => {
      const { sm, md, lg } = defaultTokens.buttonSpacing;

      // sm: 6px vertical, 12px horizontal -> 12 / 6 = 2
      expect(parseInt(sm.px, 10)).toBe(2 * parseInt(sm.py, 10));

      // md: 8px vertical, 16px horizontal -> 16 / 8 = 2
      expect(parseInt(md.px, 10)).toBe(2 * parseInt(md.py, 10));

      // lg: 12px vertical, 24px horizontal -> 24 / 12 = 2
      expect(parseInt(lg.px, 10)).toBe(2 * parseInt(lg.py, 10));
    });

    it('implements the nested border radius formula: R_inner = max(0, R_outer - Padding)', () => {
      // Outer 16px, padding 8px -> inner 8px
      expect(calcNestedRadius(16, 8)).toBe(8);

      // Outer 12px, padding 4px -> inner 8px
      expect(calcNestedRadius(12, 4)).toBe(8);

      // Outer 8px, padding 12px -> inner 0px (no negative radius)
      expect(calcNestedRadius(8, 12)).toBe(0);
    });

    it('injects CSS custom properties into container element', () => {
      const { container } = render(
        <TokenProvider>
          <div>Child Content</div>
        </TokenProvider>,
      );

      const rootWrapper = container.firstElementChild as HTMLElement;
      expect(rootWrapper).toBeInTheDocument();
      expect(rootWrapper.style.getPropertyValue('--ol-spacing-md')).toBe('12px');
      expect(rootWrapper.style.getPropertyValue('--ol-color-surface')).toBe(
        defaultTokens.colors.surface,
      );
      expect(rootWrapper.style.getPropertyValue('--ol-focus-outline')).toBe(
        defaultTokens.focus.cssString,
      );
    });
  });
});
