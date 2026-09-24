import { CSSProperties } from 'react';
import {
  Department,
  Semester,
  Class,
  ClassMembership,
  Student,
  Teacher,
  BorrowerPolicy,
} from '../../shared/api';

export type EducationTab = 'people' | 'academic' | 'policies';
export type PersonRole = 'student' | 'teacher';

export interface EducationWorkspaceProps {
  initialTab?: EducationTab;
  className?: string;
  style?: CSSProperties;
  onNavigateTab?: (tab: EducationTab) => void;
}

export interface PeopleManagerProps {
  departments: Department[];
  students: Student[];
  teachers: Teacher[];
  isLoading?: boolean;
  onRegisterStudent: (data: {
    user_id: string;
    student_number: string;
    department_id?: string | null;
    status: string;
  }) => Promise<void>;
  onRegisterTeacher: (data: {
    user_id: string;
    employee_number: string;
    department_id?: string | null;
    status: string;
  }) => Promise<void>;
}

export interface AcademicRecordsManagerProps {
  departments: Department[];
  semesters: Semester[];
  classes: Class[];
  memberships: Record<string, ClassMembership[]>;
  isLoading?: boolean;
  onCreateSemester: (data: {
    name: string;
    starts_on: string;
    ends_on: string;
    status: string;
  }) => Promise<void>;
  onCreateClass: (data: {
    code: string;
    name: string;
    semester_id: string;
    department_id?: string | null;
    status: string;
  }) => Promise<void>;
  onEnrollStudent: (classId: string, data: {
    student_id: string;
    joined_at?: string | null;
    left_at?: string | null;
  }) => Promise<void>;
  onSelectClassForMemberships?: (classId: string) => void;
}

export interface BorrowerPolicyViewProps {
  policies: BorrowerPolicy[];
  isLoading?: boolean;
}

export interface EditionUnavailableStateProps {
  detail?: string;
  className?: string;
  style?: CSSProperties;
}
