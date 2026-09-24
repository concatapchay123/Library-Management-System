import React, { useState } from 'react';
import { useTokens } from '../../shared/tokens';
import { AcademicRecordsManagerProps } from './types';
import { Input, Select, Button, StatusMessage, LoadingSkeleton, EmptyState } from '../../shared/components';
import { ProblemDetailsError } from '../../shared/api';

/**
 * Academic Records Management (FE-009).
 *
 * Implements acceptance criteria and architectural invariants:
 * - Academic date validation errors from server are attached directly to their relevant inputs.
 * - Manages semesters, classes, and student class enrollment in logical grouped sections.
 * - Single-column forms with semantic spacing and clear visual hierarchy.
 */
export function AcademicRecordsManager({
  departments,
  semesters,
  classes,
  memberships,
  isLoading = false,
  onCreateSemester,
  onCreateClass,
  onEnrollStudent,
  onSelectClassForMemberships,
}: AcademicRecordsManagerProps) {
  const tokens = useTokens();

  // Semester Form State
  const [semesterName, setSemesterName] = useState('');
  const [startsOn, setStartsOn] = useState('');
  const [endsOn, setEndsOn] = useState('');
  const [semesterStatus, setSemesterStatus] = useState('active');
  const [semesterSubmitting, setSemesterSubmitting] = useState(false);
  const [semesterSuccess, setSemesterSuccess] = useState<string | null>(null);
  const [semesterGeneralError, setSemesterGeneralError] = useState<string | null>(null);
  const [semesterDateErrors, setSemesterDateErrors] = useState<{ startsOn?: string; endsOn?: string }>({});

  // Class Form State
  const [classCode, setClassCode] = useState('');
  const [classNameInput, setClassNameInput] = useState('');
  const [classSemesterId, setClassSemesterId] = useState(semesters[0]?.semester_id || '');
  const [classDepartmentId, setClassDepartmentId] = useState('');
  const [classStatus, setClassStatus] = useState('active');
  const [classSubmitting, setClassSubmitting] = useState(false);
  const [classSuccess, setClassSuccess] = useState<string | null>(null);
  const [classError, setClassError] = useState<string | null>(null);

  // Enrollment Form State
  const [enrollClassId, setEnrollClassId] = useState(classes[0]?.class_id || '');
  const [studentId, setStudentId] = useState('');
  const [joinedAt, setJoinedAt] = useState('');
  const [leftAt, setLeftAt] = useState('');
  const [enrollSubmitting, setEnrollSubmitting] = useState(false);
  const [enrollSuccess, setEnrollSuccess] = useState<string | null>(null);
  const [enrollGeneralError, setEnrollGeneralError] = useState<string | null>(null);
  const [membershipDateErrors, setMembershipDateErrors] = useState<{ joinedAt?: string; leftAt?: string }>({});

  const cardRadius = 10;
  const cardPadding = 20;

  // Department and Semester lookup maps
  const departmentMap = new Map(departments.map((d) => [d.department_id, d.name]));
  const semesterMap = new Map(semesters.map((s) => [s.semester_id, s.name]));

  // Handle Semester creation with direct input date error binding
  const handleSemesterSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSemesterGeneralError(null);
    setSemesterSuccess(null);
    setSemesterDateErrors({});

    if (!semesterName.trim()) {
      setSemesterGeneralError('Semester name is required');
      return;
    }
    if (!startsOn || !endsOn) {
      setSemesterDateErrors({
        startsOn: !startsOn ? 'Start date is required' : undefined,
        endsOn: !endsOn ? 'End date is required' : undefined,
      });
      return;
    }

    setSemesterSubmitting(true);
    try {
      await onCreateSemester({
        name: semesterName.trim(),
        starts_on: startsOn,
        ends_on: endsOn,
        status: semesterStatus,
      });

      setSemesterSuccess(`Semester "${semesterName.trim()}" created successfully.`);
      setSemesterName('');
      setStartsOn('');
      setEndsOn('');
    } catch (err: unknown) {
      if (err instanceof ProblemDetailsError) {
        const detail = err.problem.detail;
        if (
          err.problem.type.includes('invalid-semester-dates') ||
          detail.toLowerCase().includes('starts_on') ||
          detail.toLowerCase().includes('ends_on') ||
          detail.toLowerCase().includes('date')
        ) {
          // Attached directly to relevant input
          setSemesterDateErrors({ endsOn: detail });
          return;
        }
        setSemesterGeneralError(detail || err.message);
      } else {
        setSemesterGeneralError(err instanceof Error ? err.message : 'Failed to create semester');
      }
    } finally {
      setSemesterSubmitting(false);
    }
  };

  // Handle Class creation
  const handleClassSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setClassError(null);
    setClassSuccess(null);

    const semId = classSemesterId || semesters[0]?.semester_id;
    if (!classCode.trim() || !classNameInput.trim() || !semId) {
      setClassError('Code, Name, and Semester are required');
      return;
    }

    setClassSubmitting(true);
    try {
      await onCreateClass({
        code: classCode.trim(),
        name: classNameInput.trim(),
        semester_id: semId,
        department_id: classDepartmentId || null,
        status: classStatus,
      });

      setClassSuccess(`Class "${classCode.trim()} - ${classNameInput.trim()}" created successfully.`);
      setClassCode('');
      setClassNameInput('');
      setClassDepartmentId('');
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Failed to create class';
      setClassError(msg);
    } finally {
      setClassSubmitting(false);
    }
  };

  // Handle Enrollment with direct input date error binding
  const handleEnrollSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setEnrollGeneralError(null);
    setEnrollSuccess(null);
    setMembershipDateErrors({});

    const targetClassId = enrollClassId || classes[0]?.class_id;
    if (!targetClassId || !studentId.trim()) {
      setEnrollGeneralError('Class and Student ID are required');
      return;
    }

    setEnrollSubmitting(true);
    try {
      await onEnrollStudent(targetClassId, {
        student_id: studentId.trim(),
        joined_at: joinedAt ? new Date(joinedAt).toISOString() : null,
        left_at: leftAt ? new Date(leftAt).toISOString() : null,
      });

      setEnrollSuccess(`Student enrolled in class successfully.`);
      setStudentId('');
      setJoinedAt('');
      setLeftAt('');
    } catch (err: unknown) {
      if (err instanceof ProblemDetailsError) {
        const detail = err.problem.detail;
        if (
          err.problem.type.includes('invalid-membership-dates') ||
          detail.toLowerCase().includes('left_at') ||
          detail.toLowerCase().includes('joined_at')
        ) {
          // Attached directly to left_at input
          setMembershipDateErrors({ leftAt: detail });
          return;
        }
        setEnrollGeneralError(detail || err.message);
      } else {
        setEnrollGeneralError(err instanceof Error ? err.message : 'Failed to enroll student');
      }
    } finally {
      setEnrollSubmitting(false);
    }
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: tokens.spacing['2xl'] }}>
      {/* 1. Semesters Section */}
      <section
        aria-labelledby="semesters-section-heading"
        style={{
          display: 'flex',
          flexDirection: 'column',
          gap: tokens.spacing.lg,
        }}
      >
        <header>
          <h3
            id="semesters-section-heading"
            style={{
              margin: 0,
              fontSize: tokens.typography.fontSizes.lg,
              fontWeight: tokens.typography.fontWeights.bold,
              color: tokens.colors.textPrimary,
            }}
          >
            Academic Semesters
          </h3>
          <p style={{ margin: `${tokens.spacing.xs} 0 0`, fontSize: tokens.typography.fontSizes.sm, color: tokens.colors.textSecondary }}>
            Define academic terms bounding student matriculation, enrollment windows, and course scheduling.
          </p>
        </header>

        {/* Add Semester Form */}
        <div
          style={{
            backgroundColor: tokens.colors.surface,
            border: `1px solid ${tokens.colors.border}`,
            borderRadius: `${cardRadius}px`,
            padding: `${cardPadding}px`,
            boxShadow: '0 1px 2px 0 rgba(0, 0, 0, 0.05)',
          }}
        >
          <h4 style={{ margin: `0 0 ${tokens.spacing.sm}`, fontSize: tokens.typography.fontSizes.md, fontWeight: tokens.typography.fontWeights.bold, color: tokens.colors.textPrimary }}>
            Add Academic Semester
          </h4>

          {semesterSuccess && <StatusMessage status="success" style={{ marginBottom: tokens.spacing.md }}>{semesterSuccess}</StatusMessage>}
          {semesterGeneralError && <StatusMessage status="danger" style={{ marginBottom: tokens.spacing.md }}>{semesterGeneralError}</StatusMessage>}

          <form onSubmit={handleSemesterSubmit} noValidate style={{ display: 'flex', flexDirection: 'column', gap: tokens.spacing.md }}>
            <Input
              id="semester-name"
              label="Semester Name"
              value={semesterName}
              onChange={(e) => setSemesterName(e.target.value)}
              placeholder="e.g. Fall 2026, Spring 2027"
              disabled={semesterSubmitting}
            />

            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))', gap: tokens.spacing.md }}>
              <Input
                id="semester-starts-on"
                label="Start Date"
                type="date"
                value={startsOn}
                onChange={(e) => setStartsOn(e.target.value)}
                errorMessage={semesterDateErrors.startsOn}
                disabled={semesterSubmitting}
              />

              <Input
                id="semester-ends-on"
                label="End Date"
                type="date"
                value={endsOn}
                onChange={(e) => setEndsOn(e.target.value)}
                errorMessage={semesterDateErrors.endsOn}
                description="Must occur chronologically after the start date."
                disabled={semesterSubmitting}
              />
            </div>

            <Select
              id="semester-status"
              label="Status"
              value={semesterStatus}
              onChange={(e) => setSemesterStatus(e.target.value)}
              disabled={semesterSubmitting}
            >
              <option value="active">Active</option>
              <option value="upcoming">Upcoming</option>
              <option value="archived">Archived</option>
            </Select>

            <div style={{ marginTop: tokens.spacing.sm }}>
              <Button type="submit" variant="primary" disabled={semesterSubmitting}>
                Create Semester
              </Button>
            </div>
          </form>
        </div>

        {/* Semesters List */}
        <div>
          <h4 style={{ margin: `0 0 ${tokens.spacing.sm}`, fontSize: tokens.typography.fontSizes.sm, fontWeight: tokens.typography.fontWeights.semibold, color: tokens.colors.textMuted }}>
            Configured Semesters ({semesters.length})
          </h4>

          {isLoading ? (
            <LoadingSkeleton height={80} />
          ) : semesters.length === 0 ? (
            <EmptyState title="No Semesters Registered" description="Add your first academic semester using the form above." />
          ) : (
            <div role="list" aria-label="Semesters List" style={{ display: 'flex', flexDirection: 'column', gap: tokens.spacing.sm }}>
              {semesters.map((s) => (
                <div
                  key={s.semester_id}
                  role="listitem"
                  style={{
                    backgroundColor: tokens.colors.surface,
                    border: `1px solid ${tokens.colors.border}`,
                    borderRadius: tokens.radius.md,
                    padding: tokens.spacing.md,
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    boxShadow: '0 1px 2px 0 rgba(0, 0, 0, 0.05)',
                  }}
                >
                  <div>
                    <strong style={{ display: 'block', fontSize: tokens.typography.fontSizes.md, color: tokens.colors.textPrimary }}>
                      {s.name}
                    </strong>
                    <span style={{ fontSize: tokens.typography.fontSizes.xs, color: tokens.colors.textMuted }}>
                      Dates: {s.starts_on} to {s.ends_on}
                    </span>
                  </div>
                  <span
                    style={{
                      fontSize: tokens.typography.fontSizes.xs,
                      padding: '2px 8px',
                      borderRadius: tokens.radius.sm,
                      backgroundColor: s.status === 'active' ? tokens.colors.status.success.bg : tokens.colors.surfaceAlt,
                      color: s.status === 'active' ? tokens.colors.status.success.color : tokens.colors.textMuted,
                      border: `1px solid ${s.status === 'active' ? tokens.colors.status.success.border : tokens.colors.border}`,
                      textTransform: 'capitalize',
                    }}
                  >
                    {s.status}
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>
      </section>

      {/* 2. Classes Section */}
      <section
        aria-labelledby="classes-section-heading"
        style={{
          display: 'flex',
          flexDirection: 'column',
          gap: tokens.spacing.lg,
        }}
      >
        <header>
          <h3
            id="classes-section-heading"
            style={{
              margin: 0,
              fontSize: tokens.typography.fontSizes.lg,
              fontWeight: tokens.typography.fontWeights.bold,
              color: tokens.colors.textPrimary,
            }}
          >
            Academic Classes & Sections
          </h3>
          <p style={{ margin: `${tokens.spacing.xs} 0 0`, fontSize: tokens.typography.fontSizes.sm, color: tokens.colors.textSecondary }}>
            Configure course sections linked to specific semesters and academic departments.
          </p>
        </header>

        {/* Add Class Form */}
        <div
          style={{
            backgroundColor: tokens.colors.surface,
            border: `1px solid ${tokens.colors.border}`,
            borderRadius: `${cardRadius}px`,
            padding: `${cardPadding}px`,
            boxShadow: '0 1px 2px 0 rgba(0, 0, 0, 0.05)',
          }}
        >
          <h4 style={{ margin: `0 0 ${tokens.spacing.sm}`, fontSize: tokens.typography.fontSizes.md, fontWeight: tokens.typography.fontWeights.bold, color: tokens.colors.textPrimary }}>
            Add Academic Class
          </h4>

          {classSuccess && <StatusMessage status="success" style={{ marginBottom: tokens.spacing.md }}>{classSuccess}</StatusMessage>}
          {classError && <StatusMessage status="danger" style={{ marginBottom: tokens.spacing.md }}>{classError}</StatusMessage>}

          <form onSubmit={handleClassSubmit} noValidate style={{ display: 'flex', flexDirection: 'column', gap: tokens.spacing.md }}>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))', gap: tokens.spacing.md }}>
              <Input
                id="class-code"
                label="Class Code"
                value={classCode}
                onChange={(e) => setClassCode(e.target.value)}
                placeholder="e.g. CS-101-A"
                disabled={classSubmitting}
              />

              <Input
                id="class-name"
                label="Class Name"
                value={classNameInput}
                onChange={(e) => setClassNameInput(e.target.value)}
                placeholder="e.g. Intro to Computer Science Section A"
                disabled={classSubmitting}
              />
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))', gap: tokens.spacing.md }}>
              <Select
                id="class-semester"
                label="Semester"
                value={classSemesterId}
                onChange={(e) => setClassSemesterId(e.target.value)}
                disabled={classSubmitting}
              >
                {semesters.map((s) => (
                  <option key={s.semester_id} value={s.semester_id}>
                    {s.name} ({s.starts_on} - {s.ends_on})
                  </option>
                ))}
              </Select>

              <Select
                id="class-department"
                label="Department"
                optional
                value={classDepartmentId}
                onChange={(e) => setClassDepartmentId(e.target.value)}
                disabled={classSubmitting}
              >
                <option key="none" value="">No Department Assigned</option>
                {departments.map((d) => (
                  <option key={d.department_id} value={d.department_id}>
                    {d.name} ({d.code})
                  </option>
                ))}
              </Select>
            </div>

            <Select
              id="class-status"
              label="Status"
              value={classStatus}
              onChange={(e) => setClassStatus(e.target.value)}
              disabled={classSubmitting}
            >
              <option value="active">Active</option>
              <option value="completed">Completed</option>
              <option value="cancelled">Cancelled</option>
            </Select>

            <div style={{ marginTop: tokens.spacing.sm }}>
              <Button type="submit" variant="primary" disabled={classSubmitting}>
                Create Class
              </Button>
            </div>
          </form>
        </div>

        {/* Classes List */}
        <div>
          <h4 style={{ margin: `0 0 ${tokens.spacing.sm}`, fontSize: tokens.typography.fontSizes.sm, fontWeight: tokens.typography.fontWeights.semibold, color: tokens.colors.textMuted }}>
            Configured Classes ({classes.length})
          </h4>

          {isLoading ? (
            <LoadingSkeleton height={80} />
          ) : classes.length === 0 ? (
            <EmptyState title="No Classes Found" description="Add your first class section using the form above." />
          ) : (
            <div role="list" aria-label="Classes List" style={{ display: 'flex', flexDirection: 'column', gap: tokens.spacing.sm }}>
              {classes.map((c) => {
                const semName = semesterMap.get(c.semester_id) || 'Unknown Semester';
                const deptName = c.department_id ? departmentMap.get(c.department_id) || 'General' : 'General';
                return (
                  <div
                    key={c.class_id}
                    role="listitem"
                    style={{
                      backgroundColor: tokens.colors.surface,
                      border: `1px solid ${tokens.colors.border}`,
                      borderRadius: tokens.radius.md,
                      padding: tokens.spacing.md,
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'space-between',
                      boxShadow: '0 1px 2px 0 rgba(0, 0, 0, 0.05)',
                    }}
                  >
                    <div>
                      <div style={{ display: 'flex', alignItems: 'center', gap: tokens.spacing.sm }}>
                        <span
                          style={{
                            fontSize: tokens.typography.fontSizes.xs,
                            fontWeight: tokens.typography.fontWeights.bold,
                            padding: '2px 6px',
                            borderRadius: tokens.radius.sm,
                            backgroundColor: tokens.colors.surfaceAlt,
                            color: tokens.colors.textPrimary,
                            border: `1px solid ${tokens.colors.border}`,
                          }}
                        >
                          {c.code}
                        </span>
                        <strong style={{ fontSize: tokens.typography.fontSizes.md, color: tokens.colors.textPrimary }}>
                          {c.name}
                        </strong>
                      </div>
                      <span style={{ fontSize: tokens.typography.fontSizes.xs, color: tokens.colors.textMuted, marginTop: '2px', display: 'block' }}>
                        Semester: {semName} • Dept: {deptName}
                      </span>
                    </div>
                    <span
                      style={{
                        fontSize: tokens.typography.fontSizes.xs,
                        padding: '2px 8px',
                        borderRadius: tokens.radius.sm,
                        backgroundColor: c.status === 'active' ? tokens.colors.status.success.bg : tokens.colors.surfaceAlt,
                        color: c.status === 'active' ? tokens.colors.status.success.color : tokens.colors.textMuted,
                        border: `1px solid ${c.status === 'active' ? tokens.colors.status.success.border : tokens.colors.border}`,
                        textTransform: 'capitalize',
                      }}
                    >
                      {c.status}
                    </span>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </section>

      {/* 3. Class Enrollment & Rosters Section */}
      <section
        aria-labelledby="enrollment-section-heading"
        style={{
          display: 'flex',
          flexDirection: 'column',
          gap: tokens.spacing.lg,
        }}
      >
        <header>
          <h3
            id="enrollment-section-heading"
            style={{
              margin: 0,
              fontSize: tokens.typography.fontSizes.lg,
              fontWeight: tokens.typography.fontWeights.bold,
              color: tokens.colors.textPrimary,
            }}
          >
            Class Enrollment & Rosters
          </h3>
          <p style={{ margin: `${tokens.spacing.xs} 0 0`, fontSize: tokens.typography.fontSizes.sm, color: tokens.colors.textSecondary }}>
            Register students into class sections with attached academic enrollment dates.
          </p>
        </header>

        {/* Enrollment Form */}
        <div
          style={{
            backgroundColor: tokens.colors.surface,
            border: `1px solid ${tokens.colors.border}`,
            borderRadius: `${cardRadius}px`,
            padding: `${cardPadding}px`,
            boxShadow: '0 1px 2px 0 rgba(0, 0, 0, 0.05)',
          }}
        >
          <h4 style={{ margin: `0 0 ${tokens.spacing.sm}`, fontSize: tokens.typography.fontSizes.md, fontWeight: tokens.typography.fontWeights.bold, color: tokens.colors.textPrimary }}>
            Enroll Student in Class
          </h4>

          {enrollSuccess && <StatusMessage status="success" style={{ marginBottom: tokens.spacing.md }}>{enrollSuccess}</StatusMessage>}
          {enrollGeneralError && <StatusMessage status="danger" style={{ marginBottom: tokens.spacing.md }}>{enrollGeneralError}</StatusMessage>}

          <form onSubmit={handleEnrollSubmit} noValidate style={{ display: 'flex', flexDirection: 'column', gap: tokens.spacing.md }}>
            <Select
              id="enroll-class-id"
              label="Class Section"
              value={enrollClassId}
              onChange={(e) => {
                setEnrollClassId(e.target.value);
                onSelectClassForMemberships?.(e.target.value);
              }}
              disabled={enrollSubmitting}
            >
              {classes.map((c) => (
                <option key={c.class_id} value={c.class_id}>
                  {c.code} — {c.name}
                </option>
              ))}
            </Select>

            <Input
              id="enroll-student-id"
              label="Student ID (UUID)"
              value={studentId}
              onChange={(e) => setStudentId(e.target.value)}
              placeholder="e.g. 11111111-2222-3333-4444-555555555555"
              disabled={enrollSubmitting}
            />

            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))', gap: tokens.spacing.md }}>
              <Input
                id="enroll-joined-at"
                label="Joined Date"
                type="date"
                optional
                value={joinedAt}
                onChange={(e) => setJoinedAt(e.target.value)}
                errorMessage={membershipDateErrors.joinedAt}
                description="Defaults to today if left blank."
                disabled={enrollSubmitting}
              />

              <Input
                id="enroll-left-at"
                label="Left Date"
                type="date"
                optional
                value={leftAt}
                onChange={(e) => setLeftAt(e.target.value)}
                errorMessage={membershipDateErrors.leftAt}
                description="Must be at or after the joined date."
                disabled={enrollSubmitting}
              />
            </div>

            <div style={{ marginTop: tokens.spacing.sm }}>
              <Button type="submit" variant="primary" disabled={enrollSubmitting}>
                Enroll in Class
              </Button>
            </div>
          </form>
        </div>

        {/* Memberships Roster for Selected Class */}
        <div>
          <h4 style={{ margin: `0 0 ${tokens.spacing.sm}`, fontSize: tokens.typography.fontSizes.sm, fontWeight: tokens.typography.fontWeights.semibold, color: tokens.colors.textMuted }}>
            Class Enrollment Roster
          </h4>

          {(() => {
            const activeClassId = enrollClassId || classes[0]?.class_id;
            const list = activeClassId ? memberships[activeClassId] || [] : [];
            if (list.length === 0) {
              return (
                <EmptyState
                  title="No Students Currently Enrolled"
                  description="Use the enrollment form above to register students into this class section."
                />
              );
            }
            return (
              <div role="list" aria-label="Class Memberships" style={{ display: 'flex', flexDirection: 'column', gap: tokens.spacing.sm }}>
                {list.map((m, index) => (
                  <div
                    key={m.membership_id || `${m.student_id}-${index}`}
                    role="listitem"
                    style={{
                      backgroundColor: tokens.colors.surface,
                      border: `1px solid ${tokens.colors.border}`,
                      borderRadius: tokens.radius.md,
                      padding: tokens.spacing.md,
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'space-between',
                      boxShadow: '0 1px 2px 0 rgba(0, 0, 0, 0.05)',
                    }}
                  >
                    <div>
                      <strong style={{ fontSize: tokens.typography.fontSizes.sm, color: tokens.colors.textPrimary }}>
                        Student ID: <code>{m.student_id}</code>
                      </strong>
                      <span style={{ fontSize: tokens.typography.fontSizes.xs, color: tokens.colors.textMuted, display: 'block', marginTop: '2px' }}>
                        Joined: {m.joined_at ? new Date(m.joined_at).toLocaleDateString() : 'N/A'}
                        {m.left_at ? ` • Left: ${new Date(m.left_at).toLocaleDateString()}` : ' • Active'}
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            );
          })()}
        </div>
      </section>
    </div>
  );
}
