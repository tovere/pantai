# Web-Ele Monorepo Template Design

**Date:** 2026-03-09

## Goal

将 `/Users/Jimmy/project/code/gunshui-project-manager` 抽离成一个可复用的精简 monorepo 模板，保留原 `web-ele` 的真实工程结构和核心平台能力：

- 原登录页和认证布局
- 原基础后台布局、header widgets、breadcrumb、tabbar
- 路由守卫和权限体系
- 请求层和 token 刷新逻辑
- i18n 与偏好配置
- Vben 风格的 workspace 包分层

同时移除 `perf` 业务页面、业务 API、业务 mock、无关 workspace 和品牌定制信息，使当前仓库可以作为后续新项目的起点。

## Non-Goals

- 不再做单应用模板
- 不扁平化 `@vben/*` 包到 `src/core/*`
- 不保留 `perf` 业务模块
- 不保留无关 docs / playground / scripts / business packages

## Recommended Approach

采用“先保留完整闭环，再做系统删减”的迁移方式：

1. 将源项目中 `web-ele` 运行所需的 monorepo 结构复制到当前仓库
2. 先确保模板仓库能完整安装、启动、构建
3. 再删除 `perf` 模块和不必要的 workspace
4. 最后完成模板化收尾

原因：

- 原项目的登录页、布局、widgets、stores、preferences、request、locales 耦合很深
- 先删后拼会导致大量“看起来像，但行为不一致”的问题
- 先完整保留，后续减法更容易保持行为一致

## Source Analysis

源项目是 `pnpm + turbo` monorepo，主要结构包括：

- `apps/web-ele`
- `packages/effects/*`
- `packages/styles`
- `packages/stores`
- `packages/preferences`
- `packages/locales`
- `packages/constants`
- `packages/types`
- `packages/utils`
- `packages/icons`
- `packages/@core/*`
- `internal/*`

其中 `web-ele` 的实际体验高度依赖：

- `packages/effects/layouts`
- `packages/effects/common-ui`
- `packages/effects/access`
- `packages/effects/hooks`
- `packages/effects/request`
- `packages/stores`
- `packages/preferences`
- `packages/locales`
- `packages/styles`
- `packages/icons`
- `packages/utils`
- `packages/@core/base/*`
- `packages/@core/ui-kit/*`
- `packages/@core/composables`
- `internal/vite-config`
- `internal/tailwind-config`
- `internal/tsconfig`

## Keep Scope

建议保留：

- `apps/web-ele`
- `packages/effects/layouts`
- `packages/effects/common-ui`
- `packages/effects/access`
- `packages/effects/hooks`
- `packages/effects/request`
- `packages/styles`
- `packages/stores`
- `packages/preferences`
- `packages/locales`
- `packages/constants`
- `packages/types`
- `packages/utils`
- `packages/icons`
- `packages/@core/base/*`
- `packages/@core/ui-kit/*`
- `packages/@core/composables`
- `internal/vite-config`
- `internal/tailwind-config`
- `internal/tsconfig`
- 必要的 lint / prettier / commitlint 配置
- 根级 `package.json` / `pnpm-workspace.yaml` / `turbo.json`

## Remove Scope

建议删除：

- `apps/web-ele/src/views/perf/**`
- `apps/web-ele/src/api/core/perf.ts`
- `apps/web-ele/src/mock/perf/**`
- `apps/backend-mock` 中仅服务于 `perf` 的内容
- `packages/business/**`
- `playground`
- `docs` 中与模板运行无关的文档站相关内容
- 非运行必需的 `scripts/*`
- 所有不再被 `web-ele` 或保留包引用的 workspace
- 品牌、公司、链接、默认邮箱等滚水科技特有内容

## Resulting App Scope

模板最终只保留以下页面组：

- `views/_core/authentication/*`
- `views/_core/fallback/*`
- `views/dashboard/*`
- `views/example/*`

菜单只保留：

- Dashboard / Workspace
- Example

## Template Rules

模板化时需要替换：

- `preferences.ts` 中的公司名、logo、站点链接
- 登录文案、默认介绍文案
- 顶部用户描述、通知占位
- API 示例数据

模板化时需要补充：

- `example` 路由模块
- `example` 页面
- `.env.example`
- README

## Verification Criteria

实现完成后应满足：

1. `pnpm install` 成功
2. `pnpm dev` 可以启动
3. 登录页与原认证布局保持同一体系
4. 登录后的 header / widgets / tabbar / sidebar 行为保持原体系
5. 未登录访问受保护页面会跳转登录
6. 登录后可进入 dashboard
7. 只保留模板菜单和示例模块
8. `pnpm build` 成功

## Risks

- 删除 workspace 时容易误删隐式依赖包
- `perf` 页面删除后，route/menu/access 可能仍残留引用
- 业务 mock 与通用 request 可能存在共享数据结构，删减时需要逐条确认

控制方式：

- 先复制后验证
- 再逐步删除，每一步都跑安装、启动或构建验证
- 只在确认 workspace 无引用后再删除

## Implementation Handoff

下一步进入 monorepo 版本的实现计划，按“复制闭环 -> 验证 -> 删除业务 -> 模板化 -> 最终验证”的顺序执行。
