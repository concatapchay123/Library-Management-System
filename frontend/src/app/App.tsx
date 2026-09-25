import { useState, useEffect } from 'react';
import { TokenProvider } from '../shared/tokens';
import { AppShell } from './shell/AppShell';
import { SessionProvider, ProtectedRoute, LoginForm } from '../features/auth';
import { CatalogSearch } from '../features/catalog';
import { InventoryWorkspace } from '../features/inventory';
import { CirculationDesk } from '../features/circulation';
import { ReservationInbox } from '../features/inbox';
import { EducationWorkspace } from '../features/education';
import { PublicLibraryWorkspace } from '../features/public-library';

export interface AppProps {
  initialAuthenticated?: boolean;
  autoRefreshOnMount?: boolean;
}

function resolveHashTab(hashStr: string): string {
  const hash = hashStr.replace(/^#\/?/, '');
  if (hash === 'inbox') return 'reservations';
  if (hash === 'members') return 'education';
  if (
    hash === 'public-library' ||
    hash === 'fines' ||
    hash === 'invoices' ||
    hash === 'payments' ||
    hash === 'subscriptions'
  ) {
    return 'public-library';
  }
  if (
    hash === 'catalog' ||
    hash === 'circulation' ||
    hash === 'inventory' ||
    hash === 'reservations' ||
    hash === 'education'
  ) {
    return hash;
  }
  return 'circulation';
}

function OperateModeDesk() {
  const [activeTab, setActiveTab] = useState(() => {
    if (typeof window !== 'undefined' && window.location.hash) {
      return resolveHashTab(window.location.hash);
    }
    return 'circulation';
  });

  useEffect(() => {
    function handleHashChange() {
      if (typeof window !== 'undefined' && window.location.hash) {
        setActiveTab(resolveHashTab(window.location.hash));
      }
    }
    window.addEventListener('hashchange', handleHashChange);
    return () => window.removeEventListener('hashchange', handleHashChange);
  }, []);

  const isCatalog = activeTab === 'catalog';
  const isInventory = activeTab === 'inventory';
  const isReservations = activeTab === 'reservations';
  const isEducation = activeTab === 'education' || activeTab === 'members';
  const isPublicLibrary = activeTab === 'public-library';

  let pageTitle = 'OpenLibraryOS — Operate Mode';
  let pageSubtitle = 'Low-Cognitive-Overhead Library Operations';

  if (isCatalog) {
    pageTitle = 'Bibliographic Catalog';
    pageSubtitle = 'Search works, authors, and bibliographic records across the organization';
  } else if (isInventory) {
    pageTitle = 'Inventory & Copy Management';
    pageSubtitle = 'Register copies, assign physical shelf locations, and record server-validated status changes';
  } else if (isReservations) {
    pageTitle = 'Reservation Queue & Notification Inbox';
    pageSubtitle = 'Track reservation progression, hold status, and time-sensitive alerts';
  } else if (isEducation) {
    pageTitle = 'Education & Member Management';
    pageSubtitle = 'Manage student and faculty records, academic relationships, and borrower loan policies';
  } else if (isPublicLibrary) {
    pageTitle = 'Public Library & Finance';
    pageSubtitle = 'Manage member subscriptions, borrowing policies, fines, invoices, and payments';
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
      ) : isReservations ? (
        <ReservationInbox />
      ) : isEducation ? (
        <EducationWorkspace />
      ) : isPublicLibrary ? (
        <PublicLibraryWorkspace />
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
