export type {
  Location,
  LocationPage,
  LocationWrite,
  BookCopy,
  BookCopyPage,
  BookCopyWrite,
  BookCopyUpdate,
  CopyStatusTransition,
  CopyStatusHistoryRecord,
  CopyStatusHistoryPage,
  CopyStatus,
} from '../../shared/api';

export { ALLOWED_STATUS_TRANSITIONS } from '../../shared/api';

export interface CopyRegistrationFormValues {
  barcode: string;
  location_id: string;
  condition_code: string;
}

export interface CopyRegistrationValidationErrors {
  barcode?: string;
  location_id?: string;
  condition_code?: string;
}

export interface LocationAssignmentFormValues {
  location_id: string;
  condition_code: string;
}

export interface CopyStatusFormValues {
  to_status: string;
  reason: string;
}

export interface CopyStatusValidationErrors {
  to_status?: string;
  reason?: string;
}
