import { useState, useEffect } from 'react';
import { TokenProvider } from '../shared/tokens';
import { AppShell } from './shell/AppShell';
import { SessionProvider, ProtectedRoute, LoginForm } from '../features/auth';
import { CatalogSearch } from '../features/catalog';
import { InventoryWorkspace } from '../features/inventory';
import { CirculationDesk } from '../features/circulation';

export interface AppProps {
  initialAuthenticated?: boolean;
  autoRefreshOnMount?: boolean;
}

function OperateModeDesk() {
  const [activeTab, setActiveTab] = useState(() => {
    if (typeof window !== 'undefined' && window.location.hash) {
      const hash = window.location.hash.replace(/^#\/?/, '');
      if (hash === 'catalog' || hash === 'inventory') return hash;
    }
    return 'circulation';
  });

  useEffect(() => {
    function handleHashChange() {
      if (typeof window !== 'undefined' && window.location.hash) {
        const hash = window.location.hash.replace(/^#\/?/, '');
        if (hash === 'catalog' || hash === 'circulation' || hash === 'inventory') {
          setActiveTab(hash);
        }
      }
    }
    window.addEventListener('hashchange', handleHashChange);
    return () => window.removeEventListener('hashchange', handleHashChange);
  }, []);

  const isCatalog = activeTab === 'catalog';
  const isInventory = activeTab === 'inventory';

  let pageTitle = 'OpenLibraryOS — Operate Mode';
  let pageSubtitle = 'Low-Cognitive-Overhead Library Operations';

  if (isCatalog) {
    pageTitle = 'Bibliographic Catalog';
    pageSubtitle = 'Search works, authors, and bibliographic records across the organization';
  } else if (isInventory) {
    pageTitle = 'Inventory & Copy Management';
    pageSubtitle = 'Register copies, assign physical shelf locations, and record server-validated status changes';
  }

  return (
    <AppShell
      pageTitle={pageTitle}
      pageSubtitle={pageSubtitle}
      activeNavigationId={activeTab}
      onNavigate={(id) => setActiveTab(id)}
      operatorDeskName="Librarian Desk"
    >
      {isCatalog ? (
        <CatalogSearch />
      ) : isInventory ? (
        <InventoryWorkspace />
      ) : (
        <CirculationDesk />
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
