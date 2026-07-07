# Web-Ele Monorepo Template Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 将当前仓库整体替换为一个精简后的 Vben 风格 monorepo 模板，保留原 `web-ele` 的登录页、布局、widgets、权限、请求和 i18n 体系，同时移除 `perf` 业务模块。

**Architecture:** 以源项目的 monorepo 结构为基底，先复制 `web-ele` 的完整运行闭环，再通过删除 `perf` 页面、业务 API、业务 mock 和无关 workspace 做减法，最后补齐模板专用的品牌、示例模块和文档。整个过程尽量不重组已有分层，而是保留原包结构与行为一致性。

**Tech Stack:** pnpm workspace, Turbo, Vue 3, Vite, TypeScript, Pinia, Vue Router, Element Plus, Vben workspace packages

---

### Task 1: 清理当前单应用骨架并准备 monorepo 根结构

**Files:**
- Delete: 当前单应用根级文件和 `src/`, `public/`, `dist/` 等目录
- Create: `package.json`
- Create: `pnpm-workspace.yaml`
- Create: `turbo.json`
- Create: `.gitignore`
- Create: `.npmrc`
- Create: `.env.example`

**Step 1: 列出当前仓库现有文件**

Run: `find . -maxdepth 2 | sort`
Expected: 明确当前单应用结构，确认待替换范围。

**Step 2: 删除单应用模板文件**

删除当前根级 `src/`, `public/`, `index.html`, `vite.config.ts`, `tsconfig*.json` 等单应用文件，只保留 `docs/plans/*`。

**Step 3: 复制源项目的根级 monorepo 配置**

从 `/Users/Jimmy/project/code/gunshui-project-manager` 复制并调整：

- 根 `package.json`
- `pnpm-workspace.yaml`
- `turbo.json`
- 必要的根配置文件

**Step 4: 写 `.env.example`**

补充模板通用环境变量说明。

**Step 5: 验证根结构存在**

Run: `find . -maxdepth 2 \\( -name package.json -o -name pnpm-workspace.yaml -o -name turbo.json \\) | sort`
Expected: monorepo 根配置到位。

### Task 2: 复制 `web-ele` 闭环所需 workspace

**Files:**
- Create: `apps/web-ele/**`
- Create: `packages/effects/{layouts,common-ui,access,hooks,request}/**`
- Create: `packages/{styles,stores,preferences,locales,constants,types,utils,icons}/**`
- Create: `packages/@core/base/**`
- Create: `packages/@core/ui-kit/**`
- Create: `packages/@core/composables/**`
- Create: `internal/{vite-config,tailwind-config,tsconfig}/**`
- Create: 必要的 lint/prettier/commitlint 配置包

**Step 1: 从源项目复制包目录**

确保只复制 `web-ele` 真正依赖的 workspace，不复制 `packages/business`、`playground` 等。

**Step 2: 检查 workspace 声明**

Run: `find apps packages internal -maxdepth 3 -name package.json | sort`
Expected: 只保留模板需要的 workspace。

**Step 3: 安装依赖**

Run: `pnpm install`
Expected: workspace 依赖安装成功，无缺失包错误。

### Task 3: 跑通原始闭环

**Files:**
- Modify: 仅必要的环境配置和占位变量

**Step 1: 运行类型检查或构建前检查**

Run: `pnpm check:type`
Expected: 现有 monorepo 至少能进入类型检查阶段，若失败则记录缺失包或路径问题。

**Step 2: 启动 `web-ele`**

Run: `pnpm dev`
Expected: `apps/web-ele` 启动成功，登录页和主 layout 处于原始状态。

**Step 3: 运行构建**

Run: `pnpm build`
Expected: 保留闭环后的原始工程可构建。

### Task 4: 删除 `perf` 页面、路由、API 和 mock

**Files:**
- Delete: `apps/web-ele/src/views/perf/**`
- Delete: `apps/web-ele/src/mock/perf/**`
- Delete: `apps/web-ele/src/api/core/perf.ts`
- Modify: `apps/web-ele/src/router/routes/modules/*.ts`
- Modify: `apps/web-ele/src/api/core/index.ts`
- Modify: `apps/web-ele/src/router/routes/index.ts`

**Step 1: 写失败检查**

用 `rg "perf/" apps/web-ele/src` 和 `rg "Perf" apps/web-ele/src` 找出所有残留引用。

**Step 2: 删除业务目录**

移除 `perf` 相关页面、mock 和 API。

**Step 3: 清理路由和导出**

删除 `perf` 模块路由引用和 API 导出，避免构建时残留引用。

**Step 4: 运行搜索复查**

Run: `rg "perf/" apps/web-ele/src`
Expected: 仅保留允许存在的注释或文档引用，代码引用应清零。

### Task 5: 添加模板示例模块并收敛菜单

**Files:**
- Create: `apps/web-ele/src/views/example/index.vue`
- Create: `apps/web-ele/src/router/routes/modules/example.ts`
- Modify: `apps/web-ele/src/router/routes/modules/dashboard.ts`
- Modify: `apps/web-ele/src/router/routes/index.ts`
- Modify: `apps/web-ele/src/locales/langs/**`

**Step 1: 添加 example 页面**

提供一个符合原 layout 体系的最小示例页。

**Step 2: 添加 example 路由**

将菜单收敛为 dashboard + example。

**Step 3: 清理旧业务菜单**

删除需求、项目管理、GitLab、AI review、绩效评估等菜单入口。

**Step 4: 运行启动验证**

Run: `pnpm dev`
Expected: 登录后左侧菜单只显示模板保留项。

### Task 6: 模板化认证与品牌配置

**Files:**
- Modify: `apps/web-ele/src/preferences.ts`
- Modify: `apps/web-ele/src/views/_core/authentication/*.vue`
- Modify: `apps/web-ele/src/layouts/basic.vue`
- Modify: `apps/web-ele/src/layouts/auth.vue`
- Modify: `apps/web-ele/public/**`
- Modify: `apps/web-ele/src/locales/langs/**`

**Step 1: 替换品牌信息**

去掉滚水科技品牌名、logo、站点、邮箱、文案。

**Step 2: 保留原结构但替换成模板占位内容**

不改布局体系，只替换文案和占位资源。

**Step 3: 验证登录页和主布局**

Run: `pnpm dev`
Expected: 视觉结构和交互体系仍是原项目风格，但品牌已模板化。

### Task 7: 模板化 API 和默认数据

**Files:**
- Modify: `apps/web-ele/src/api/core/auth.ts`
- Modify: `apps/web-ele/src/api/core/user.ts`
- Modify: `apps/backend-mock/**` 或替换为更小 mock 实现
- Modify: 相关 store / route access 初始化文件

**Step 1: 保留认证流程**

保留登录、获取用户信息、获取权限码、刷新 token 的接口形态。

**Step 2: 移除业务数据结构**

默认返回模板用户、模板权限码和模板菜单，不依赖 `perf` 业务实体。

**Step 3: 验证登录链路**

Run: `pnpm dev`
Expected: 默认账号可登录并进入 dashboard/example。

### Task 8: 删除不再需要的 workspace 和工程文件

**Files:**
- Delete: `packages/business/**`
- Delete: `playground/**`
- Delete: 非必需 `docs/**`
- Delete: 非必需 `scripts/**`
- Modify: 根 `package.json`
- Modify: `pnpm-workspace.yaml`

**Step 1: 查引用**

Run: `rg "packages/business|playground|scripts/" .`
Expected: 找出仍有引用的位置。

**Step 2: 删除未引用 workspace**

确保只保留模板闭环所需包。

**Step 3: 更新 workspace 声明**

同步修改 `pnpm-workspace.yaml` 和根脚本，避免指向已删除目录。

**Step 4: 重新安装**

Run: `pnpm install`
Expected: 依赖关系仍完整。

### Task 9: README 与模板文档收尾

**Files:**
- Create: `README.md`
- Modify: `.env.example`

**Step 1: 编写 README**

至少说明：

- 如何安装
- 如何启动
- monorepo 目录结构
- 哪些包是平台层
- 如何替换品牌
- 如何新增菜单和页面
- 如何接真实登录接口

**Step 2: 校验文档与当前结构一致**

Run: `find apps packages internal -maxdepth 3 | sort`
Expected: README 中描述与实际结构匹配。

### Task 10: 最终验证

**Files:**
- Modify: `docs/plans/2026-03-09-web-ele-monorepo-template-design.md`
- Modify: `docs/plans/2026-03-09-web-ele-monorepo-template.md`

**Step 1: 跑类型检查**

Run: `pnpm check:type`
Expected: 通过。

**Step 2: 跑开发启动**

Run: `pnpm dev`
Expected: 登录页、dashboard、example、layout、widgets 可用。

**Step 3: 跑构建**

Run: `pnpm build`
Expected: 构建成功。

**Step 4: 记录偏差**

如果实际保留或删除的 workspace 与设计有差异，回写到文档中。
