import { describe, it, expect } from 'vitest';
import fs from 'node:fs';
import path from 'node:path';
import { apiClient } from '../../src/shared/api';

/**
 * OpenAPI Contract Drift & Route Parity Gate (P2-04, P1-02, M-01).
 *
 * Verifies that the frontend typed API client and types adhere strictly
 * to the authoritative OpenAPI v1 contract at contracts/openapi/v1.yaml.
 * Ensures that neither backend nor frontend drifts silently.
 */
describe('OpenAPI Contract Drift & Route Parity Gate (P2-04)', () => {
  const openapiPath = path.resolve(__dirname, '../../../contracts/openapi/v1.yaml');

  it('validates that contracts/openapi/v1.yaml is present and conforms to OpenAPI 3.1', () => {
    expect(fs.existsSync(openapiPath)).toBe(true);
    const rawContent = fs.readFileSync(openapiPath, 'utf-8');
    const spec = JSON.parse(rawContent) as {
      openapi: string;
      info: { title: string; version: string };
      paths: Record<string, unknown>;
      components: { schemas: Record<string, unknown> };
    };

    expect(spec.openapi).toMatch(/^3\.[01]\./);
    expect(spec.info.title).toBe('OpenLibraryOS API');
    expect(spec.paths).toBeDefined();
    expect(Object.keys(spec.paths).length).toBeGreaterThanOrEqual(60);
    expect(spec.components.schemas).toBeDefined();
  });

  it('verifies that every API client endpoint maps to a defined OpenAPI path or documented alias', () => {
    const rawContent = fs.readFileSync(openapiPath, 'utf-8');
    const spec = JSON.parse(rawContent) as {
      paths: Record<string, unknown>;
    };
    const openapiPaths = new Set(Object.keys(spec.paths));

    // Documented aliases also recognized by backend/tests/integration/api/test_openapi_parity.py
    const knownAliases = new Set([
      '/public-library/plans',
      '/public-library/plans/{param}',
      '/public-library/plans/seed',
      '/books/{param}/copies/{param}/status',
      '/books/{param}/copies/{param}/history',
    ]);

    // Read apiClient.ts source code and extract endpoint paths
    const clientPath = path.resolve(__dirname, '../../src/shared/api/apiClient.ts');
    const clientSource = fs.readFileSync(clientPath, 'utf-8');

    // Extract endpoint patterns like get('/foo'), post(`/bar/${param}`), etc.
    const endpointMatches = clientSource.matchAll(
      /(?:get|post|put|patch|delete|request)<[^>]*>\(\s*[`'"](\/[^`'"?]+)/g,
    );

    const clientNormalizedPaths = new Set<string>();
    for (const match of endpointMatches) {
      let rawPath = match[1];
      if (!rawPath) continue;
      // Normalize template interpolations `${...}` to `{param}`
      const normalized = rawPath.replace(/\$\{[^}]+\}/g, '{param}');
      clientNormalizedPaths.add(normalized);
    }

    expect(clientNormalizedPaths.size).toBeGreaterThanOrEqual(30);

    const unmappedEndpoints: string[] = [];

    // Helper to check if client path matches any OpenAPI path
    function isPathSupported(clientEndpoint: string): boolean {
      if (openapiPaths.has(clientEndpoint) || knownAliases.has(clientEndpoint)) {
        return true;
      }
      // Check parameter pattern equivalence: e.g. /books/{book_id} matches /books/{param}
      for (const openPath of openapiPaths) {
        const normalizedOpenPath = openPath.replace(/\{[^}]+\}/g, '{param}');
        if (normalizedOpenPath === clientEndpoint) {
          return true;
        }
      }
      return false;
    }

    for (const endpoint of clientNormalizedPaths) {
      if (!isPathSupported(endpoint)) {
        unmappedEndpoints.push(endpoint);
      }
    }

    expect(unmappedEndpoints).toEqual([]);
  });

  it('verifies that core schema models in contracts/openapi/v1.yaml exist and are defined', () => {
    const rawContent = fs.readFileSync(openapiPath, 'utf-8');
    const spec = JSON.parse(rawContent) as {
      components: { schemas: Record<string, unknown> };
    };
    const schemas = spec.components.schemas;

    const requiredDomainSchemas = [
      'HealthStatus',
      'WorkerHealthStatus',
      'AccessToken',
      'AccessPrincipal',
      'Book',
      'BookCopy',
      'Loan',
      'Reservation',
      'EducationDepartment',
      'EducationStudent',
      'EducationTeacher',
      'EducationBorrowerPolicy',
      'PublicLibraryMember',
      'PublicLibraryFine',
      'PublicLibraryInvoice',
      'PublicLibraryPayment',
    ];

    for (const schemaName of requiredDomainSchemas) {
      expect(schemas[schemaName], `Expected schema "${schemaName}" in OpenAPI spec`).toBeDefined();
    }
  });

  it('verifies that apiClient exports all required functional domain modules', () => {
    expect(apiClient.health).toBeDefined();
    expect(apiClient.auth).toBeDefined();
    expect(apiClient.organizations).toBeDefined();
    expect(apiClient.books).toBeDefined();
    expect(apiClient.locations).toBeDefined();
    expect(apiClient.copies).toBeDefined();
    expect(apiClient.loans).toBeDefined();
    expect(apiClient.reservations).toBeDefined();
    expect(apiClient.notifications).toBeDefined();
    expect(apiClient.education).toBeDefined();
    expect(apiClient.publicLibrary).toBeDefined();
  });
});
