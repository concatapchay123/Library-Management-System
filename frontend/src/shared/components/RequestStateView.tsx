import React from 'react';
import { ProblemDetailsError } from '../api/problemDetails';
import { ProblemDetailsRenderer } from './ProblemDetailsRenderer';
import { LoadingSkeleton } from './LoadingSkeleton';
import { EmptyState, EmptyStateAction } from './EmptyState';

export type RequestStatus = 'idle' | 'loading' | 'success' | 'empty' | 'error';

export interface RequestStateViewProps {
  status: RequestStatus;
  error?: ProblemDetailsError | Error | unknown;
  onRetry?: () => void | Promise<void>;
  isSafeToRetry?: boolean;
  emptyTitle?: string;
  emptyDescription?: string;
  emptyAction?: EmptyStateAction;
  loadingLines?: number;
  loadingLabel?: string;
  children?: React.ReactNode;
  className?: string;
  style?: React.CSSProperties;
}

/**
 * Common Request State View for OpenLibraryOS.
 *
 * Coordinates loading shimmer, empty explanation, safe retry error, and live children display.
 * Strictly adheres to acceptance criteria:
 * - Empty states state what is absent and the one next action when permitted.
 * - Retry controls repeat only safe documented requests.
 * - User-facing errors are concise and do not expose sensitive data.
 */
export function RequestStateView({
  status,
  error,
  onRetry,
  isSafeToRetry,
  emptyTitle = 'No Records Found',
  emptyDescription = 'There is currently no data available for this view.',
  emptyAction,
  loadingLines = 3,
  loadingLabel = 'Loading data...',
  children,
  className,
  style,
}: RequestStateViewProps) {
  if (status === 'loading') {
    return (
      <div className={className} style={style}>
        <LoadingSkeleton lines={loadingLines} ariaLabel={loadingLabel} />
      </div>
    );
  }

  if (status === 'empty') {
    return (
      <div className={className} style={style}>
        <EmptyState
          title={emptyTitle}
          description={emptyDescription}
          action={emptyAction}
        />
      </div>
    );
  }

  if (status === 'error') {
    const safeRetry =
      isSafeToRetry ?? (error instanceof ProblemDetailsError ? error.isSafeToRetry : false);

    return (
      <div className={className} style={style}>
        <ProblemDetailsRenderer
          error={error}
          onRetry={onRetry}
          isSafeToRetry={safeRetry}
        />
      </div>
    );
  }

  // Idle or success states render child content
  return <>{children}</>;
}

export default RequestStateView;
