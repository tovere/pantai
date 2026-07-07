# CRUD Generator Rules Reference

本文件为 `crud-generator` skill 的详细参考规则。

## 1. 输入结构

```yaml
moduleName: 用户管理
modulePath: user
moduleCode: User

fields:
  - name: id
    type: string
    label: ID
    table: true
    tableWidth: 80
    form: false

  - name: username
    type: string
    label: 用户名
    required: true
    min: 3
    max: 20
    search: true
    table: true
    tableWidth: 120
    form: true

  - name: status
    type: number
    label: 状态
    enum:
      - label: 启用
        value: 1
        tagType: success
      - label: 禁用
        value: 0
        tagType: danger
    defaultValue: 1
    search: true
    table: true
    tableWidth: 80
    form: true

permissions:
  - code: user:list
    label: 查看列表
  - code: user:add
    label: 新增
  - code: user:edit
    label: 编辑
  - code: user:delete
    label: 删除
```

## 2. 生成规则

### 2.1 API 接口规则

- 使用项目统一请求客户端。
- 接口路径遵循 `/${modulePath}/list`、`/${modulePath}/:id`。
- 类型命名：`${ModuleCode}Item`、`${ModuleCode}ListParams`、`${ModuleCode}FormData`。
- 函数命名：
  - `get${ModuleCode}ListApi`
  - `get${ModuleCode}DetailApi`
  - `create${ModuleCode}Api`
  - `update${ModuleCode}Api`
  - `delete${ModuleCode}Api`
  - `batchDelete${ModuleCode}Api`

### 2.2 表格规则

- 使用 `useVbenVxeGrid` 创建表格组件 `<Grid>`。
- 必须包含 checkbox 选择列用于批量操作。
- `field/title/width` 分别映射字段 `name/label/tableWidth`。
- 枚举字段使用 `slots` 渲染 Tag。
- 操作列固定右侧（`fixed: 'right'`）。
- 列表请求走 `proxyConfig.ajax.query`，返回 `{ items, total }`。
- 使用 `const [Grid, gridApi] = useVbenVxeGrid({ gridOptions })` 模式。

### 2.3 搜索栏规则

- 仅生成 `search: true` 字段。
- 字符串：输入框；枚举：下拉；日期：日期选择器。

### 2.4 表单规则

- 使用 `VbenForm`。
- 仅生成 `form: true` 字段。
- 组件映射：
  - `string -> VbenInput`
  - `number -> VbenInputNumber`
  - `enum -> VbenSelect`
  - 长文本 -> `VbenTextarea`
- 使用 `zod` 构建验证（required/min/max/pattern/email）。

### 2.5 枚举规则

- 字典位置：`apps/web-ele/src/dict/${modulePath}.ts`。
- 常量名：`${MODULE_CODE}_${FIELD_NAME}`（大写蛇形）。
- 表格中通过 slot 渲染 `el-tag`，显示 `name` 并绑定 `tagType`。

### 2.6 Loading 规则

- 提交按钮：`submitLoading`
- 单行删除：`deleteLoadingMap[id]`
- 批量删除：`batchDeleteLoading`
- 表格加载：`tableLoading`

### 2.7 错误处理规则

所有异步请求统一使用 `try/catch/finally`，并确保：

- 重复点击保护（loading guard）
- 成功提示和失败提示
- `finally` 中恢复 loading 状态

## 3. 标准输出文件清单

- `apps/web-ele/src/api/${modulePath}.ts`
- `apps/web-ele/src/router/routes/modules/${modulePath}.ts`
- `apps/web-ele/src/views/${modulePath}/index.vue`
- `apps/web-ele/src/views/${modulePath}/FormModal.vue`
- `apps/web-ele/src/dict/${modulePath}.ts`（如存在 enum）
- `apps/web-ele/src/mock/modules/${modulePath}.ts`（Mock 接口）
- `apps/web-ele/src/mock/index.ts`（注册 Mock 模块）

## 4. 模板变量约定

- `${moduleName}`: 中文模块名
- `${modulePath}`: 路径段（小写）
- `${moduleCode}` / `${ModuleCode}`: 代码名（PascalCase）
- `${fields}`: 全字段定义
- `${searchFields}` / `${tableFields}` / `${formFields}` / `${enumFields}`: 按用途筛选的字段子集

## 5. 输出质量检查清单

- API、路由、视图、字典、mock 命名一致
- 列表返回结构一致（items/total）
- 权限码与按钮行为一致
- 枚举显示与表单选项一致
- 所有提交/删除行为具备 loading 和错误处理

