import { useState, useEffect, useCallback, useContext } from 'react';
import { useTokens } from '../../shared/tokens';
import {
  Department,
  Semester,
  Class,
  ClassMembership,
  Student,
  Teacher,
  BorrowerPolicy,
  ProblemDetails,
  ProblemDetailsError,
  apiClient,
} from '../../shared/api';
import { AuthContext } from '../auth/context';
import { ProblemDetailsRenderer } from '../../shared/components';
import { EducationWorkspaceProps, EducationTab } from './types';
import { EditionUnavailableState } from './EditionUnavailableState';
import { PeopleManager } from './PeopleManager';
import { AcademicRecordsManager } from './AcademicRecordsManager';
import { BorrowerPolicyView } from './BorrowerPolicyView';

/**
 * Education Management and Borrower Policy Views Workspace (FE-009).
 *
 * Implements acceptance criteria and architectural invariants:
 * - Simple, low-cognitive-overhead education workspace for authorized staff.
 * - Grouped forms for student/teacher and academic relationships.
 * - Visual distinction between student and teacher records without separate visual noise.
 * - Explanatory unavailable state when the education edition is disabled (HTTP 403 edition-unavailable),
 *   leaking no tenant database configuration or internal infrastructure details.
 * - Read-only explanation of configured borrower policies and operational checkout effects in plain language.
 * - Attaches academic date validation errors directly to their relevant inputs.
 */
export function EducationWorkspace({
  initialTab = 'people',
  className,
  style,
  onNavigateTab,
}: EducationWorkspaceProps) {
  const tokens = useTokens();
  const authContext = useContext(AuthContext);
  const token = authContext?.accessToken;

  const [activeTab, setActiveTab] = useState<EducationTab>(initialTab);

  // Data state
  const [departments, setDepartments] = useState<Department[]>([]);
  const [semesters, setSemesters] = useState<Semester[]>([]);
  const [classes, setClasses] = useState<Class[]>([]);
  const [students, setStudents] = useState<Student[]>([]);
  const [teachers, setTeachers] = useState<Teacher[]>([]);
  const [policies, setPolicies] = useState<BorrowerPolicy[]>([]);
  const [memberships, setMemberships] = useState<Record<string, ClassMembership[]>>({});

  // Request state
  const [isLoading, setIsLoading] = useState(true);
  const [isEditionUnavailable, setIsEditionUnavailable] = useState(false);
  const [editionUnavailableDetail, setEditionUnavailableDetail] = useState<string | undefined>();
  const [problemError, setProblemError] = useState<ProblemDetails | Error | null>(null);

  // Load all education workspace datasets
  const loadWorkspaceData = useCallback(async () => {
    setIsLoading(true);
    setProblemError(null);
    setIsEditionUnavailable(false);

    try {
      const [deptRes, semRes, clsRes, stuRes, tchRes, polRes] = await Promise.all([
        apiClient.education.departments.list({ token }),
        apiClient.education.semesters.list({ token }),
        apiClient.education.classes.list({ token }),
        apiClient.education.students.list({ token }),
        apiClient.education.teachers.list({ token }),
        apiClient.education.policies.list({ token }),
      ]);

      setDepartments(deptRes.items || []);
      setSemesters(semRes.items || []);
      setClasses(clsRes.items || []);
      setStudents(stuRes.items || []);
      setTeachers(tchRes.items || []);
      setPolicies(polRes.items || []);

      // Preload memberships for the first class if available
      const firstClass = clsRes.items?.[0];
      if (firstClass) {
        const firstClassId = firstClass.class_id;
        try {
          const memRes = await apiClient.education.classes.listMemberships(firstClassId, { token });
          setMemberships((prev) => ({ ...prev, [firstClassId]: memRes.items || [] }));
        } catch {
          // Non-critical background fetch failure for optional memberships
        }
      }
    } catch (err: unknown) {
      if (err instanceof ProblemDetailsError) {
        const problem = err.problem;
        if (problem.type.includes('edition-unavailable') || problem.status === 403) {
          setIsEditionUnavailable(true);
          setEditionUnavailableDetail(problem.detail);
          return;
        }
        setProblemError(problem);
      } else if (err instanceof Error) {
        setProblemError(err);
      } else {
        setProblemError(new Error('Failed to load education workspace data'));
      }
    } finally {
      setIsLoading(false);
    }
  }, [token]);

  useEffect(() => {
    loadWorkspaceData();
  }, [loadWorkspaceData]);

  // Tab switching
  const handleTabChange = (tab: EducationTab) => {
    setActiveTab(tab);
    onNavigateTab?.(tab);
  };

  // Mutators
  const handleRegisterStudent = async (data: {
    user_id: string;
    student_number: string;
    department_id?: string | null;
    status: string;
  }) => {
    const created = await apiClient.education.students.create(data, { token });
    setStudents((prev) => [created, ...prev]);
  };

  const handleRegisterTeacher = async (data: {
    user_id: string;
    employee_number: string;
    department_id?: string | null;
    status: string;
  }) => {
    const created = await apiClient.education.teachers.create(data, { token });
    setTeachers((prev) => [created, ...prev]);
  };

  const handleCreateSemester = async (data: {
    name: string;
    starts_on: string;
    ends_on: string;
    status: string;
  }) => {
    const created = await apiClient.education.semesters.create(data, { token });
    setSemesters((prev) => [created, ...prev]);
  };

  const handleCreateClass = async (data: {
    code: string;
    name: string;
    semester_id: string;
    department_id?: string | null;
    status: string;
  }) => {
    const created = await apiClient.education.classes.create(data, { token });
    setClasses((prev) => [created, ...prev]);
  };

  const handleEnrollStudent = async (
    classId: string,
    data: { student_id: string; joined_at?: string | null; left_at?: string | null },
  ) => {
    const created = await apiClient.education.classes.createMembership(classId, data, { token });
    setMemberships((prev) => ({
      ...prev,
      [classId]: [created, ...(prev[classId] || [])],
    }));
  };

  const handleSelectClassForMemberships = async (classId: string) => {
    if (!memberships[classId]) {
      try {
        const res = await apiClient.education.classes.listMemberships(classId, { token });
        setMemberships((prev) => ({ ...prev, [classId]: res.items || [] }));
      } catch {
        // Memberships fetch error handled gracefully
      }
    }
  };

  // 1. Edition-Unavailable Interception
  if (isEditionUnavailable) {
    return <EditionUnavailableState detail={editionUnavailableDetail} className={className} style={style} />;
  }

  // 2. Fatal General Request Error
  if (problemError && !isLoading) {
    return (
      <div style={{ maxWidth: '800px', margin: '0 auto', ...style }}>
        <ProblemDetailsRenderer
          error={problemError}
          onRetry={loadWorkspaceData}
          isSafeToRetry={true}
        />
      </div>
    );
  }

  return (
    <div
      className={className}
      style={{
        display: 'flex',
        flexDirection: 'column',
        gap: tokens.spacing.lg,
        maxWidth: '1280px',
        margin: '0 auto',
        width: '100%',
        ...style,
      }}
    >
      {/* Workspace Header */}
      <header style={{ borderBottom: `1px solid ${tokens.colors.border}`, paddingBottom: tokens.spacing.md }}>
        <h2
          style={{
            margin: 0,
            fontSize: tokens.typography.fontSizes['2xl'],
            fontWeight: tokens.typography.fontWeights.bold,
            color: tokens.colors.textPrimary,
            letterSpacing: '-0.01em',
          }}
        >
          Education Workspace
        </h2>
        <p
          style={{
            margin: `${tokens.spacing.xs} 0 0`,
            fontSize: tokens.typography.fontSizes.sm,
            color: tokens.colors.textSecondary,
          }}
        >
          Manage student and faculty records, academic relationships, and inspect configured borrower loan policies.
        </p>
      </header>

      {/* Accessible Tab List */}
      <div
        role="tablist"
        aria-label="Education Management Workspace Sections"
        style={{
          display: 'flex',
          gap: tokens.spacing.sm,
          borderBottom: `2px solid ${tokens.colors.border}`,
          paddingBottom: '2px',
          flexWrap: 'wrap',
        }}
      >
        <button
          type="button"
          role="tab"
          id="tab-people"
          aria-selected={activeTab === 'people'}
          aria-controls="panel-people"
          tabIndex={activeTab === 'people' ? 0 : -1}
          onClick={() => handleTabChange('people')}
          style={{
            padding: `${tokens.buttonSpacing.md.py} ${tokens.buttonSpacing.md.px}`,
            borderRadius: `${tokens.radius.md} ${tokens.radius.md} 0 0`,
            border: 'none',
            borderBottom: `3px solid ${activeTab === 'people' ? tokens.colors.primary : 'transparent'}`,
            backgroundColor: activeTab === 'people' ? tokens.colors.surfaceElevated : 'transparent',
            color: activeTab === 'people' ? tokens.colors.primary : tokens.colors.textSecondary,
            fontWeight: activeTab === 'people' ? tokens.typography.fontWeights.bold : tokens.typography.fontWeights.medium,
            fontSize: tokens.typography.fontSizes.sm,
            cursor: 'pointer',
            outline: 'none',
            transition: 'all 150ms ease',
          }}
        >
          People & Profiles
        </button>

        <button
          type="button"
          role="tab"
          id="tab-academic"
          aria-selected={activeTab === 'academic'}
          aria-controls="panel-academic"
          tabIndex={activeTab === 'academic' ? 0 : -1}
          onClick={() => handleTabChange('academic')}
          style={{
            padding: `${tokens.buttonSpacing.md.py} ${tokens.buttonSpacing.md.px}`,
            borderRadius: `${tokens.radius.md} ${tokens.radius.md} 0 0`,
            border: 'none',
            borderBottom: `3px solid ${activeTab === 'academic' ? tokens.colors.primary : 'transparent'}`,
            backgroundColor: activeTab === 'academic' ? tokens.colors.surfaceElevated : 'transparent',
            color: activeTab === 'academic' ? tokens.colors.primary : tokens.colors.textSecondary,
            fontWeight: activeTab === 'academic' ? tokens.typography.fontWeights.bold : tokens.typography.fontWeights.medium,
            fontSize: tokens.typography.fontSizes.sm,
            cursor: 'pointer',
            outline: 'none',
            transition: 'all 150ms ease',
          }}
        >
          Academic Records
        </button>

        <button
          type="button"
          role="tab"
          id="tab-policies"
          aria-selected={activeTab === 'policies'}
          aria-controls="panel-policies"
          tabIndex={activeTab === 'policies' ? 0 : -1}
          onClick={() => handleTabChange('policies')}
          style={{
            padding: `${tokens.buttonSpacing.md.py} ${tokens.buttonSpacing.md.px}`,
            borderRadius: `${tokens.radius.md} ${tokens.radius.md} 0 0`,
            border: 'none',
            borderBottom: `3px solid ${activeTab === 'policies' ? tokens.colors.primary : 'transparent'}`,
            backgroundColor: activeTab === 'policies' ? tokens.colors.surfaceElevated : 'transparent',
            color: activeTab === 'policies' ? tokens.colors.primary : tokens.colors.textSecondary,
            fontWeight: activeTab === 'policies' ? tokens.typography.fontWeights.bold : tokens.typography.fontWeights.medium,
            fontSize: tokens.typography.fontSizes.sm,
            cursor: 'pointer',
            outline: 'none',
            transition: 'all 150ms ease',
          }}
        >
          Borrower Policies
        </button>
      </div>

      {/* Main Tab Panels */}
      <main style={{ marginTop: tokens.spacing.sm }}>
        {/* Panel 1: People & Profiles */}
        <div
          role="tabpanel"
          id="panel-people"
          aria-labelledby="tab-people"
          hidden={activeTab !== 'people'}
        >
          {activeTab === 'people' && (
            <PeopleManager
              departments={departments}
              students={students}
              teachers={teachers}
              isLoading={isLoading}
              onRegisterStudent={handleRegisterStudent}
              onRegisterTeacher={handleRegisterTeacher}
            />
          )}
        </div>

        {/* Panel 2: Academic Records */}
        <div
          role="tabpanel"
          id="panel-academic"
          aria-labelledby="tab-academic"
          hidden={activeTab !== 'academic'}
        >
          {activeTab === 'academic' && (
            <AcademicRecordsManager
              departments={departments}
              semesters={semesters}
              classes={classes}
              memberships={memberships}
              isLoading={isLoading}
              onCreateSemester={handleCreateSemester}
              onCreateClass={handleCreateClass}
              onEnrollStudent={handleEnrollStudent}
              onSelectClassForMemberships={handleSelectClassForMemberships}
            />
          )}
        </div>

        {/* Panel 3: Borrower Policies */}
        <div
          role="tabpanel"
          id="panel-policies"
          aria-labelledby="tab-policies"
          hidden={activeTab !== 'policies'}
        >
          {activeTab === 'policies' && (
            <BorrowerPolicyView
              policies={policies}
              isLoading={isLoading}
            />
          )}
        </div>
      </main>
    </div>
  );
}
