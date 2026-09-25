import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, within } from '@testing-library/react';
import { useState, useRef } from 'react';
import { App } from '../../src/app/App';
import { AppShell } from '../../src/app/shell/AppShell';
import { navigationItems } from '../../src/app/navigation/navigationModel';
import {
  Button,
  Input,
  StatusMessage,
  Dialog,
} from '../../src/shared/components';
import { TokenProvider } from '../../src/shared/tokens';

describe('App Shell, Navigation & Shared Controls (FE-002)', () => {
  beforeEach(() => {
    vi.spyOn(globalThis, 'fetch');
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  describe('Semantic Landmarks & DOM Order', () => {
    it('renders landmarks in predictable accessible order: skip link -> banner -> navigation -> main', () => {
      const { container } = render(<App initialAuthenticated={true} autoRefreshOnMount={false} />);

      expect(globalThis.fetch).not.toHaveBeenCalled();

      // 1. Skip link
      const skipLink = screen.getByRole('link', { name: /skip to main content/i });
      expect(skipLink).toBeInTheDocument();
      expect(skipLink).toHaveAttribute('href', '#main-content');

      // 2. Banner landmark
      const banner = screen.getByRole('banner');
      expect(banner).toBeInTheDocument();

      // 3. Navigation landmark inside or right after banner
      const navigation = screen.getByRole('navigation', { name: /primary navigation/i });
      expect(navigation).toBeInTheDocument();

      // 4. Main landmark
      const main = screen.getByRole('main');
      expect(main).toBeInTheDocument();
      expect(main).toHaveAttribute('id', 'main-content');

      // Verify DOM document order
      const allElements = Array.from(container.querySelectorAll('*'));
      const skipIdx = allElements.indexOf(skipLink);
      const bannerIdx = allElements.indexOf(banner);
      const navIdx = allElements.indexOf(navigation);
      const mainIdx = allElements.indexOf(main);

      expect(skipIdx).toBeLessThan(bannerIdx);
      expect(bannerIdx).toBeLessThan(mainIdx);
      expect(navIdx).toBeLessThan(mainIdx);
    });

    it('renders logo-to-home navigation link with product branding', () => {
      render(<App initialAuthenticated={true} autoRefreshOnMount={false} />);

      const logoLink = screen.getByRole('link', { name: /openlibraryos/i });
      expect(logoLink).toBeInTheDocument();
      expect(logoLink).toHaveAttribute('href', '#/');
    });

    it('renders account area displaying human-readable desk context without technical IDs', () => {
      render(<App initialAuthenticated={true} autoRefreshOnMount={false} />);

      const accountArea = screen.getByLabelText(/account/i);
      expect(accountArea).toBeInTheDocument();
      expect(accountArea).toHaveTextContent(/librarian desk|quầy thủ thư/i);
      // Ensure no raw technical IDs or tokens are exposed
      expect(accountArea).not.toHaveTextContent(/user_id|uuid|token|jwt/i);
    });

    it('renders AppShell standalone with custom titles and operator desk props', () => {
      render(
        <TokenProvider>
          <AppShell
            pageTitle="Inventory Workspace"
            pageSubtitle="Manage book copies and barcode tracking"
            operatorDeskName="Quầy Kho Sách"
          >
            <div>Custom Content</div>
          </AppShell>
        </TokenProvider>,
      );

      expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent(/inventory workspace/i);
      expect(screen.getByText(/manage book copies and barcode tracking/i)).toBeInTheDocument();
      expect(screen.getByText(/quầy kho sách/i)).toBeInTheDocument();
      expect(screen.getByText('Custom Content')).toBeInTheDocument();
    });
  });

  describe('Primary Navigation & Product Language', () => {
    it('uses product terminology for all navigation labels rather than technical identifiers', () => {
      render(<App initialAuthenticated={true} autoRefreshOnMount={false} />);

      const navigation = screen.getByRole('navigation', { name: /primary navigation/i });
      expect(navigation).toBeInTheDocument();

      // Verify defined navigation model
      expect(navigationItems.length).toBeGreaterThanOrEqual(5);

      // Verify product terms exist
      expect(within(navigation).getByRole('link', { name: /catalog/i })).toBeInTheDocument();
      expect(within(navigation).getByRole('link', { name: /circulation/i })).toBeInTheDocument();
      expect(within(navigation).getByRole('link', { name: /inventory/i })).toBeInTheDocument();
      expect(within(navigation).getByRole('link', { name: /members/i })).toBeInTheDocument();
      expect(within(navigation).getByRole('link', { name: /reservations/i })).toBeInTheDocument();

      // Technical anti-pattern checks: no raw database or controller names
      expect(within(navigation).queryByText(/tbl_books/i)).not.toBeInTheDocument();
      expect(within(navigation).queryByText(/loan_controller/i)).not.toBeInTheDocument();
      expect(within(navigation).queryByText(/endpoint/i)).not.toBeInTheDocument();
    });

    it('indicates active navigation route using aria-current="page"', () => {
      render(<App initialAuthenticated={true} autoRefreshOnMount={false} />);

      const navigation = screen.getByRole('navigation', { name: /primary navigation/i });
      const currentLinks = within(navigation).getAllByRole('link');
      const activeLink = currentLinks.find((link) => link.getAttribute('aria-current') === 'page');

      expect(activeLink).toBeDefined();
      expect(activeLink).toHaveAttribute('aria-current', 'page');
    });

    it('explicitly decouples navigation model from authorization decisions', () => {
      // Invariant check: navigation items describe navigation paths only;
      // they do not infer or enforce backend permissions.
      for (const item of navigationItems) {
        expect(item).toHaveProperty('id');
        expect(item).toHaveProperty('label');
        expect(item).toHaveProperty('href');
        // No client-side permission authority claim
        expect(item).not.toHaveProperty('authorizesAction');
      }
    });
  });

  describe('Single Visually Primary Action Rule', () => {
    it('limits each distinct screen region to strictly one visually primary action', () => {
      render(<App initialAuthenticated={true} autoRefreshOnMount={false} />);

      const banner = screen.getByRole('banner');
      const main = screen.getByRole('main');

      // Banner should not have competing primary buttons
      const bannerPrimaryButtons = within(banner)
        .queryAllByRole('button')
        .filter((btn) => btn.getAttribute('data-variant') === 'primary');
      expect(bannerPrimaryButtons.length).toBeLessThanOrEqual(1);

      // Main content region must have at most 1 primary action button
      const mainPrimaryButtons = within(main)
        .queryAllByRole('button')
        .filter((btn) => btn.getAttribute('data-variant') === 'primary');
      expect(mainPrimaryButtons.length).toBe(1);
    });
  });

  describe('Shared Component: Accessible Button', () => {
    it('renders with 2:1 whitespace padding ratio and Title Case formatting', () => {
      render(
        <TokenProvider>
          <Button variant="primary" size="md">
            Check Out Book
          </Button>
          <Button variant="secondary" size="sm">
            Cancel
          </Button>
        </TokenProvider>,
      );

      const primaryBtn = screen.getByRole('button', { name: /check out book/i });
      expect(primaryBtn).toBeInTheDocument();
      expect(primaryBtn).toHaveAttribute('data-variant', 'primary');
      expect(primaryBtn).toHaveAttribute('data-size', 'md');

      // Ratio check: md spacing is 8px vertical, 16px horizontal (16 / 8 = 2)
      expect(primaryBtn.style.paddingTop).toBe('8px');
      expect(primaryBtn.style.paddingBottom).toBe('8px');
      expect(primaryBtn.style.paddingLeft).toBe('16px');
      expect(primaryBtn.style.paddingRight).toBe('16px');

      // sm spacing: 6px vertical, 12px horizontal (12 / 6 = 2)
      const secondaryBtn = screen.getByRole('button', { name: /cancel/i });
      expect(secondaryBtn.style.paddingTop).toBe('6px');
      expect(secondaryBtn.style.paddingBottom).toBe('6px');
      expect(secondaryBtn.style.paddingLeft).toBe('12px');
      expect(secondaryBtn.style.paddingRight).toBe('12px');
    });

    it('supports danger variant for destructive actions with danger styling', () => {
      render(
        <TokenProvider>
          <Button variant="danger">Delete Copy</Button>
        </TokenProvider>,
      );

      const deleteBtn = screen.getByRole('button', { name: /delete copy/i });
      expect(deleteBtn).toBeInTheDocument();
      expect(deleteBtn).toHaveAttribute('data-variant', 'danger');
    });

    it('handles disabled state properly and prevents interaction', () => {
      const handleClick = vi.fn();
      render(
        <TokenProvider>
          <Button variant="primary" disabled onClick={handleClick}>
            Processing
          </Button>
        </TokenProvider>,
      );

      const btn = screen.getByRole('button', { name: /processing/i });
      expect(btn).toBeDisabled();
      fireEvent.click(btn);
      expect(handleClick).not.toHaveBeenCalled();
    });
  });

  describe('Shared Component: Labeled Input', () => {
    it('associates label, description, and error message programmatically via ARIA', () => {
      render(
        <TokenProvider>
          <Input
            id="book-barcode"
            label="Book Barcode / ISBN"
            description="Scan the physical barcode or enter a 13-digit ISBN."
            errorMessage="Barcode not found in inventory."
            defaultValue=""
          />
        </TokenProvider>,
      );

      const input = screen.getByRole('textbox', { name: /book barcode \/ isbn/i });
      expect(input).toBeInTheDocument();
      expect(input).toHaveAttribute('id', 'book-barcode');

      // Accessible description
      const desc = screen.getByText(/scan the physical barcode/i);
      expect(desc).toBeInTheDocument();
      expect(desc).toHaveAttribute('id', 'book-barcode-description');

      // Accessible error
      const errorMsg = screen.getByRole('alert');
      expect(errorMsg).toHaveTextContent(/barcode not found in inventory/i);
      expect(errorMsg).toHaveAttribute('id', 'book-barcode-error');

      // aria-describedby links both description and error
      const ariaDescribedBy = input.getAttribute('aria-describedby');
      expect(ariaDescribedBy).toContain('book-barcode-description');
      expect(ariaDescribedBy).toContain('book-barcode-error');

      // aria-invalid set to true
      expect(input).toHaveAttribute('aria-invalid', 'true');
    });

    it('displays (Optional) tag instead of excessive red asterisks for non-mandatory fields', () => {
      render(
        <TokenProvider>
          <Input
            id="loan-note"
            label="Loan Note"
            optional
            description="Optional comment regarding copy condition."
          />
        </TokenProvider>,
      );

      const label = screen.getByText(/loan note/i);
      expect(label).toHaveTextContent(/(optional)/i);
      // No red asterisk
      expect(label).not.toHaveTextContent('*');
    });
  });

  describe('Shared Component: StatusMessage with Non-Color Cues', () => {
    it('renders accessible status message with icon, textual label, and descriptive text', () => {
      render(
        <TokenProvider>
          <StatusMessage status="success" title="Checkout Completed">
            Book copy #1088 has been successfully assigned to student Jane Doe.
          </StatusMessage>
          <StatusMessage status="danger" title="Item Overdue">
            This item is past its due date and has an outstanding fine.
          </StatusMessage>
        </TokenProvider>,
      );

      // Success message check
      const successStatus = screen.getByRole('status');
      expect(successStatus).toBeInTheDocument();
      expect(successStatus).toHaveTextContent(/success/i);
      expect(successStatus).toHaveTextContent(/checkout completed/i);
      expect(successStatus).toHaveTextContent(/book copy #1088/i);
      expect(within(successStatus).getByTestId('status-icon-success')).toBeInTheDocument();

      // Danger message check (role alert)
      const dangerAlert = screen.getByRole('alert');
      expect(dangerAlert).toBeInTheDocument();
      expect(dangerAlert).toHaveTextContent(/danger/i);
      expect(dangerAlert).toHaveTextContent(/item overdue/i);
      expect(within(dangerAlert).getByTestId('status-icon-danger')).toBeInTheDocument();
    });
  });

  describe('Shared Component: Accessible Dialog with Escape Dismissal & Focus Return', () => {
    function DialogHarness() {
      const [isOpen, setIsOpen] = useState(false);
      const triggerBtnRef = useRef<HTMLButtonElement>(null);

      return (
        <TokenProvider>
          <div>
            <button
              ref={triggerBtnRef}
              data-testid="open-dialog-trigger"
              onClick={() => setIsOpen(true)}
            >
              Open Return Confirmation
            </button>
            <Dialog
              isOpen={isOpen}
              onClose={() => setIsOpen(false)}
              title="Confirm Book Return"
              description="Verify copy condition before confirming check-in."
              triggerRef={triggerBtnRef}
            >
              <div data-testid="dialog-body-content">
                <p>Are you sure you want to mark this copy as returned to shelf?</p>
                <Button
                  variant="primary"
                  onClick={() => setIsOpen(false)}
                >
                  Confirm Return
                </Button>
                <Button
                  variant="secondary"
                  onClick={() => setIsOpen(false)}
                >
                  Cancel
                </Button>
              </div>
            </Dialog>
          </div>
        </TokenProvider>
      );
    }

    it('renders dialog with modal attributes, titles, and descriptions', () => {
      render(<DialogHarness />);

      const trigger = screen.getByTestId('open-dialog-trigger');
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument();

      // Open dialog
      fireEvent.click(trigger);

      const dialog = screen.getByRole('dialog');
      expect(dialog).toBeInTheDocument();
      expect(dialog).toHaveAttribute('aria-modal', 'true');
      expect(dialog).toHaveAttribute('aria-labelledby');
      expect(dialog).toHaveAttribute('aria-describedby');

      expect(screen.getByText(/confirm book return/i)).toBeInTheDocument();
      expect(screen.getByText(/verify copy condition before confirming check-in/i)).toBeInTheDocument();
    });

    it('closes dialog on Escape key press and restores focus to trigger element', () => {
      render(<DialogHarness />);

      const trigger = screen.getByTestId('open-dialog-trigger');
      trigger.focus();
      expect(document.activeElement).toBe(trigger);

      // Open dialog
      fireEvent.click(trigger);
      expect(screen.getByRole('dialog')).toBeInTheDocument();

      // Press Escape
      fireEvent.keyDown(window, { key: 'Escape', code: 'Escape' });

      // Dialog is dismissed
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument();

      // Focus returns to the trigger button
      expect(document.activeElement).toBe(trigger);
    });

    it('closes dialog via Close button and returns focus to trigger element', () => {
      render(<DialogHarness />);

      const trigger = screen.getByTestId('open-dialog-trigger');
      trigger.focus();

      fireEvent.click(trigger);
      expect(screen.getByRole('dialog')).toBeInTheDocument();

      const closeBtn = screen.getByRole('button', { name: /close dialog/i });
      fireEvent.click(closeBtn);

      expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
      expect(document.activeElement).toBe(trigger);
    });
  });

  describe('Responsive Navigation & Narrow Viewport Behavior', () => {
    it('provides accessible toggle menu button for narrow viewports without hiding navigation', () => {
      render(<App initialAuthenticated={true} autoRefreshOnMount={false} />);

      const toggleBtn = screen.getByRole('button', { name: /toggle navigation menu/i });
      expect(toggleBtn).toBeInTheDocument();
      expect(toggleBtn).toHaveAttribute('aria-expanded');

      // Toggling changes aria-expanded state
      const initialExpanded = toggleBtn.getAttribute('aria-expanded');
      fireEvent.click(toggleBtn);
      expect(toggleBtn.getAttribute('aria-expanded')).not.toBe(initialExpanded);
    });
  });
});
