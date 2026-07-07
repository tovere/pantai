---
name: mockjs-web-ele
description: This skill should be used when creating, migrating, or fixing MockJS APIs in apps/web-ele/mock for the Vben Admin Element Plus app, especially when replacing legacy backend-mock style rules with the current web-ele mockjs conventions.
---

# Mockjs Web Ele

## Overview

Standardize MockJS development for `apps/web-ele/mock`.
Generate module mocks that match existing project patterns for response shape, auth checks, pagination, URL matching, and CRUD handlers.

Load `references/mock-rules.md` before implementation when the request involves new endpoints, migration from legacy backend-mock, or troubleshooting invalid mock behavior.

## Trigger Conditions

Trigger this skill when user intent includes one or more of the following:

- Create a new mock module under `apps/web-ele/mock/*.ts`
- Add list/detail/create/update/delete mock handlers
- Migrate from legacy `backend-mock` conventions to `web-ele/mock` conventions
- Fix inconsistent response payloads (`code/data/error/message`)
- Add auth checks using `checkAuth()` for protected APIs
- Add pagination/filtering/path-params parsing for list/detail endpoints

## Workflow

### 1) Discover Current Module Pattern
Inspect existing files in `apps/web-ele/mock` and choose the closest module pattern:

- Resource-like CRUD: `banner.ts`, `system.ts`
- User-centric subresources: `user.ts`
- Auth/session related: `auth.ts`
- Utility/common APIs: `common.ts`

Reuse helper functions from `_utils.ts` and avoid introducing a parallel response standard.

### 2) Align Global Mock Entry and Scope
Keep module files inside `apps/web-ele/mock` and ensure global setup remains in `apps/web-ele/mock/index.ts`.
Only add `import './<module>'` in `index.ts` when creating a brand-new module file.

### 3) Apply Endpoint Implementation Standard
For each endpoint:

- Match URL using `Mock.mock(/.../, '<method>', handler)`
- Parse query by `getQueryParams(options.url)`
- Parse path params by `extractPathParams(options.url, '/api/x/:id')`
- Use `checkAuth()` for protected endpoints
- Return success via `responseSuccess(data)` or `pageResponseSuccess(items, total)`
- Return failures via `responseError(message, error?)`
- Use in-memory array updates for CRUD mutation simulation

### 4) Respect Data and Behavior Conventions
- Use `Mock.Random` to generate realistic Chinese-oriented demo data where appropriate.
- Keep response shape exactly:
  - success: `{ code: 0, data, error: null, message: 'ok' }`
  - error: `{ code: -1, data: null, error, message }`
- Keep pagination shape under `data`: `{ items, total }`.
- Prefer deterministic filtering and pagination over random list length changes within one request.

### 5) Migration Rule (Legacy backend-mock -> web-ele/mock)
When request mentions backend-mock migration:

- Remove Nitro-style server assumptions
- Convert handler logic into `Mock.mock(...)` declarations
- Replace legacy response wrapper calls with `_utils.ts` wrappers
- Keep endpoint path compatibility unless user explicitly requests path changes

## Output Contract

When applying this skill, produce:

1. Target file list under `apps/web-ele/mock`
2. Complete file content for newly created module(s)
3. Minimal diffs for touched existing files (`index.ts` import, shared helper adjustments)
4. Brief validation checklist (response shape, auth, pagination, filters)

## Guardrails

- Do not use `apps/backend-mock` patterns for new implementation.
- Do not introduce `any` in new TypeScript when concrete types are feasible.
- Do not alter unrelated modules in `apps/web-ele/mock`.
- Do not change API paths without explicit requirement.

## Resources

Use the following reference file as the source of truth for coding patterns:

- `references/mock-rules.md`

Delete unused generated sample resources and keep this skill lean.
