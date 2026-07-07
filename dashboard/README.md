# Web-Ele Monorepo Template

基于 `pnpm workspace + turbo + Vben` 的精简 monorepo 模板。

这个模板保留了原 `web-ele` 的核心体验和工程结构：

- 原认证页与登录流程
- 原后台 layout、header widgets、breadcrumb、tabbar
- 路由守卫与权限体系
- 请求层与 token 刷新逻辑
- i18n、preferences、stores、workspace 分层

同时删除了原项目中的 `perf` 业务页面、业务 API、业务 mock 数据和品牌定制内容。

## 启动

```bash
pnpm install
pnpm dev
```

默认账号：

- `template-admin / 123456`
- `admin / 123456`
- `editor / 123456`

## 构建

```bash
pnpm build
```

## 目录结构

```text
apps/
  web-ele/        # 后台应用
    src/
      mock/       # MockJS mock 服务（前端内置）
packages/
  effects/        # layouts / common-ui / request / hooks / access / plugins
  styles/
  stores/
  preferences/
  locales/
  constants/
  types/
  utils/
  icons/
  @core/
internal/
  vite-config/
  tailwind-config/
  tsconfig/
```

## 当前保留的页面

- `_core/authentication/*`
- `_core/fallback/*`
- `dashboard/*`
- `example/*`

## 如何替换品牌

修改以下文件：

- [apps/web-ele/src/preferences.ts](/Users/Jimmy/project/code/gunshui_frontend_template/dashboard-template/apps/web-ele/src/preferences.ts)
- [apps/web-ele/index.html](/Users/Jimmy/project/code/gunshui_frontend_template/dashboard-template/apps/web-ele/index.html)
- [apps/web-ele/.env](/Users/Jimmy/project/code/gunshui_frontend_template/dashboard-template/apps/web-ele/.env)

## 如何扩展新业务模块

1. 复制 [apps/web-ele/src/router/routes/modules/example.ts](/Users/Jimmy/project/code/gunshui_frontend_template/dashboard-template/apps/web-ele/src/router/routes/modules/example.ts)
2. 在 `apps/web-ele/src/views/` 下新增页面
3. 在 `apps/web-ele/src/api/` 下补业务接口
4. 如需权限控制，保留原 access code 流程

## 如何接真实接口

当前 mock 服务位于：

- [apps/web-ele/src/mock](/Users/Jimmy/project/code/gunshui_frontend_template/dashboard-template/apps/web-ele/src/mock)

前端接口入口位于：

- [apps/web-ele/src/api/core/auth.ts](/Users/Jimmy/project/code/gunshui_frontend_template/dashboard-template/apps/web-ele/src/api/core/auth.ts)
- [apps/web-ele/src/api/core/user.ts](/Users/Jimmy/project/code/gunshui_frontend_template/dashboard-template/apps/web-ele/src/api/core/user.ts)
- [apps/web-ele/src/api/core/menu.ts](/Users/Jimmy/project/code/gunshui_frontend_template/dashboard-template/apps/web-ele/src/api/core/menu.ts)

接真实后端时，优先保持这些函数签名不变，只替换请求实现和返回结构。
