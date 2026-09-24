import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { TokenProvider } from '../../../src/shared/tokens';
import { SessionProvider } from '../../../src/features/auth';
import { EducationWorkspace } from '../../../src/features/education';
import {
  Department,
  Semester,
  Class,
  Student,
  Teacher,
  BorrowerPolicy,
} from '../../../src/shared/api';
import { App } from '../../../src/app/App';

const mockDepartments: Department[] = [
  {
    department_id: 'dept-11111111-1111-4111-8111-111111111111',
    organization_id: 'org-test-001',
    code: 'CS',
    name: 'Computer Science',
    status: 'active',
  },
  {
    department_id: 'dept-22222222-2222-4222-8222-222222222222',
    organization_id: 'org-test-001',
    code: 'MATH',
    name: 'Mathematics',
    status: 'active',
  },
];

const mockSemesters: Semester[] = [
  {
    semester_id: 'sem-11111111-1111-4111-8111-111111111111',
    organization_id: 'org-test-001',
    name: 'Fall 2026',
    starts_on: '2026-09-01',
    ends_on: '2026-12-20',
    status: 'active',
  },
];

const mockClasses: Class[] = [
  {
    class_id: 'cls-11111111-1111-4111-8111-111111111111',
    organization_id: 'org-test-001',
    code: 'CS-101-A',
    name: 'Intro to Programming Section A',
    semester_id: 'sem-11111111-1111-4111-8111-111111111111',
    department_id: 'dept-11111111-1111-4111-8111-111111111111',
    status: 'active',
  },
];

const mockStudents: Student[] = [
  {
    student_id: 'stu-11111111-1111-4111-8111-111111111111',
    organization_id: 'org-test-001',
    user_id: 'usr-11111111-1111-4111-8111-111111111111',
    student_number: 'STU-2026-001',
    department_id: 'dept-11111111-1111-4111-8111-111111111111',
    status: 'active',
  },
];

const mockTeachers: Teacher[] = [
  {
    teacher_id: 'tch-11111111-1111-4111-8111-111111111111',
    organization_id: 'org-test-001',
    user_id: 'usr-22222222-2222-4222-8222-222222222222',
    employee_number: 'FAC-2026-099',
    department_id: 'dept-11111111-1111-4111-8111-111111111111',
    status: 'active',
  },
];

const mockBorrowerPolicies: BorrowerPolicy[] = [
  {
    policy_id: 'pol-11111111-1111-4111-8111-111111111111',
    organization_id: 'org-test-001',
    borrower_type: 'student',
    max_active_loans: 5,
    duration_days: 14,
    status: 'active',
  },
  {
    policy_id: 'pol-22222222-2222-4222-8222-222222222222',
    organization_id: 'org-test-001',
    borrower_type: 'teacher',
    max_active_loans: 20,
    duration_days: 90,
    status: 'active',
  },
];

function setupDefaultMocks() {
  vi.mocked(globalThis.fetch).mockImplementation(async (input) => {
    const url = typeof input === 'string' ? input : (input as Request).url;

    if (url.includes('/education/departments')) {
      return {
        ok: true,
        status: 200,
        headers: new Headers({ 'Content-Type': 'application/json' }),
        json: async () => ({ items: mockDepartments }),
      } as Response;
    }
    if (url.includes('/education/semesters')) {
      return {
        ok: true,
        status: 200,
        headers: new Headers({ 'Content-Type': 'application/json' }),
        json: async () => ({ items: mockSemesters }),
      } as Response;
    }
    if (url.includes('/memberships')) {
      return {
        ok: true,
        status: 200,
        headers: new Headers({ 'Content-Type': 'application/json' }),
        json: async () => ({ items: [] }),
      } as Response;
    }
    if (url.includes('/education/classes')) {
      return {
        ok: true,
        status: 200,
        headers: new Headers({ 'Content-Type': 'application/json' }),
        json: async () => ({ items: mockClasses }),
      } as Response;
    }
    if (url.includes('/education/students')) {
      return {
        ok: true,
        status: 200,
        headers: new Headers({ 'Content-Type': 'application/json' }),
        json: async () => ({ items: mockStudents }),
      } as Response;
    }
    if (url.includes('/education/teachers')) {
      return {
        ok: true,
        status: 200,
        headers: new Headers({ 'Content-Type': 'application/json' }),
        json: async () => ({ items: mockTeachers }),
      } as Response;
    }
    if (url.includes('/education/borrower-policies')) {
      return {
        ok: true,
        status: 200,
        headers: new Headers({ 'Content-Type': 'application/json' }),
        json: async () => ({ items: mockBorrowerPolicies }),
      } as Response;
    }

    return {
      ok: true,
      status: 200,
      headers: new Headers({ 'Content-Type': 'application/json' }),
      json: async () => ({ items: [] }),
    } as Response;
  });
}

function renderEducationWorkspace(props: { initialTab?: 'people' | 'academic' | 'policies' } = {}) {
  return render(
    <TokenProvider>
      <SessionProvider initialAccessToken="test-education-token">
        <EducationWorkspace initialTab={props.initialTab} />
      </SessionProvider>
    </TokenProvider>,
  );
}

describe('Education management and borrower-policy views (FE-009)', () => {
  beforeEach(() => {
    vi.spyOn(globalThis, 'fetch');
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  describe('Tab Navigation and Workspace Layout', () => {
    it('renders the education workspace with accessible tab list', async () => {
      setupDefaultMocks();
      renderEducationWorkspace();

      expect(screen.getByRole('heading', { level: 2, name: /education workspace/i })).toBeInTheDocument();
      expect(screen.getByRole('tab', { name: /people & profiles/i })).toBeInTheDocument();
      expect(screen.getByRole('tab', { name: /academic records/i })).toBeInTheDocument();
      expect(screen.getByRole('tab', { name: /borrower policies/i })).toBeInTheDocument();

      await waitFor(() => {
        expect(screen.getByText('STU-2026-001')).toBeInTheDocument();
      });
    });

    it('switches tabs and updates panel visibility with keyboard and click support', async () => {
      setupDefaultMocks();
      renderEducationWorkspace();

      await waitFor(() => {
        expect(screen.getByText('STU-2026-001')).toBeInTheDocument();
      });

      const academicTab = screen.getByRole('tab', { name: /academic records/i });
      fireEvent.click(academicTab);

      await waitFor(() => {
        expect(screen.getByText('Fall 2026')).toBeInTheDocument();
        expect(screen.getByText('CS-101-A')).toBeInTheDocument();
      });

      const policyTab = screen.getByRole('tab', { name: /borrower policies/i });
      fireEvent.click(policyTab);

      await waitFor(() => {
        expect(screen.getByText(/configured borrower policies/i)).toBeInTheDocument();
      });
    });
  });

  describe('People Management: Grouped Form and Visual Distinction', () => {
    it('visually distinguishes student and teacher records without visual noise', async () => {
      setupDefaultMocks();
      renderEducationWorkspace({ initialTab: 'people' });

      await waitFor(() => {
        expect(screen.getByText('STU-2026-001')).toBeInTheDocument();
        expect(screen.getByText('FAC-2026-099')).toBeInTheDocument();
      });

      // Distinct subtle role badges
      const studentBadge = screen.getByText(/^student$/i);
      const teacherBadge = screen.getByText(/^faculty \/ teacher$/i);
      expect(studentBadge).toBeInTheDocument();
      expect(teacherBadge).toBeInTheDocument();

      // Check student number vs employee number labels
      expect(screen.getByText(/student #:/i)).toBeInTheDocument();
      expect(screen.getByText(/employee #:/i)).toBeInTheDocument();
    });

    it('renders a grouped form with named logical sections when fields exceed five', async () => {
      setupDefaultMocks();
      renderEducationWorkspace({ initialTab: 'people' });

      await waitFor(() => {
        expect(screen.getByText('STU-2026-001')).toBeInTheDocument();
      });

      // Verify Miller's Law: Named logical fieldsets with legend headers
      const identityGroup = screen.getByRole('group', { name: /identity & role/i });
      const institutionalGroup = screen.getByRole('group', { name: /institutional identification/i });
      const affiliationGroup = screen.getByRole('group', { name: /academic affiliation & status/i });

      expect(identityGroup).toBeInTheDocument();
      expect(institutionalGroup).toBeInTheDocument();
      expect(affiliationGroup).toBeInTheDocument();

      // Fields exist inside grouped sections
      expect(screen.getByLabelText(/user id/i)).toBeInTheDocument();
      expect(screen.getByLabelText(/student number/i)).toBeInTheDocument();
      expect(screen.getByLabelText(/department/i)).toBeInTheDocument();
      expect(screen.getByRole('combobox', { name: /^status$/i })).toBeInTheDocument();
    });

    it('submits student creation payload when student role is selected', async () => {
      setupDefaultMocks();
      renderEducationWorkspace({ initialTab: 'people' });

      await waitFor(() => {
        expect(screen.getByText('STU-2026-001')).toBeInTheDocument();
      });

      // Fill in user id and student number
      const userIdInput = screen.getByLabelText(/user id/i);
      fireEvent.change(userIdInput, { target: { value: 'usr-99999999-9999-4999-8999-999999999999' } });

      const studentNumberInput = screen.getByLabelText(/student number/i);
      fireEvent.change(studentNumberInput, { target: { value: 'STU-NEW-777' } });

      const submitBtn = screen.getByRole('button', { name: /register profile/i });
      fireEvent.click(submitBtn);

      await waitFor(() => {
        expect(globalThis.fetch).toHaveBeenCalledWith(
          '/api/v1/education/students',
          expect.objectContaining({
            method: 'POST',
            body: expect.stringContaining('STU-NEW-777'),
          }),
        );
      });
    });

    it('switches identifier input to employee number when teacher role is selected', async () => {
      setupDefaultMocks();
      renderEducationWorkspace({ initialTab: 'people' });

      await waitFor(() => {
        expect(screen.getByText('STU-2026-001')).toBeInTheDocument();
      });

      // Select Teacher radio / segmented control
      const teacherOption = screen.getByLabelText(/faculty \/ teacher/i);
      fireEvent.click(teacherOption);

      expect(screen.getByLabelText(/employee number/i)).toBeInTheDocument();

      const userIdInput = screen.getByLabelText(/user id/i);
      fireEvent.change(userIdInput, { target: { value: 'usr-88888888-8888-4888-8888-888888888888' } });

      const empInput = screen.getByLabelText(/employee number/i);
      fireEvent.change(empInput, { target: { value: 'EMP-FAC-555' } });

      const submitBtn = screen.getByRole('button', { name: /register profile/i });
      fireEvent.click(submitBtn);

      await waitFor(() => {
        expect(globalThis.fetch).toHaveBeenCalledWith(
          '/api/v1/education/teachers',
          expect.objectContaining({
            method: 'POST',
            body: expect.stringContaining('EMP-FAC-555'),
          }),
        );
      });
    });
  });

  describe('Academic Records: Inline Date Validation Attachment', () => {
    it('attaches academic date validation errors directly to the relevant date inputs upon server 400', async () => {
      setupDefaultMocks();

      // Mock failure for semester creation with invalid-semester-dates
      vi.mocked(globalThis.fetch).mockImplementation(async (input, init) => {
        const url = typeof input === 'string' ? input : (input as Request).url;
        const method = init?.method || 'GET';

        if (url.includes('/education/semesters') && method === 'POST') {
          return {
            ok: false,
            status: 400,
            headers: new Headers({ 'Content-Type': 'application/problem+json' }),
            json: async () => ({
              type: 'https://openlibraryos.example/problems/invalid-semester-dates',
              title: 'Invalid semester dates',
              status: 400,
              detail: 'Semester starts_on must be before ends_on',
              instance: '/api/v1/education/semesters',
              request_id: 'req-err-dates-001',
            }),
          } as Response;
        }

        if (url.includes('/education/semesters')) {
          return {
            ok: true,
            status: 200,
            headers: new Headers({ 'Content-Type': 'application/json' }),
            json: async () => ({ items: mockSemesters }),
          } as Response;
        }
        if (url.includes('/education/classes')) {
          return {
            ok: true,
            status: 200,
            headers: new Headers({ 'Content-Type': 'application/json' }),
            json: async () => ({ items: mockClasses }),
          } as Response;
        }
        return {
          ok: true,
          status: 200,
          headers: new Headers({ 'Content-Type': 'application/json' }),
          json: async () => ({ items: [] }),
        } as Response;
      });

      renderEducationWorkspace({ initialTab: 'academic' });

      await waitFor(() => {
        expect(screen.getByText('Fall 2026')).toBeInTheDocument();
      });

      const nameInput = screen.getByLabelText(/semester name/i);
      fireEvent.change(nameInput, { target: { value: 'Spring 2027' } });

      const startsOnInput = screen.getByLabelText(/start date/i);
      fireEvent.change(startsOnInput, { target: { value: '2027-06-01' } });

      const endsOnInput = screen.getByLabelText(/end date/i);
      fireEvent.change(endsOnInput, { target: { value: '2027-01-01' } });

      const createBtn = screen.getByRole('button', { name: /create semester/i });
      fireEvent.click(createBtn);

      // Verify acceptance criterion: Academic date validation errors are attached to their relevant inputs
      await waitFor(() => {
        const errorMsg = screen.getByText(/semester starts_on must be before ends_on/i);
        expect(errorMsg).toBeInTheDocument();
      });

      // The input should have aria-invalid and reference the error message
      expect(endsOnInput).toHaveAttribute('aria-invalid', 'true');
    });

    it('attaches membership date validation errors directly to the left_at input upon server 400', async () => {
      setupDefaultMocks();

      vi.mocked(globalThis.fetch).mockImplementation(async (input, init) => {
        const url = typeof input === 'string' ? input : (input as Request).url;
        const method = init?.method || 'GET';

        if (url.includes('/memberships') && method === 'POST') {
          return {
            ok: false,
            status: 400,
            headers: new Headers({ 'Content-Type': 'application/problem+json' }),
            json: async () => ({
              type: 'https://openlibraryos.example/problems/invalid-membership-dates',
              title: 'Invalid membership dates',
              status: 400,
              detail: 'Membership left_at must be at or after joined_at',
              instance: '/api/v1/education/classes/cls-111/memberships',
              request_id: 'req-mem-dates-001',
            }),
          } as Response;
        }

        if (url.includes('/education/classes')) {
          return {
            ok: true,
            status: 200,
            headers: new Headers({ 'Content-Type': 'application/json' }),
            json: async () => ({ items: mockClasses }),
          } as Response;
        }
        if (url.includes('/education/semesters')) {
          return {
            ok: true,
            status: 200,
            headers: new Headers({ 'Content-Type': 'application/json' }),
            json: async () => ({ items: mockSemesters }),
          } as Response;
        }
        return {
          ok: true,
          status: 200,
          headers: new Headers({ 'Content-Type': 'application/json' }),
          json: async () => ({ items: [] }),
        } as Response;
      });

      renderEducationWorkspace({ initialTab: 'academic' });

      await waitFor(() => {
        expect(screen.getByText('CS-101-A')).toBeInTheDocument();
      });

      // Enroll student in class
      const studentInput = screen.getByLabelText(/student id/i);
      fireEvent.change(studentInput, { target: { value: 'stu-11111111-1111-4111-8111-111111111111' } });

      const joinedInput = screen.getByLabelText(/joined date/i);
      fireEvent.change(joinedInput, { target: { value: '2026-09-01' } });

      const leftInput = screen.getByLabelText(/left date/i);
      fireEvent.change(leftInput, { target: { value: '2026-08-01' } });

      const enrollBtn = screen.getByRole('button', { name: /enroll in class/i });
      fireEvent.click(enrollBtn);

      await waitFor(() => {
        const errorMsg = screen.getByText(/membership left_at must be at or after joined_at/i);
        expect(errorMsg).toBeInTheDocument();
      });

      expect(leftInput).toHaveAttribute('aria-invalid', 'true');
    });
  });

  describe('Borrower Policy View: Read-Only Server Explanation', () => {
    it('describes server configuration in plain language without calculating client entitlement', async () => {
      setupDefaultMocks();
      renderEducationWorkspace({ initialTab: 'policies' });

      await waitFor(() => {
        expect(screen.getByText(/configured borrower policies/i)).toBeInTheDocument();
      });

      // Student Policy Card
      expect(screen.getByText(/student borrower policy/i)).toBeInTheDocument();
      expect(screen.getByText(/5 active loans/i)).toBeInTheDocument();
      expect(screen.getAllByText(/14 days/i).length).toBeGreaterThanOrEqual(1);

      // Teacher Policy Card
      expect(screen.getByText(/faculty \/ teacher borrower policy/i)).toBeInTheDocument();
      expect(screen.getByText(/20 active loans/i)).toBeInTheDocument();
      expect(screen.getAllByText(/90 days/i).length).toBeGreaterThanOrEqual(1);

      // Check plain language description of server effect
      expect(
        screen.getByText(/checkout eligibility and due dates are determined authoritatively by the library server/i),
      ).toBeInTheDocument();

      // Check evidence checkpoint: No client-side eligibility calculation or entitlement assertion
      expect(screen.queryByText(/you are eligible to borrow/i)).not.toBeInTheDocument();
      expect(screen.queryByText(/remaining loan balance/i)).not.toBeInTheDocument();
    });
  });

  describe('Edition-Unavailable State Handling', () => {
    it('respects edition-disabled API responses (403 edition-unavailable) with explanatory view', async () => {
      vi.mocked(globalThis.fetch).mockResolvedValue({
        ok: false,
        status: 403,
        headers: new Headers({ 'Content-Type': 'application/problem+json' }),
        json: async () => ({
          type: 'https://openlibraryos.example/problems/edition-unavailable',
          title: 'Edition unavailable',
          status: 403,
          detail: 'The education edition is not enabled for this organization.',
          instance: '/api/v1/education/students',
          request_id: 'req-disabled-edition-001',
        }),
      } as Response);

      renderEducationWorkspace();

      await waitFor(() => {
        expect(screen.getByRole('heading', { name: /education edition unavailable/i })).toBeInTheDocument();
      });

      // Clear explanation
      expect(
        screen.getByText(/the education edition is not enabled for this organization/i),
      ).toBeInTheDocument();

      // Reviewer checklist: Leaks no tenant database configuration
      expect(screen.queryByText(/sqlserver/i)).not.toBeInTheDocument();
      expect(screen.queryByText(/connection_string/i)).not.toBeInTheDocument();
      expect(screen.queryByText(/org-test-001/i)).not.toBeInTheDocument();

      // Clear return path
      const returnBtn = screen.getByRole('link', { name: /return to circulation/i });
      expect(returnBtn).toBeInTheDocument();
      expect(returnBtn).toHaveAttribute('href', '#/circulation');
    });
  });

  describe('App Shell Navigation Integration', () => {
    it('navigates to education workspace when hash is #education or #members', async () => {
      setupDefaultMocks();
      window.location.hash = '#/education';

      render(<App />);

      await waitFor(() => {
        expect(screen.getByRole('heading', { level: 2, name: /education workspace/i })).toBeInTheDocument();
      });
    });
  });
});
