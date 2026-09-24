import { CSSProperties } from 'react';
import { Reservation, Notification } from '../../shared/api';

export type InboxViewFilter = 'all' | 'notifications' | 'reservations';

export interface ReservationInboxProps {
  initialReservations?: Reservation[];
  initialNotifications?: Notification[];
  onOpenRecord?: (recordType: string, recordId: string) => void;
  className?: string;
  style?: CSSProperties;
}

export interface ReservationStatusCardProps {
  reservation: Reservation;
  onCancel?: (reservationId: string) => Promise<void> | void;
  onOpenRecord?: (recordType: string, recordId: string) => void;
  isCancelling?: boolean;
}

export interface NotificationCardProps {
  notification: Notification;
  onMarkRead?: (notificationId: string) => Promise<void> | void;
  onOpenRecord?: (recordType: string, recordId: string) => void;
  isMarkingRead?: boolean;
}
