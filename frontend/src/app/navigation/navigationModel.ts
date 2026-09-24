export interface NavigationItem {
  id: string;
  label: string;
  href: string;
  description: string;
}

/**
 * ARCHITECTURE INVARIANT:
 * Navigation links describe available product workspaces using human-readable product language.
 * Navigation visibility is strictly decoupled from authorization:
 * - Hiding or displaying a navigation link MUST NEVER be treated as an access control or security boundary.
 * - All authorization, role-based access control (RBAC), and tenant boundaries are enforced
 *   authoritatively by the backend domain/application services and database policies.
 */
export const navigationItems: readonly NavigationItem[] = [
  {
    id: 'catalog',
    label: 'Catalog',
    href: '#/catalog',
    description: 'Search bibliographic records, books, authors, and availability.',
  },
  {
    id: 'circulation',
    label: 'Circulation',
    href: '#/circulation',
    description: 'Circulation desk operations: checkout, check-in, loans, and returns.',
  },
  {
    id: 'inventory',
    label: 'Inventory',
    href: '#/inventory',
    description: 'Physical copies, shelf locations, and barcode status management.',
  },
  {
    id: 'members',
    label: 'Members',
    href: '#/members',
    description: 'Borrower records, student profiles, and library membership accounts.',
  },
  {
    id: 'reservations',
    label: 'Reservations',
    href: '#/reservations',
    description: 'Hold queue priorities, reservation allocations, and pickup notifications.',
  },
];
