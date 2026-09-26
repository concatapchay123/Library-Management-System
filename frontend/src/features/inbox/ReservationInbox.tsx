import { useState, useEffect, useContext, useCallback } from 'react';
import { useTokens } from '../../shared/tokens';
import {
  Reservation,
  Notification,
  ProblemDetails,
  apiClient,
} from '../../shared/api';
import { AuthContext } from '../auth/context';
import {
  Button,
  EmptyState,
  LoadingSkeleton,
  ProblemDetailsRenderer,
  StatusMessage,
} from '../../shared/components';
import { ReservationStatusCard } from './ReservationStatusCard';
import { NotificationCard } from './NotificationCard';
import { CreateReservationModal } from './CreateReservationModal';
import { ReservationInboxProps, InboxViewFilter } from './types';

/**
 * Reservation Status and Notification Inbox Workspace (FE-008).
 *
 * Implements acceptance criteria and architectural invariants:
 * - Shows users their reservation progression and time-sensitive notifications in one concise inbox.
 * - Queue/hold progression uses backend-provided state and dates strictly without promising dates beyond server facts.
 * - Marking notifications read updates ONLY after a successful server response.
 * - Distinct, understandable copy for no-reservation and no-notification empty states.
 * - Exactly one dominant action per card: Open Relevant Record.
 * - Read-state controls are keyboard accessible and compliant with WCAG AA contrast.
 * - UI does not expose another user's data; notifications are not treated as a source of authorization truth.
 */
export function ReservationInbox({
  initialReservations,
  initialNotifications,
  onOpenRecord,
  className,
  style,
}: ReservationInboxProps) {
  const tokens = useTokens();
  const authContext = useContext(AuthContext);
  const token = authContext?.accessToken;

  const [activeFilter, setActiveFilter] = useState<InboxViewFilter>('all');

  const [reservations, setReservations] = useState<Reservation[]>(
    initialReservations ?? [],
  );
  const [notifications, setNotifications] = useState<Notification[]>(
    initialNotifications ?? [],
  );

  const [isLoading, setIsLoading] = useState(!initialReservations && !initialNotifications);
  const [loadError, setLoadError] = useState<ProblemDetails | Error | null>(null);
  const [isCreateModalOpen, setIsCreateModalOpen] = useState(false);

  const handleReservationCreated = (newReservation: Reservation) => {
    setReservations((prev) => [newReservation, ...prev]);
  };

  // Fetch reservations and notifications
  const loadInboxData = useCallback(async () => {
    setIsLoading(true);
    setLoadError(null);

    try {
      const [resResult, notifResult] = await Promise.all([
        initialReservations !== undefined
          ? Promise.resolve({ items: initialReservations, total: initialReservations.length })
          : apiClient.reservations.list(undefined, { token }),
        initialNotifications !== undefined
          ? Promise.resolve({ items: initialNotifications, total: initialNotifications.length })
          : apiClient.notifications.list(undefined, { token }),
      ]);

      setReservations(resResult.items || []);
      setNotifications(notifResult.items || []);
    } catch (err) {
      setLoadError(err as ProblemDetails | Error);
    } finally {
      setIsLoading(false);
    }
  }, [initialReservations, initialNotifications, token]);

  useEffect(() => {
    if (initialReservations === undefined || initialNotifications === undefined) {
      loadInboxData();
    }
  }, [loadInboxData, initialReservations, initialNotifications]);

  // Read-state mutation: updates ONLY after successful server response
  const handleMarkNotificationRead = async (notificationId: string) => {
    const updated = await apiClient.notifications.markRead(notificationId, { token });

    setNotifications((prev) =>
      prev.map((notif) =>
        notif.notification_id === notificationId ? updated : notif,
      ),
    );
  };

  // Reservation cancellation mutation
  const handleCancelReservation = async (reservationId: string) => {
    const updated = await apiClient.reservations.cancel(reservationId, { token });
    setReservations((prev) =>
      prev.map((res) =>
        res.reservation_id === reservationId ? updated : res,
      ),
    );
  };

  const handleOpenRecord = (recordType: string, recordId: string) => {
    if (onOpenRecord) {
      onOpenRecord(recordType, recordId);
      return;
    }

    if (typeof window !== 'undefined') {
      if (recordType === 'book') {
        window.location.hash = '#/catalog';
      } else if (recordType === 'loan' || recordType === 'reservation') {
        window.location.hash = '#/circulation';
      }
    }
  };

  const unreadCount = notifications.filter((n) => n.status === 'unread').length;
  const activeReservationCount = reservations.filter(
    (r) => r.status === 'pending' || r.status === 'held',
  ).length;

  return (
    <div
      data-testid="reservation-inbox-workspace"
      className={className}
      style={{
        display: 'flex',
        flexDirection: 'column',
        gap: tokens.spacing.semantic.groupToGroup,
        maxWidth: '780px',
        ...style,
      }}
    >
      {/* Header and Operational Status Cue */}
      {!loadError && (
        <StatusMessage status="info" title="Time-Sensitive Inbox">
          Hold allocations, pickup windows, and circulation notices synchronized with authoritative backend state.
        </StatusMessage>
      )}

      {/* Title & View Filters */}
      <div>
        <h2
          style={{
            margin: 0,
            fontFamily: tokens.typography.fontFamily,
            fontSize: tokens.typography.fontSizes['2xl'],
            fontWeight: tokens.typography.fontWeights.bold,
            color: tokens.colors.textPrimary,
          }}
        >
          Reservation Queue & Notification Inbox
        </h2>
        <p
          style={{
            margin: '4px 0 0 0',
            fontFamily: tokens.typography.fontFamily,
            fontSize: tokens.typography.fontSizes.sm,
            color: tokens.colors.textSecondary,
          }}
        >
          Track reservation progression, hold status, and time-sensitive alerts
        </p>
      </div>

      {/* Filter Segmented Control & Actions Row */}
      {!loadError && (
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            flexWrap: 'wrap',
            gap: tokens.spacing.md,
          }}
        >
          <div
            role="tablist"
            aria-label="Inbox view filters"
            style={{
              display: 'flex',
              gap: tokens.spacing.xs,
              backgroundColor: tokens.colors.surfaceAlt,
              padding: '4px',
              borderRadius: tokens.radius.md,
              border: `1px solid ${tokens.colors.border}`,
              width: 'fit-content',
            }}
          >
            <button
              role="tab"
              aria-selected={activeFilter === 'all'}
              onClick={() => setActiveFilter('all')}
              style={{
                padding: `${tokens.spacing.xs} ${tokens.spacing.sm}`,
                borderRadius: tokens.radius.sm,
                border: 'none',
                backgroundColor: activeFilter === 'all' ? tokens.colors.surface : 'transparent',
                color: activeFilter === 'all' ? tokens.colors.textPrimary : tokens.colors.textSecondary,
                fontWeight: activeFilter === 'all' ? tokens.typography.fontWeights.semibold : tokens.typography.fontWeights.normal,
                fontSize: tokens.typography.fontSizes.sm,
                cursor: 'pointer',
                boxShadow: activeFilter === 'all' ? '0 1px 2px rgba(0, 0, 0, 0.05)' : 'none',
              }}
            >
              All Items ({reservations.length + notifications.length})
            </button>

            <button
              role="tab"
              aria-selected={activeFilter === 'notifications'}
              onClick={() => setActiveFilter('notifications')}
              style={{
                padding: `${tokens.spacing.xs} ${tokens.spacing.sm}`,
                borderRadius: tokens.radius.sm,
                border: 'none',
                backgroundColor: activeFilter === 'notifications' ? tokens.colors.surface : 'transparent',
                color: activeFilter === 'notifications' ? tokens.colors.textPrimary : tokens.colors.textSecondary,
                fontWeight: activeFilter === 'notifications' ? tokens.typography.fontWeights.semibold : tokens.typography.fontWeights.normal,
                fontSize: tokens.typography.fontSizes.sm,
                cursor: 'pointer',
                boxShadow: activeFilter === 'notifications' ? '0 1px 2px rgba(0, 0, 0, 0.05)' : 'none',
              }}
            >
              Notifications {unreadCount > 0 ? `(${unreadCount} unread)` : `(${notifications.length})`}
            </button>

            <button
              role="tab"
              aria-selected={activeFilter === 'reservations'}
              onClick={() => setActiveFilter('reservations')}
              style={{
                padding: `${tokens.spacing.xs} ${tokens.spacing.sm}`,
                borderRadius: tokens.radius.sm,
                border: 'none',
                backgroundColor: activeFilter === 'reservations' ? tokens.colors.surface : 'transparent',
                color: activeFilter === 'reservations' ? tokens.colors.textPrimary : tokens.colors.textSecondary,
                fontWeight: activeFilter === 'reservations' ? tokens.typography.fontWeights.semibold : tokens.typography.fontWeights.normal,
                fontSize: tokens.typography.fontSizes.sm,
                cursor: 'pointer',
                boxShadow: activeFilter === 'reservations' ? '0 1px 2px rgba(0, 0, 0, 0.05)' : 'none',
              }}
            >
              Reservations {activeReservationCount > 0 ? `(${activeReservationCount} active)` : `(${reservations.length})`}
            </button>
          </div>

          {/* Direct Reservation Placement (M-05) */}
          <Button
            type="button"
            variant="secondary"
            size="sm"
            onClick={() => setIsCreateModalOpen(true)}
          >
            + Đặt Giữ Sách
          </Button>
        </div>
      )}

      {/* Loading Shimmer State */}
      {isLoading && (
        <LoadingSkeleton
          lines={4}
          ariaLabel="Loading reservation queue and notification inbox..."
        />
      )}

      {/* Failure State with RFC Problem Details and Retry */}
      {!isLoading && loadError && (
        <ProblemDetailsRenderer
          error={loadError}
          isSafeToRetry={true}
          onRetry={loadInboxData}
        />
      )}

      {/* Content Rendering */}
      {!isLoading && !loadError && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: tokens.spacing.semantic.groupToGroup }}>
          {/* Notifications Section */}
          {(activeFilter === 'all' || activeFilter === 'notifications') && (
            <section
              aria-labelledby="section-notifications-title"
              style={{ display: 'flex', flexDirection: 'column', gap: tokens.spacing.sm }}
            >
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <h3
                  id="section-notifications-title"
                  style={{
                    margin: 0,
                    fontFamily: tokens.typography.fontFamily,
                    fontSize: tokens.typography.fontSizes.lg,
                    fontWeight: tokens.typography.fontWeights.semibold,
                    color: tokens.colors.textPrimary,
                  }}
                >
                  Notifications Inbox
                </h3>
                {unreadCount > 0 && (
                  <span
                    style={{
                      fontSize: tokens.typography.fontSizes.xs,
                      color: tokens.colors.status.warning.color,
                      backgroundColor: tokens.colors.status.warning.bg,
                      padding: '2px 8px',
                      borderRadius: tokens.radius.full,
                      fontWeight: tokens.typography.fontWeights.semibold,
                    }}
                  >
                    {unreadCount} Unread
                  </span>
                )}
              </div>

              {notifications.length === 0 ? (
                <EmptyState
                  title="Notification Inbox Clear"
                  description="You have no unread notifications or system alerts. Time-sensitive loan due dates, hold pickup notices, and account updates will appear here."
                />
              ) : (
                <div style={{ display: 'flex', flexDirection: 'column', gap: tokens.spacing.sm }}>
                  {notifications.map((notif) => (
                    <NotificationCard
                      key={notif.notification_id}
                      notification={notif}
                      onMarkRead={handleMarkNotificationRead}
                      onOpenRecord={handleOpenRecord}
                    />
                  ))}
                </div>
              )}
            </section>
          )}

          {/* Reservations Progression Section */}
          {(activeFilter === 'all' || activeFilter === 'reservations') && (
            <section
              aria-labelledby="section-reservations-title"
              style={{ display: 'flex', flexDirection: 'column', gap: tokens.spacing.sm }}
            >
              <h3
                id="section-reservations-title"
                style={{
                  margin: 0,
                  fontFamily: tokens.typography.fontFamily,
                  fontSize: tokens.typography.fontSizes.lg,
                  fontWeight: tokens.typography.fontWeights.semibold,
                  color: tokens.colors.textPrimary,
                }}
              >
                Reservation Queue Status
              </h3>

              {reservations.length === 0 ? (
                <EmptyState
                  title="No Active Reservations"
                  description="You do not have any pending or held book reservations at this time. Search the bibliographic catalog to place a hold when copies are unavailable."
                  action={{
                    label: 'Explore Catalog',
                    onAction: () => {
                      if (typeof window !== 'undefined') {
                        window.location.hash = '#/catalog';
                      }
                    },
                  }}
                />
              ) : (
                <div style={{ display: 'flex', flexDirection: 'column', gap: tokens.spacing.sm }}>
                  {reservations.map((res) => (
                    <ReservationStatusCard
                      key={res.reservation_id}
                      reservation={res}
                      onCancel={handleCancelReservation}
                      onOpenRecord={handleOpenRecord}
                    />
                  ))}
                </div>
              )}
            </section>
          )}
        </div>
      )}

      {/* Direct Reservation Creation Modal (M-05) */}
      <CreateReservationModal
        isOpen={isCreateModalOpen}
        onClose={() => setIsCreateModalOpen(false)}
        onSuccess={handleReservationCreated}
        accessToken={token}
      />
    </div>
  );
}
