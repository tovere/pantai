# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

A performance management system (绩效管理系统) for 滚水科技 (Boiling Water Tech), built on top of [Vue Vben Admin v5](https://github.com/vbenjs/vue-vben-admin). It tracks projects, requirements, bugs, sprints, employee evaluations, AI code reviews, and scoring/weighting configuration.

The UI language is **Chinese** — menu titles, status options, and labels are all in Chinese. Maintain this convention.

## Common Commands

```bash
pnpm install          # Install dependencies (pnpm only — enforced by preinstall)
pnpm dev              # Start dev server (web-ele app + backend-mock on :5320)
pnpm build            # Production build (web-ele)
pnpm lint             # ESLint + Stylelint via @vben/vsh
pnpm format           # Prettier format
pnpm check:type       # TypeScript type checking (turbo typecheck)
pnpm test:unit        # Run all unit tests (vitest with happy-dom)
```

Run a single test file:
```bash
pnpm vitest run --dom path/to/file.test.ts
```

Backend mock server standalone:
```bash
pnpm -F @vben/backend-mock start   # Starts Nitro dev server on port 5320
```

## Monorepo Structure

**Package manager:** pnpm (v10+) with workspace catalogs in `pnpm-workspace.yaml`.
**Build orchestration:** Turborepo (`turbo.json`).
**Node version:** 22.22.0 (`.node-version`).

### Apps
- **`apps/web-ele`** — Main frontend app. Vue 3 + Element Plus + Vite. Package: `@vben/web-ele`
- **`apps/backend-mock`** — Mock API server. Nitro (h3) + @faker-js/faker. Package: `@vben/backend-mock`

### Packages (consumed by apps)
- **`packages/@core/`** — Core framework: `base/` (design tokens, shared, typings, icons), `ui-kit/` (form, layout, menu, popup, shadcn, tabs), `composables`, `preferences`
- **`packages/effects/`** — Higher-level features: `access`, `common-ui`, `hooks`, `layouts`, `plugins`, `request`
- **`packages/`** (top-level) — `constants`, `icons`, `locales`, `preferences`, `stores`, `styles`, `types`, `utils`

### Internal tooling (`internal/`)
- `vite-config` — Shared Vite configuration (`@vben/vite-config`)
- `tsconfig` — Shared TypeScript configs (`@vben/tsconfig`)
- `tailwind-config` — Shared Tailwind config
- `node-utils` — Node utility scripts
- `lint-configs/` — ESLint, Prettier, Stylelint, Commitlint configs

## Architecture

### Frontend (web-ele)

- **Framework:** Vue 3 Composition API + TypeScript
- **UI Library:** Element Plus (auto-imported via `unplugin-vue-components`)
- **Routing:** vue-router with file-based route modules in `src/router/routes/modules/`. Two route files: `dashboard.ts` and `perf.ts`
- **State:** Pinia stores in `src/store/`
- **API layer:** `src/api/core/perf.ts` — all perf API functions use `requestClient` from `#/api/request`
- **Path alias:** `#/*` maps to `./src/*` (configured in `package.json` imports field)
- **Shared constants:** `src/views/perf/_shared/constants.ts` — status enums, priority options, tag type mappings
- **Factory helpers:** `src/mock/perf/factories.ts` — draft object creators for requirements, design tasks, dev tasks, bugs
- **Vite proxy:** `/api` requests proxy to `http://localhost:5320/api`

### Backend Mock (Nitro)

- File-based routing in `api/` directory. HTTP method suffix convention: `list.ts` = GET, `list.post.ts` = POST
- Central data store: `utils/perf-data.ts` — typed interfaces and in-memory data arrays for all entities (projects, employees, sprints, requirements, bugs, etc.)
- Auth: JWT-based via `utils/jwt-utils.ts` — endpoints verify tokens with `verifyAccessToken(event)`
- Response helpers: `utils/response.ts` — `useResponseSuccess()`, `unAuthorizedResponse()`

### Perf Module Domains

The `perf` module covers these business domains, each with matching frontend views (`views/perf/`) and backend API routes (`api/perf/`):

| Domain | Frontend path | Description |
|--------|--------------|-------------|
| project | `project/` | Project CRUD, detail (tabs: overview, members, requirements, design tasks, dev tasks, sprints, bugs, AI review, logs) |
| requirement | `requirement/` | Requirement workbench with stage advancement workflow |
| bug | `bug/` | Bug list and P0 tracking |
| evaluation | `evaluation/` | Score overview, employee detail, project output, manager review, monthly settlement |
| ai | `ai/` | AI code review score library |
| gitlab | `gitlab/` | GitLab repo integration |
| org | `org/` | Organization structure, employee management, roles |
| settings | `settings/` | Scoring weights configuration |

## Git Conventions

- **Commit format:** Conventional Commits enforced via commitlint + lefthook pre-commit hooks
  - Types: `feat`, `fix`, `style`, `perf`, `refactor`, `revert`, `test`, `docs`, `chore`, `ci`, `types`
- **Pre-commit hooks** (lefthook): Prettier, ESLint, Stylelint run automatically on staged files
- **Branch naming:** `feat/xxxx`, `fix/xxxx`, etc.
