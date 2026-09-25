import React from 'react';
import {
  PublicLibraryMember,
  PublicLibraryMembershipPlan,
  PublicLibrarySubscription,
  PublicLibraryFine,
  PublicLibraryInvoice,
  PublicLibraryPayment,
} from '../../shared/api';

export type PublicLibraryTab = 'memberships' | 'fines' | 'invoices' | 'payments';

export interface PublicLibraryWorkspaceProps {
  initialTab?: PublicLibraryTab;
  className?: string;
  style?: React.CSSProperties;
}

export interface EditionUnavailableStateProps {
  detail?: string;
  className?: string;
  style?: React.CSSProperties;
}

export interface MembershipSummaryViewProps {
  members: PublicLibraryMember[];
  plans: PublicLibraryMembershipPlan[];
  subscriptions: PublicLibrarySubscription[];
  isLoading: boolean;
  onRefresh: () => void;
  onError: (error: unknown) => void;
}

export interface FinesViewProps {
  fines: PublicLibraryFine[];
  isLoading: boolean;
  onRefresh: () => void;
  onError: (error: unknown) => void;
}

export interface InvoicesViewProps {
  invoices: PublicLibraryInvoice[];
  isLoading: boolean;
  onRefresh: () => void;
  onError: (error: unknown) => void;
}

export interface PaymentsViewProps {
  payments: PublicLibraryPayment[];
  isLoading: boolean;
  onRefresh: () => void;
  onError: (error: unknown) => void;
}
