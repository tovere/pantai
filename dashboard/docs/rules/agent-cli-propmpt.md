---
trigger: always_on
---

---
description: Vben Admin Element Plus 前端开发规范（精简版）
globs:
alwaysApply: true
---

不要创建 md 总结文档或任何总结文档
不要创建测试文件
不要创建 bat

# Vben Admin Element Plus 前端开发规范（精简版）

## 1. 规范文档索引（按场景查详细规则）

开发特定功能时，优先读取对应文档：

| 文档 | 场景 |
|---|---|
| `./crud-module.md` | 标准 CRUD（用户/角色/字典等） |
| `./dashboard.md` | Dashboard 仪表盘页面 |
| `./tree-module.md` | 树形结构（菜单/部门/分类） |
| `./form-module.md` | 复杂表单（分步/联动/动态） |
| `./shop-module.md` | 商城模块 |

> 原则：本文件只保留“高频、通用、必须遵守”的规则；详细示例统一放到当前目录规则文档。

## 1.1 技能库索引（.roo/skills）

开发时优先复用技能，避免重复手写模板：

| 技能 | 路径 | 适用场景 |
|---|---|---|
| `crud-generator` | `../skills/crud-generator/` | 快速生成标准 CRUD 模块（API/路由/列表/表单/Mock） |
| `mockjs-web-ele` | `../skills/mockjs-web-ele/` | 统一 web-ele 的 MockJS 写法，修复或迁移旧 Mock 规则 |

### 技能使用优先级

1. 任务属于标准 CRUD：优先使用 `crud-generator`
2. 任务涉及 Mock 接口：优先使用 `mockjs-web-ele`
3. 非标准场景：按 `rules` 手工实现

### 相关文档

- `../skills/crud-generator/SKILL.md`
- `../skills/mockjs-web-ele/SKILL.md`

## 2. 技术栈与范围

- 开发目录：**所有业务开发都在 `../../apps/web-ele` 下进行**
- 技术栈：Vue 3 + TypeScript + Vite + Element Plus + Pinia + Tailwind
- 包管理：pnpm（workspace + turbo）

### 1. 开发目录
**所有开发工作都在 `apps/web-ele` 目录下进行！**

> **页面与文件夹创建规范**
> - 页面与业务模块目录统一放在 `apps/web-ele/src/views/[业务模块]/` 下
> - 每个页面建议使用 `index.vue` 作为入口文件，子组件放在同级 `components/` 目录
> - 路由模块文件放在 `apps/web-ele/src/router/routes/modules/`，与 `views` 业务模块保持同名目录
> - API 文件放在 `apps/web-ele/src/api/`，按业务模块命名（如 `user.ts`）
> - 需要新增字典/枚举时放在 `apps/web-ele/src/dict/`，按业务模块命名

```text
apps/web-ele/
├── src/
│   ├── mock/                  # Mock 服务（mockjs）
│   ├── api/                    # API 接口层
│   │   ├── request.ts          # 请求客户端配置
│   │   ├── core/               # 核心接口（登录、菜单等）
│   │   └── [业务模块].ts       # 业务接口
│   │
│   ├── router/                 # 路由配置
│   │   ├── routes/
│   │   │   ├── core/           # 核心路由（登录、404等）
│   │   │   └── modules/        # 业务路由模块
│   │   └── guard.ts            # 路由守卫
│   │
│   ├── store/                  # 状态管理
│   │   └── auth.ts             # 认证相关 store
│   │
│   ├── views/                  # 页面组件
│   │   ├── _core/              # 核心页面（登录等）
│   │   ├── dashboard/          # 仪表盘
│   │   └── [业务模块]/          # 业务页面
│   │
│   ├── locales/                # 国际化
│   │   └── langs/
│   │       └── zh-CN/          # 中文语言包
│   │
│   ├── adapter/                # UI 组件适配器
│   │   ├── component.ts        # 组件映射
│   │   └── form.ts             # 表单适配
│   │
│   ├── preferences.ts          # 偏好设置覆盖
│   └── bootstrap.ts            # 应用启动
│
└── package.json
```

### 目录约定

- 页面：`../../apps/web-ele/src/views/[module]/index.vue`
- 路由：`../../apps/web-ele/src/router/routes/modules/[module].ts`
- API：`../../apps/web-ele/src/api/[module].ts`
- 字典：`../../apps/web-ele/src/dict/[module].ts`
- 工具：`../../apps/web-ele/src/utils/*`

## 3. 全局编码规范（必须）

1. 使用 `<script setup lang="ts">`
2. 禁止 `any`（无充分理由）
3. 命名规范：
   - 组件：PascalCase
   - 函数/变量：camelCase
   - 常量：UPPER_SNAKE_CASE
4. 异步请求必须 `try/catch/finally`
5. 需要用户反馈的操作必须有消息提示
6. 不要新增“说明性总结文档”

## 4. 组件与交互规范

- 消息：`ElMessage`
- 确认框：`ElMessageBox`
- 表单：`VbenForm`
- 表格：使用 `useVbenVxeGrid` 创建 `<Grid>` 组件（不要使用 `VbenVxeTable`）
- 弹窗：`ElDialog` 或 `VbenModal`

## 5. API 与错误处理规范

- 使用 `requestClient` 访问业务接口
- 所有请求使用统一模式：
  - 请求前：设置 loading 并防重复触发
  - 成功：明确 success 提示/状态更新
  - 失败：明确 error 提示（不要吞错）
  - 结束：finally 重置 loading

参考：`./crud-module.md`（请求、列表、提交完整示例）

## 6. 路由与权限规范

- 每个业务模块单独路由文件
- `meta.authority` 配置权限码
- 按钮权限使用 `v-access` 或 `<AccessControl>`

## 7. 表格页面规范（简版）

- 使用 `useVbenVxeGrid` 创建表格：`const [Grid, gridApi] = useVbenVxeGrid({ gridOptions })`
- 支持分页、筛选、搜索
- 状态列/操作列优先使用插槽
- 删除操作必须二次确认
- 批量操作使用 `gridApi.getCheckboxRecords()` 获取选中项
- 刷新表格使用 `gridApi.reload()`

详细实现参考：`./crud-module.md`

## 8. 表单规范（简版）

- 使用 `VbenForm`
- 使用 zod 做校验
- 编辑态和新增态逻辑明确区分
- 提交按钮必须带 loading 防重复提交

详细实现参考：`./form-module.md`

## 9. 国际化规范

- 默认不强制 i18n
- 若需求明确要求国际化，统一使用 `$t()` + 语言包

## 10. Mock 规范（简版）

- Mock 文件：`../../apps/web-ele/src/mock/`
- 列表接口必须支持分页与筛选
- 所有接口先做 `checkAuth()`

详细实现参考：`./common/mock-module.md`

## 11. 路径别名

- `#/*` -> `apps/web-ele/src/*`
- `@vben/*` -> `packages/*`

## 12. 枚举与字典规范

- 禁止在页面写魔法数字（如 `status === 1`）
- 统一在 `src/dict/` 定义枚举常量
- 枚举项至少包含 `name`、`value`（可扩展 `tagType`）

详细实现参考：`./common/enum.md`

## 13. Dict 弹窗规范

- 多场景确认弹窗用字典对象统一管理
- `visibleType + modalVisible` 控制展示与行为

详细实现参考：`./common/dict-modal.md`

## 14. Loading / Debounce 规范

- 所有异步操作都需要 loading
- 高频触发动作（搜索输入等）使用防抖（推荐 VueUse）

详细实现参考：`./common/loading.md`、`./common/debounce.md`、`./common/error-handling.md`

## 15. 数据回显规范（新增重点）

在编辑页、详情页数据回显时，统一遵循：`./common/data-echo.md`

- 函数：`assignParentValuesToChild`
- 位置：`../../apps/web-ele/src/utils/index.ts`
- 详细实现参考：`./common/data-echo.md`

## 16. AI 执行优先级（给 Agent）

1. 先判断任务属于哪个场景（CRUD / Form / Tree / Dashboard / Shop）
2. 先读当前目录对应规则文件（`./*.md`）
3. 再按本文件“必须规则”落地实现
4. 输出以“可直接落地代码”为主，少讲空泛概念

## 17. 最小交付要求

- 代码可编译
- 类型可通过
- 关键交互可用（新增/编辑/删除/回显/加载）
- 不新增无关文件

## 18. 补充说明

- 若项目依赖或脚手架发生变更，需同步更新本规范
- 遇到 Element Plus 问题，优先查官方文档
- 遇到 Vben 问题，优先查 `../../CLAUDE.md` 与 `../`
