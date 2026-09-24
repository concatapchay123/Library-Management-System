import React, { useState } from 'react';
import { useTokens, calcNestedRadius } from '../../shared/tokens';
import { PeopleManagerProps, PersonRole } from './types';
import { Input, Select, Button, StatusMessage, LoadingSkeleton, EmptyState } from '../../shared/components';

/**
 * People and Profiles Management (FE-009).
 *
 * Implements acceptance criteria and design invariants:
 * - Visually distinguishes student and teacher records without separate visual noise.
 * - Adheres to Miller's Law (Chunking): Groups forms with >5 fields into named logical sections
 *   (Identity & Role, Institutional Identification, Academic Affiliation & Status).
 * - Single-column vertical form flow, semantic spacing progression (12px/24px/32px).
 * - Actionable search placeholder ("Search by student number, employee number, or user ID...").
 */
export function PeopleManager({
  departments,
  students,
  teachers,
  isLoading = false,
  onRegisterStudent,
  onRegisterTeacher,
}: PeopleManagerProps) {
  const tokens = useTokens();

  // Role toggle
  const [selectedRole, setSelectedRole] = useState<PersonRole>('student');

  // Form fields
  const [userId, setUserId] = useState('');
  const [identifier, setIdentifier] = useState('');
  const [departmentId, setDepartmentId] = useState('');
  const [status, setStatus] = useState('active');

  // Filter / Search
  const [searchQuery, setSearchQuery] = useState('');

  // Form state
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [formSuccess, setFormSuccess] = useState<string | null>(null);

  const [fieldErrors, setFieldErrors] = useState<{
    userId?: string;
    identifier?: string;
  }>({});

  const cardRadius = 10;
  const cardPadding = 20;
  const innerRadius = calcNestedRadius(cardRadius, cardPadding);

  // Department lookup map
  const departmentMap = new Map(departments.map((d) => [d.department_id, d.name]));

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setFormError(null);
    setFormSuccess(null);

    const errors: { userId?: string; identifier?: string } = {};
    if (!userId.trim()) {
      errors.userId = 'User ID is required';
    }
    if (!identifier.trim()) {
      errors.identifier = selectedRole === 'student' ? 'Student number is required' : 'Employee number is required';
    }

    if (Object.keys(errors).length > 0) {
      setFieldErrors(errors);
      return;
    }
    setFieldErrors({});

    setIsSubmitting(true);
    try {
      if (selectedRole === 'student') {
        await onRegisterStudent({
          user_id: userId.trim(),
          student_number: identifier.trim(),
          department_id: departmentId.trim() || null,
          status: status.trim() || 'active',
        });
        setFormSuccess(`Student profile for "${identifier.trim()}" registered successfully.`);
      } else {
        await onRegisterTeacher({
          user_id: userId.trim(),
          employee_number: identifier.trim(),
          department_id: departmentId.trim() || null,
          status: status.trim() || 'active',
        });
        setFormSuccess(`Teacher profile for "${identifier.trim()}" registered successfully.`);
      }

      // Reset form
      setUserId('');
      setIdentifier('');
      setDepartmentId('');
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Failed to register profile';
      setFormError(msg);
    } finally {
      setIsSubmitting(false);
    }
  };

  // Combine and filter people records
  type PersonListItem =
    | { type: 'student'; id: string; user_id: string; number: string; dept_id: string | null | undefined; status: string }
    | { type: 'teacher'; id: string; user_id: string; number: string; dept_id: string | null | undefined; status: string };

  const allPeople: PersonListItem[] = [
    ...students.map((s) => ({
      type: 'student' as const,
      id: s.student_id,
      user_id: s.user_id,
      number: s.student_number,
      dept_id: s.department_id,
      status: s.status,
    })),
    ...teachers.map((t) => ({
      type: 'teacher' as const,
      id: t.teacher_id,
      user_id: t.user_id,
      number: t.employee_number,
      dept_id: t.department_id,
      status: t.status,
    })),
  ];

  const filteredPeople = allPeople.filter((p) => {
    if (!searchQuery.trim()) return true;
    const q = searchQuery.toLowerCase();
    return (
      p.number.toLowerCase().includes(q) ||
      p.user_id.toLowerCase().includes(q) ||
      (p.dept_id && (departmentMap.get(p.dept_id) || '').toLowerCase().includes(q))
    );
  });

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: tokens.spacing.xl }}>
      {/* 1. Grouped Registration Form (> 5 fields chunked according to Miller's Law) */}
      <section
        aria-labelledby="register-profile-heading"
        style={{
          backgroundColor: tokens.colors.surface,
          border: `1px solid ${tokens.colors.border}`,
          borderRadius: `${cardRadius}px`,
          padding: `${cardPadding}px`,
          boxShadow: '0 1px 2px 0 rgba(0, 0, 0, 0.05)',
        }}
      >
        <header style={{ marginBottom: tokens.spacing.lg }}>
          <h3
            id="register-profile-heading"
            style={{
              margin: 0,
              fontSize: tokens.typography.fontSizes.lg,
              fontWeight: tokens.typography.fontWeights.bold,
              color: tokens.colors.textPrimary,
            }}
          >
            Register Academic Profile
          </h3>
          <p
            style={{
              margin: `${tokens.spacing.xs} 0 0`,
              fontSize: tokens.typography.fontSizes.sm,
              color: tokens.colors.textSecondary,
            }}
          >
            Assign institutional student or faculty identifiers to link tenant users with educational borrowing privileges.
          </p>
        </header>

        {formSuccess && (
          <StatusMessage
            status="success"
            style={{ marginBottom: tokens.spacing.lg }}
          >
            {formSuccess}
          </StatusMessage>
        )}

        {formError && (
          <StatusMessage
            status="danger"
            style={{ marginBottom: tokens.spacing.lg }}
          >
            {formError}
          </StatusMessage>
        )}

        <form onSubmit={handleSubmit} noValidate style={{ display: 'flex', flexDirection: 'column', gap: tokens.spacing.lg }}>
          {/* Section 1: Identity & Role */}
          <fieldset
            aria-labelledby="legend-identity"
            style={{
              border: `1px solid ${tokens.colors.border}`,
              borderRadius: `${innerRadius}px`,
              padding: tokens.spacing.md,
              margin: 0,
              display: 'flex',
              flexDirection: 'column',
              gap: tokens.spacing.md,
            }}
          >
            <legend
              id="legend-identity"
              style={{
                fontSize: tokens.typography.fontSizes.sm,
                fontWeight: tokens.typography.fontWeights.bold,
                color: tokens.colors.textPrimary,
                padding: `0 ${tokens.spacing.xs}`,
              }}
            >
              Identity & Role
            </legend>

            <div>
              <span
                style={{
                  display: 'block',
                  fontSize: tokens.typography.fontSizes.sm,
                  fontWeight: tokens.typography.fontWeights.semibold,
                  color: tokens.colors.textPrimary,
                  marginBottom: tokens.spacing.xs,
                }}
              >
                Profile Role
              </span>
              <div
                role="radiogroup"
                aria-label="Profile Role"
                style={{
                  display: 'inline-flex',
                  gap: tokens.spacing.xs,
                  padding: '4px',
                  backgroundColor: tokens.colors.surfaceAlt,
                  borderRadius: tokens.radius.md,
                  border: `1px solid ${tokens.colors.border}`,
                }}
              >
                <label
                  style={{
                    display: 'inline-flex',
                    alignItems: 'center',
                    gap: tokens.spacing.xs,
                    padding: `${tokens.buttonSpacing.sm.py} ${tokens.buttonSpacing.sm.px}`,
                    borderRadius: tokens.radius.sm,
                    backgroundColor: selectedRole === 'student' ? tokens.colors.surface : 'transparent',
                    color: selectedRole === 'student' ? tokens.colors.primary : tokens.colors.textSecondary,
                    fontWeight: selectedRole === 'student' ? tokens.typography.fontWeights.semibold : tokens.typography.fontWeights.normal,
                    cursor: 'pointer',
                    boxShadow: selectedRole === 'student' ? '0 1px 2px 0 rgba(0, 0, 0, 0.05)' : 'none',
                    border: `1px solid ${selectedRole === 'student' ? tokens.colors.primary : 'transparent'}`,
                  }}
                >
                  <input
                    type="radio"
                    name="profile-role"
                    value="student"
                    checked={selectedRole === 'student'}
                    onChange={() => {
                      setSelectedRole('student');
                      setFieldErrors({});
                    }}
                    style={{ position: 'absolute', opacity: 0, pointerEvents: 'none' }}
                  />
                  🎓 Student
                </label>

                <label
                  style={{
                    display: 'inline-flex',
                    alignItems: 'center',
                    gap: tokens.spacing.xs,
                    padding: `${tokens.buttonSpacing.sm.py} ${tokens.buttonSpacing.sm.px}`,
                    borderRadius: tokens.radius.sm,
                    backgroundColor: selectedRole === 'teacher' ? tokens.colors.surface : 'transparent',
                    color: selectedRole === 'teacher' ? tokens.colors.primary : tokens.colors.textSecondary,
                    fontWeight: selectedRole === 'teacher' ? tokens.typography.fontWeights.semibold : tokens.typography.fontWeights.normal,
                    cursor: 'pointer',
                    boxShadow: selectedRole === 'teacher' ? '0 1px 2px 0 rgba(0, 0, 0, 0.05)' : 'none',
                    border: `1px solid ${selectedRole === 'teacher' ? tokens.colors.primary : 'transparent'}`,
                  }}
                >
                  <input
                    type="radio"
                    name="profile-role"
                    value="teacher"
                    checked={selectedRole === 'teacher'}
                    onChange={() => {
                      setSelectedRole('teacher');
                      setFieldErrors({});
                    }}
                    style={{ position: 'absolute', opacity: 0, pointerEvents: 'none' }}
                  />
                  💼 Faculty / Teacher
                </label>
              </div>
            </div>

            <Input
              id="person-user-id"
              label="User ID (UUID)"
              value={userId}
              onChange={(e) => setUserId(e.target.value)}
              placeholder="e.g. 550e8400-e29b-41d4-a716-446655440000"
              errorMessage={fieldErrors.userId}
              disabled={isSubmitting}
            />
          </fieldset>

          {/* Section 2: Institutional Identification */}
          <fieldset
            aria-labelledby="legend-institutional"
            style={{
              border: `1px solid ${tokens.colors.border}`,
              borderRadius: `${innerRadius}px`,
              padding: tokens.spacing.md,
              margin: 0,
              display: 'flex',
              flexDirection: 'column',
              gap: tokens.spacing.md,
            }}
          >
            <legend
              id="legend-institutional"
              style={{
                fontSize: tokens.typography.fontSizes.sm,
                fontWeight: tokens.typography.fontWeights.bold,
                color: tokens.colors.textPrimary,
                padding: `0 ${tokens.spacing.xs}`,
              }}
            >
              Institutional Identification
            </legend>

            <Input
              id="person-identifier"
              label={selectedRole === 'student' ? 'Student Number' : 'Employee Number'}
              value={identifier}
              onChange={(e) => setIdentifier(e.target.value)}
              placeholder={selectedRole === 'student' ? 'e.g. STU-2026-0042' : 'e.g. EMP-FAC-108'}
              errorMessage={fieldErrors.identifier}
              description={
                selectedRole === 'student'
                  ? 'Unique institutional matriculation or student card code.'
                  : 'Institutional faculty or staff payroll identifier.'
              }
              disabled={isSubmitting}
            />
          </fieldset>

          {/* Section 3: Academic Affiliation & Status */}
          <fieldset
            aria-labelledby="legend-affiliation"
            style={{
              border: `1px solid ${tokens.colors.border}`,
              borderRadius: `${innerRadius}px`,
              padding: tokens.spacing.md,
              margin: 0,
              display: 'flex',
              flexDirection: 'column',
              gap: tokens.spacing.md,
            }}
          >
            <legend
              id="legend-affiliation"
              style={{
                fontSize: tokens.typography.fontSizes.sm,
                fontWeight: tokens.typography.fontWeights.bold,
                color: tokens.colors.textPrimary,
                padding: `0 ${tokens.spacing.xs}`,
              }}
            >
              Academic Affiliation & Status
            </legend>

            <Select
              id="person-department"
              label="Department"
              optional
              value={departmentId}
              onChange={(e) => setDepartmentId(e.target.value)}
              disabled={isSubmitting}
            >
              <option key="none" value="">No Department Assigned (General / Undecided)</option>
              {departments.map((d) => (
                <option key={d.department_id} value={d.department_id}>
                  {d.name} ({d.code})
                </option>
              ))}
            </Select>

            <Select
              id="person-status"
              label="Status"
              value={status}
              onChange={(e) => setStatus(e.target.value)}
              disabled={isSubmitting}
            >
              <option key="active" value="active">Active</option>
              <option key="inactive" value="inactive">Inactive</option>
              <option key="on_leave" value="on_leave">On Leave</option>
              <option key="graduated" value="graduated">Graduated / Alumni</option>
            </Select>
          </fieldset>

          {/* Submit Button */}
          <div style={{ marginTop: tokens.spacing.sm }}>
            <Button
              type="submit"
              variant="primary"
              disabled={isSubmitting}
            >
              Register Profile
            </Button>
          </div>
        </form>
      </section>

      {/* 2. Registered People Directory */}
      <section
        aria-labelledby="people-directory-heading"
        style={{
          display: 'flex',
          flexDirection: 'column',
          gap: tokens.spacing.md,
        }}
      >
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: tokens.spacing.sm }}>
          <div>
            <h3
              id="people-directory-heading"
              style={{
                margin: 0,
                fontSize: tokens.typography.fontSizes.lg,
                fontWeight: tokens.typography.fontWeights.bold,
                color: tokens.colors.textPrimary,
              }}
            >
              Academic Profiles Directory
            </h3>
            <p
              style={{
                margin: `${tokens.spacing.xs} 0 0`,
                fontSize: tokens.typography.fontSizes.sm,
                color: tokens.colors.textSecondary,
              }}
            >
              {allPeople.length} registered profiles ({students.length} students, {teachers.length} teachers).
            </p>
          </div>

          <div style={{ width: '100%', maxWidth: '360px' }}>
            <Input
              id="people-search"
              label="Filter Profiles"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search by student number, employee number, or user ID..."
            />
          </div>
        </div>

        {isLoading ? (
          <div style={{ display: 'flex', flexDirection: 'column', gap: tokens.spacing.sm }}>
            <LoadingSkeleton height={60} />
            <LoadingSkeleton height={60} />
            <LoadingSkeleton height={60} />
          </div>
        ) : filteredPeople.length === 0 ? (
          <EmptyState
            title="No Academic Profiles Found"
            description={
              searchQuery
                ? `No profiles matching "${searchQuery}". Try adjusting your search query.`
                : 'No student or teacher profiles have been registered yet for this organization.'
            }
          />
        ) : (
          <div
            role="list"
            aria-label="Academic Profiles"
            style={{
              display: 'flex',
              flexDirection: 'column',
              gap: tokens.spacing.sm,
            }}
          >
            {filteredPeople.map((p) => {
              const isStudent = p.type === 'student';
              const deptName = p.dept_id ? departmentMap.get(p.dept_id) || 'Unknown Dept' : 'Unassigned';

              return (
                <div
                  key={`${p.type}-${p.id}`}
                  role="listitem"
                  style={{
                    backgroundColor: tokens.colors.surface,
                    border: `1px solid ${tokens.colors.border}`,
                    borderRadius: `${tokens.radius.md}`,
                    padding: `${tokens.spacing.md} ${tokens.spacing.lg}`,
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    gap: tokens.spacing.md,
                    flexWrap: 'wrap',
                    boxShadow: '0 1px 2px 0 rgba(0, 0, 0, 0.05)',
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', gap: tokens.spacing.md }}>
                    {/* Visual Role Distinction: Distinct badge without visual clutter */}
                    <span
                      style={{
                        display: 'inline-flex',
                        alignItems: 'center',
                        fontSize: tokens.typography.fontSizes.xs,
                        fontWeight: tokens.typography.fontWeights.semibold,
                        padding: '3px 10px',
                        borderRadius: `${innerRadius}px`,
                        backgroundColor: isStudent ? tokens.colors.status.info.bg : tokens.colors.surfaceElevated,
                        color: isStudent ? tokens.colors.status.info.color : tokens.colors.primary,
                        border: `1px solid ${isStudent ? tokens.colors.status.info.border : tokens.colors.primary}`,
                      }}
                    >
                      {isStudent ? 'Student' : 'Faculty / Teacher'}
                    </span>

                    <div>
                      <div style={{ display: 'flex', alignItems: 'center', gap: tokens.spacing.sm }}>
                        <span style={{ fontSize: tokens.typography.fontSizes.sm, color: tokens.colors.textMuted }}>
                          {isStudent ? 'Student #:' : 'Employee #:'}
                        </span>
                        <strong style={{ fontSize: tokens.typography.fontSizes.md, color: tokens.colors.textPrimary }}>
                          {p.number}
                        </strong>
                      </div>
                      <div style={{ fontSize: tokens.typography.fontSizes.xs, color: tokens.colors.textMuted, marginTop: '2px' }}>
                        User ID: <code>{p.user_id}</code> • Dept: {deptName}
                      </div>
                    </div>
                  </div>

                  <div style={{ display: 'flex', alignItems: 'center', gap: tokens.spacing.md }}>
                    <span
                      style={{
                        fontSize: tokens.typography.fontSizes.xs,
                        padding: '2px 8px',
                        borderRadius: tokens.radius.sm,
                        backgroundColor: p.status === 'active' ? tokens.colors.status.success.bg : tokens.colors.surfaceAlt,
                        color: p.status === 'active' ? tokens.colors.status.success.color : tokens.colors.textMuted,
                        border: `1px solid ${p.status === 'active' ? tokens.colors.status.success.border : tokens.colors.border}`,
                        textTransform: 'capitalize',
                      }}
                    >
                      {p.status}
                    </span>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </section>
    </div>
  );
}
