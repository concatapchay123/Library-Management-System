import { useState, useRef, useEffect } from 'react';
import { TokenProvider, useTokens } from '../shared/tokens';
import { AppShell } from './shell/AppShell';
import { Button, Input, StatusMessage, Dialog } from '../shared/components';
import { SessionProvider, ProtectedRoute, LoginForm } from '../features/auth';
import { CatalogSearch } from '../features/catalog';

export interface AppProps {
  initialAuthenticated?: boolean;
  autoRefreshOnMount?: boolean;
}

function OperateModeDesk() {
  const tokens = useTokens();
  const [activeTab, setActiveTab] = useState(() => {
    if (typeof window !== 'undefined' && window.location.hash) {
      const hash = window.location.hash.replace(/^#\/?/, '');
      if (hash === 'catalog') return 'catalog';
    }
    return 'circulation';
  });
  const [isDialogOpen, setIsDialogOpen] = useState(false);
  const [barcode, setBarcode] = useState('');
  const [borrowerId, setBorrowerId] = useState('');
  const [note, setNote] = useState('');

  const dialogTriggerRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    function handleHashChange() {
      if (typeof window !== 'undefined' && window.location.hash) {
        const hash = window.location.hash.replace(/^#\/?/, '');
        if (hash === 'catalog' || hash === 'circulation') {
          setActiveTab(hash);
        }
      }
    }
    window.addEventListener('hashchange', handleHashChange);
    return () => window.removeEventListener('hashchange', handleHashChange);
  }, []);

  const isCatalog = activeTab === 'catalog';

  return (
    <AppShell
      pageTitle={isCatalog ? 'Bibliographic Catalog' : 'OpenLibraryOS — Operate Mode'}
      pageSubtitle={
        isCatalog
          ? 'Search works, authors, and bibliographic records across the organization'
          : 'Low-Cognitive-Overhead Library Operations'
      }
      activeNavigationId={activeTab}
      onNavigate={(id) => setActiveTab(id)}
      operatorDeskName="Librarian Desk"
    >
      {isCatalog ? (
        <CatalogSearch />
      ) : (
        <div
        style={{
          display: 'flex',
          flexDirection: 'column',
          gap: tokens.spacing.semantic.groupToGroup,
          maxWidth: '680px',
        }}
      >
        {/* Status Cue Landmark */}
        <StatusMessage status="success" title="Operational Status: Ready">
          Offline foundation verified. Circulation desk initialized for high-throughput scanning and
          patron service.
        </StatusMessage>

        {/* Operating Card */}
        <div
          style={{
            backgroundColor: tokens.colors.surfaceAlt,
            borderRadius: tokens.radius.xl,
            border: `1px solid ${tokens.colors.border}`,
            padding: tokens.spacing.xl,
            boxSizing: 'border-box',
          }}
        >
          <div style={{ marginBottom: tokens.spacing.lg }}>
            <h2
              style={{
                margin: 0,
                fontFamily: tokens.typography.fontFamily,
                fontSize: tokens.typography.fontSizes.xl,
                fontWeight: tokens.typography.fontWeights.bold,
                color: tokens.colors.textPrimary,
              }}
            >
              Rapid Circulation Desk
            </h2>
            <p
              style={{
                margin: 0,
                marginTop: tokens.spacing.xs,
                fontFamily: tokens.typography.fontFamily,
                fontSize: tokens.typography.fontSizes.sm,
                color: tokens.colors.textSecondary,
              }}
            >
              Single-column input optimized for barcode scanners and keyboard traversal.
            </p>
          </div>

          <form
            onSubmit={(e) => {
              e.preventDefault();
            }}
            style={{
              display: 'flex',
              flexDirection: 'column',
              gap: tokens.spacing.semantic.groupToGroup,
            }}
          >
            {/* Field 1: Book Barcode / ISBN */}
            <Input
              id="book-barcode"
              label="Book Barcode / ISBN"
              description="Scan the physical barcode or enter a 13-digit ISBN."
              placeholder="e.g. 978-0-12345-0001 or scan barcode..."
              value={barcode}
              onChange={(e) => setBarcode(e.target.value)}
            />

            {/* Field 2: Borrower ID */}
            <Input
              id="borrower-id"
              label="Borrower Card / Student ID"
              description="Scan borrower barcode or enter student matriculation number."
              placeholder="e.g. STU-2026-8819..."
              value={borrowerId}
              onChange={(e) => setBorrowerId(e.target.value)}
            />

            {/* Field 3: Note (Optional) */}
            <Input
              id="desk-loan-note"
              label="Loan Condition Note"
              optional
              description="Record any pre-existing cover or spine defects."
              placeholder="e.g. Minor wear on spine cover..."
              value={note}
              onChange={(e) => setNote(e.target.value)}
            />

            {/* Action Buttons: strictly 1 primary action */}
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: tokens.spacing.md,
                marginTop: tokens.spacing.sm,
                paddingTop: tokens.spacing.md,
                borderTop: `1px solid ${tokens.colors.borderMuted}`,
                flexWrap: 'wrap',
              }}
            >
              {/* The ONLY visually primary action in this region */}
              <Button
                type="submit"
                variant="primary"
                size="md"
              >
                Check Out Book
              </Button>

              {/* Secondary Action */}
              <Button
                ref={dialogTriggerRef}
                type="button"
                variant="secondary"
                size="md"
                onClick={() => setIsDialogOpen(true)}
              >
                Confirm Quick Return
              </Button>
            </div>
          </form>
        </div>

        {/* Modal Dialog for Return Confirmation */}
        <Dialog
          isOpen={isDialogOpen}
          onClose={() => setIsDialogOpen(false)}
          title="Confirm Book Return"
          description="Verify physical condition before accepting item back into inventory."
          triggerRef={dialogTriggerRef}
        >
          <div style={{ display: 'flex', flexDirection: 'column', gap: tokens.spacing.md }}>
            <p
              style={{
                margin: 0,
                fontFamily: tokens.typography.fontFamily,
                fontSize: tokens.typography.fontSizes.sm,
                color: tokens.colors.textSecondary,
                lineHeight: tokens.typography.lineHeights.normal,
              }}
            >
              Please verify that all pages and barcodes are intact. Marking as returned will update
              the copy status to available on shelf.
            </p>
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'flex-end',
                gap: tokens.spacing.md,
                marginTop: tokens.spacing.sm,
              }}
            >
              <Button
                variant="secondary"
                size="sm"
                onClick={() => setIsDialogOpen(false)}
              >
                Cancel
              </Button>
              {/* Only 1 primary action inside dialog */}
              <Button
                variant="primary"
                size="sm"
                onClick={() => setIsDialogOpen(false)}
              >
                Confirm Return
              </Button>
            </div>
          </div>
        </Dialog>
      </div>
      )}
    </AppShell>
  );
}

export function App({
  initialAuthenticated = true,
  autoRefreshOnMount = false,
}: AppProps = {}) {
  const initialToken = initialAuthenticated ? 'in-memory-operate-session' : null;

  return (
    <TokenProvider>
      <SessionProvider
        initialAccessToken={initialToken}
        autoRefreshOnMount={autoRefreshOnMount}
      >
        <ProtectedRoute fallback={<LoginForm />}>
          <OperateModeDesk />
        </ProtectedRoute>
      </SessionProvider>
    </TokenProvider>
  );
}

export default App;
