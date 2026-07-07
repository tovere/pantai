---
name: crud-generator
description: This skill should be used when generating or refactoring standard CRUD modules for apps/web-ele, including API types/functions, route modules, list pages, form modal schemas, enum dictionaries, and mock endpoints with consistent project conventions.
---

# CRUD Generator

## Overview

Standardize CRUD module generation for `apps/web-ele`.
Generate complete module scaffolding that stays consistent with existing Vben Admin Element Plus conventions for API contracts, route naming, table/form behavior, loading states, and error handling.

Load `references/crud-generator-rules.md` before implementation when request includes new CRUD modules, batch CRUD migration, or fixing inconsistent module structure.

## Trigger Conditions

Trigger this skill when user intent includes one or more of the following:

- Generate a new CRUD module from field definitions
- Build list/detail/create/update/delete code in one pass
- Add table + search + form modal for management pages
- Generate API file + route module + view files + mock endpoint together
- Normalize legacy module code to unified CRUD pattern
- Add enum dictionary files and status-tag rendering patterns

## Workflow

### 1) Confirm Module Input Contract

Collect and normalize:

- `moduleName` (中文业务名)
- `modulePath` (路由/API 路径片段)
- `moduleCode` (PascalCase 代码名)
- `fields[]` (type/label/search/table/form/enum/validation)
- `permissions[]` (list/add/edit/delete)

If user input is incomplete, infer from nearest existing modules in `apps/web-ele/src/views` and `apps/web-ele/src/api`, then keep naming consistent.

### 2) Generate API + Types First

Create API module under `apps/web-ele/src/api` and keep function/type naming deterministic:

- `get${ModuleCode}ListApi`
- `get${ModuleCode}DetailApi`
- `create${ModuleCode}Api`
- `update${ModuleCode}Api`
- `delete${ModuleCode}Api`
- `batchDelete${ModuleCode}Api`

Use typed params and response data. Keep request implementation aligned with project request client wrapper.

### 3) Generate View Layer (Table + Search + Form)

Create list page and form modal under `apps/web-ele/src/views/${modulePath}`:

- Table: Use `useVbenVxeGrid` to create `<Grid>` component with columns from `table: true`
- Search: fields with `search: true`
- Form schema: fields with `form: true`
- Enum fields: tag slot rendering + select options
- Operations: add/edit/delete/batch-delete handlers using `gridApi.reload()` and `gridApi.getCheckboxRecords()`

Apply loading guards and predictable state transitions.

### 4) Generate Route and Optional Dict/Mock

- Route module: `apps/web-ele/src/router/routes/modules/${modulePath}.ts`
- Enum dictionary: `apps/web-ele/src/dict/${modulePath}.ts` when enum exists
- Mock endpoint module: align with current web-ele mock conventions (not backend-mock style)

### 5) Validate Consistency

Check all generated files for:

- Naming consistency (`modulePath` / `moduleCode`)
- Response and pagination shape consistency
- Authority code consistency
- Form validation consistency with field metadata
- Error handling and loading state completeness

## Output Contract

When applying this skill, produce:

1. Target file list (API / route / view / dict / mock)
2. Complete content for newly created files
3. Minimal diffs for modified existing files
4. Brief validation checklist (API shape, form validation, table behavior, permissions)

## Guardrails

- Do not introduce backend-mock style handlers for new web-ele mock files.
- Do not use `any`, `@ts-ignore`, or `@ts-expect-error` in generated TypeScript.
- Do not change existing API path contracts unless explicitly required.
- Do not alter unrelated modules when generating a single CRUD module.

## Resources

Use the following reference as source of truth:

- `references/crud-generator-rules.md`
- `../../docs/rules/crud-module.md`

