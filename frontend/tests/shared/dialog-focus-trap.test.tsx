import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { Dialog } from '../../src/shared/components/Dialog';
import { TokenProvider } from '../../src/shared/tokens';

describe('Dialog Focus Trap Primitive (P1-05)', () => {
  it('traps Tab navigation within the dialog focusable elements', () => {
    function TestComponent() {
      return (
        <TokenProvider>
          <button data-testid="outside-button">Outside</button>
          <Dialog isOpen={true} onClose={vi.fn()} title="Test Modal">
            <input data-testid="input-1" placeholder="First field" />
            <input data-testid="input-2" placeholder="Second field" />
            <button data-testid="submit-button">Submit</button>
          </Dialog>
        </TokenProvider>
      );
    }

    render(<TestComponent />);

    const input1 = screen.getByTestId('input-1');
    const submitBtn = screen.getByTestId('submit-button');
    const closeBtn = screen.getByRole('button', { name: /close dialog|đóng/i });

    // Initial focus starts inside dialog on first input field
    expect(document.activeElement).toBe(input1);

    // Tab from submitBtn (last focusable element) wraps around to closeBtn (first focusable element)
    submitBtn.focus();
    const tabEvent = new KeyboardEvent('keydown', { key: 'Tab', bubbles: true, cancelable: true });
    window.dispatchEvent(tabEvent);
    expect(tabEvent.defaultPrevented).toBe(true);
    expect(document.activeElement).toBe(closeBtn);

    // Shift+Tab from closeBtn (first focusable element) wraps around to submitBtn (last focusable element)
    closeBtn.focus();
    const shiftTabEvent = new KeyboardEvent('keydown', { key: 'Tab', shiftKey: true, bubbles: true, cancelable: true });
    window.dispatchEvent(shiftTabEvent);
    expect(shiftTabEvent.defaultPrevented).toBe(true);
    expect(document.activeElement).toBe(submitBtn);
  });
});
