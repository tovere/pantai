## 2026-02-25 Context Initialization
- Existing global pages under `views/perf/requirement|bug|me/issues` are basic table-only and read-only.
- Rich workflow patterns exist in `views/perf/project/requirements.vue` and `views/perf/project/bugs.vue`.
- Reuse `PageShell`, `StatusTag`, `EmployeeSelect`, and `constants.ts` option maps.

## 2026-02-25 Module Upgrade Pass
- `me/issues.vue` switched to employee-first dashboard with KPI cards and quick filters (`待处理/P0风险/全部`).
- Global `requirement/list.vue`, `bug/list.vue`, and `bug/p0.vue` now provide searchable/filterable risk-oriented tables.
- For employee filtering, `ownerId`/`owner` matching is used with graceful fallback to full list when no user match exists.

## 2026-02-25 Unified Workbench Pass
- Requirement/Bug/P0 is consolidated into a single workbench page (`requirement/list.vue`) with internal tab switching.
- Data source changed from global static endpoints to project-aligned sources (`project requirement pool + project bugs`) aggregated per project.
- Inline status update is now supported for requirement and bug rows, and each row can jump to project detail with tab context.
