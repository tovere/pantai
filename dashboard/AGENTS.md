---
trigger: always_on
---

---
description: Vben Admin Element Plus 前端开发规范
globs:
alwaysApply: true
---
不要创建md总结文档或任何总结文档
不要创建测试文件
不要创建bat

# Vben Admin Element Plus 前端开发规范

## 规范文档索引

开发特定类型功能时，请参考对应的规范文档：

| 规范文档 | 适用场景 |
|----------|----------|
| [`docs/rules/crud-module.md`](docs/rules/crud-module.md) | 标准 CRUD 模块（用户管理、角色管理等） |
| [`docs/rules/dashboard.md`](docs/rules/dashboard.md) | Dashboard 仪表盘、数据统计页面 |
| [`docs/rules/tree-module.md`](docs/rules/tree-module.md) | 树形结构（部门管理、菜单管理、分类管理等） |
| [`docs/rules/form-module.md`](docs/rules/form-module.md) | 复杂表单（分步表单、动态表单、表单联动） |
| [`docs/rules/shop-module.md`](docs/rules/shop-module.md) | 商城/购物模块（商品、订单、购物车、支付） |

## 技能库索引

快速生成常见业务模块代码，请参考：[`docs/skills/README.md`](docs/skills/README.md)

| 技能 | 说明 |
|------|------|
| [CRUD 生成器](skills/crud-generator/SKILL.md) | 快速生成标准增删改查模块 |

## 基础角色定位
你是一个资深前端工程师 + AI 助手，专长 Vue 3（Composition API / <script setup>）、TypeScript、Vite、Element Plus、TailwindCSS、Pinia。
你会给出清晰、可执行、可复制粘贴的代码和步骤，并在必要时提供解释与调试建议。
输出代码时，优先给出完整文件内容与文件路径；若返回多文件，则用清单并分别给出每个文件的完整内容；尽量少只给片段。

## 项目技术栈
- **框架**: Vue 3.5+ + TypeScript 5.6+ + Vite 6.0+
- **UI 库**: Element Plus（使用 apps/web-ele 应用）
- **样式**: TailwindCSS + shadcn-vue
- **状态管理**: Pinia
- **表单**: VbenForm（@vben/common-ui）
- **表格**: VbenVxeTable 或 ApiComponent
- **请求**: RequestClient（@vben/request，基于 Axios 封装）
- **路由**: Vue Router + 权限守卫
- **包管理**: PNPM（pnpm workspaces + Turborepo）
- **代码规范**: ESLint + Prettier + Stylelint
- **提交规范**: Conventional Commits（commitlint + lefthook）

## 核心开发规范

### 1. 开发目录
**所有开发工作都在 `apps/web-ele` 目录下进行！**

> **页面与文件夹创建规范**
> - 页面与业务模块目录统一放在 `apps/web-ele/src/views/[业务模块]/` 下
> - 每个页面建议使用 `index.vue` 作为入口文件，子组件放在同级 `components/` 目录
> - 路由模块文件放在 `apps/web-ele/src/router/routes/modules/`，与 `views` 业务模块保持同名目录
> - API 文件放在 `apps/web-ele/src/api/`，按业务模块命名（如 `user.ts`）
> - 需要新增字典/枚举时放在 `apps/web-ele/src/dict/`，按业务模块命名

```
apps/web-ele/
├── src/
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

### 2. 代码风格与结构
- 使用 Composition API 与 `<script setup lang="ts">` 语法
- 组件和样式要可维护、语义化
- 文件结构清晰，组件拆分合理
- **统一使用 TypeScript**，禁止使用 any 类型
- **统一命名规范**：
  - 组件文件：PascalCase（如 `UserList.vue`）
  - 工具函数：camelCase（如 `formatDate.ts`）
  - 常量：UPPER_SNAKE_CASE（如 `API_PREFIX`）
  - 路由 name：PascalCase（如 `UserList`）

### 3. UI 组件使用规范
- **消息提示**：使用 Element Plus 的 `ElMessage`
- **确认弹窗**：使用 Element Plus 的 `ElMessageBox`
- **表单**：使用 `@vben/common-ui` 的 VbenForm
- **表格**：使用 `@vben/common-ui` 的 VbenVxeTable 或 ApiComponent
- **弹窗**：使用 Element Plus 的 ElDialog 或 `@vben/common-ui` 的 VbenModal

```typescript
// ✅ 正确
import { ElMessage, ElMessageBox } from 'element-plus';

// ❌ 错误（不要使用 ant-design-vue）
import { message } from 'ant-design-vue';
```

### 4. 状态管理（Pinia）
- 使用 store 统一管理全局状态
- store 文件位置：`packages/stores/` 或 `apps/web-ele/src/store/`
- 示例：
  ```typescript
  import { defineStore } from 'pinia';
  import { ref, computed } from 'vue';
  
  export const useUserStore = defineStore('user', () => {
    // 状态
    const userInfo = ref<UserInfo | null>(null);
    const roles = computed(() => userInfo.value?.roles ?? []);
    
    // 方法
    const setUserInfo = (info: UserInfo) => {
      userInfo.value = info;
    };
    
    const reset = () => {
      userInfo.value = null;
    };
    
    return { userInfo, roles, setUserInfo, reset };
  });
  ```

### 5. API 接口规范
- 接口文件位置：`apps/web-ele/src/api/`
- 使用 `requestClient` 发送请求（自动解包响应）
- 使用 `baseRequestClient` 获取原始响应

```typescript
// apps/web-ele/src/api/user.ts
import { requestClient } from '#/api/request';

// 类型定义
export interface UserItem {
  id: string;
  username: string;
  realName: string;
  mobile: string;
  email?: string;
  status: number;
  createTime: string;
}

export interface UserListParams {
  page: number;
  pageSize: number;
  username?: string;
  status?: number;
}

// 获取用户列表
export async function getUserListApi(params: UserListParams) {
  return requestClient.get<{ items: UserItem[]; total: number }>('/user/list', {
    params,
  });
}

// 新增用户
export async function createUserApi(data: Partial<UserItem>) {
  return requestClient.post<UserItem>('/user', data);
}

// 编辑用户
export async function updateUserApi(id: string, data: Partial<UserItem>) {
  return requestClient.put<UserItem>(`/user/${id}`, data);
}

// 删除用户
export async function deleteUserApi(id: string) {
  return requestClient.delete(`/user/${id}`);
}
```

### 6. 路由配置规范
- 业务路由位置：`apps/web-ele/src/router/routes/modules/`
- 每个模块一个文件，导出 `RouteRecordRaw[]`

```typescript
// apps/web-ele/src/router/routes/modules/system.ts
import type { RouteRecordRaw } from 'vue-router';

import { $t } from '#/locales';

const routes: RouteRecordRaw[] = [
  {
    meta: {
      icon: 'lucide:settings',
      title: $t('routes.system.title'),
      order: 1,
    },
    name: 'System',
    path: '/system',
    children: [
      {
        name: 'UserList',
        path: '/system/user',
        component: () => import('#/views/system/user/index.vue'),
        meta: {
          icon: 'lucide:user',
          title: $t('routes.system.user'),
          authority: ['system:user:list'],
        },
      },
      {
        name: 'RoleList',
        path: '/system/role',
        component: () => import('#/views/system/role/index.vue'),
        meta: {
          icon: 'lucide:shield',
          title: $t('routes.system.role'),
          authority: ['system:role:list'],
        },
      },
    ],
  },
];

export default routes;
```

### 7. 表格页面开发规范
- 使用 `VbenVxeTable` 或 `ApiComponent`
- 支持分页、搜索、筛选
- 操作列使用插槽

```vue
<script lang="ts" setup>
import { reactive } from 'vue';
import { VbenVxeTable } from '@vben/common-ui';
import type { VxeGridProps } from 'vxe-table';
import { ElMessage, ElMessageBox } from 'element-plus';

import { getUserListApi, deleteUserApi } from '#/api/user';

// 表格配置
const gridOptions = reactive<VxeGridProps>({
  columns: [
    { type: 'checkbox', width: 50 },
    { field: 'username', title: '用户名', width: 120 },
    { field: 'realName', title: '真实姓名', width: 100 },
    { field: 'mobile', title: '手机号', width: 120 },
    { 
      field: 'status', 
      title: '状态', 
      width: 80, 
      slots: { default: 'status' } 
    },
    { field: 'createTime', title: '创建时间', width: 160 },
    { 
      field: 'actions', 
      title: '操作', 
      width: 150, 
      fixed: 'right',
      slots: { default: 'actions' } 
    },
  ],
  proxyConfig: {
    ajax: {
      query: async ({ page }) => {
        const res = await getUserListApi({
          page: page.currentPage,
          pageSize: page.pageSize,
        });
        return { items: res.items, total: res.total };
      },
    },
  },
  checkboxConfig: {
    reserve: true,
  },
});

// 删除用户
async function handleDelete(id: string) {
  await ElMessageBox.confirm('确定要删除该用户吗？', '提示', {
    type: 'warning',
  });
  await deleteUserApi(id);
  ElMessage.success('删除成功');
}
</script>

<template>
  <div class="p-4">
    <VbenVxeTable :options="gridOptions">
      <!-- 状态列 -->
      <template #status="{ row }">
        <el-tag :type="row.status === 1 ? 'success' : 'danger'">
          {{ row.status === 1 ? '启用' : '禁用' }}
        </el-tag>
      </template>
      
      <!-- 操作列 -->
      <template #actions="{ row }">
        <el-button type="primary" link>编辑</el-button>
        <el-button type="danger" link @click="handleDelete(row.id)">
          删除
        </el-button>
      </template>
    </VbenVxeTable>
  </div>
</template>
```

### 8. 表单开发规范
- 使用 `VbenForm` 组件
- 使用 `zod` 进行表单验证

```vue
<script lang="ts" setup>
import { computed } from 'vue';
import { VbenForm, z } from '@vben/common-ui';
import type { VbenFormSchema } from '@vben/common-ui';

interface FormData {
  username: string;
  realName: string;
  mobile: string;
  email?: string;
  status: number;
}

const formData = defineModel<FormData>('data');

const formSchema = computed((): VbenFormSchema[] => [
  {
    component: 'VbenInput',
    fieldName: 'username',
    label: '用户名',
    rules: z.string().min(3, '用户名至少3个字符').max(20, '用户名最多20个字符'),
    componentProps: {
      placeholder: '请输入用户名',
    },
  },
  {
    component: 'VbenInput',
    fieldName: 'realName',
    label: '真实姓名',
    rules: z.string().min(1, '请输入真实姓名'),
    componentProps: {
      placeholder: '请输入真实姓名',
    },
  },
  {
    component: 'VbenInput',
    fieldName: 'mobile',
    label: '手机号',
    rules: z.string().regex(/^1[3-9]\d{9}$/, '请输入正确的手机号'),
    componentProps: {
      placeholder: '请输入手机号',
    },
  },
  {
    component: 'VbenInput',
    fieldName: 'email',
    label: '邮箱',
    rules: z.string().email('请输入正确的邮箱').optional(),
    componentProps: {
      placeholder: '请输入邮箱',
    },
  },
  {
    component: 'VbenSelect',
    fieldName: 'status',
    label: '状态',
    componentProps: {
      options: [
        { label: '启用', value: 1 },
        { label: '禁用', value: 0 },
      ],
    },
  },
]);
</script>

<template>
  <VbenForm :schema="formSchema" :values="formData" />
</template>
```

### 9. 国际化规范
- 使用 `$t()` 函数获取国际化文案
- 语言文件位置：`packages/locales/` 和 `apps/web-ele/src/locales/langs/`
- **默认不强制国际化**：若需求未明确要求国际化，可直接使用中文文案；仅在需求明确要求国际化时，才统一使用 `$t()` 与语言包键值

```typescript
// 在脚本中使用
import { $t } from '#/locales';
const title = $t('common.confirm');

// 在模板中使用
<template>
  <span>{{ $t('common.confirm') }}</span>
</template>
```
  
### 10. Mock 数据规范
- **Mock 服务位置**：`apps/web-ele/mock/`
- **Mock 库**：使用 `mockjs` 进行数据模拟
- **启用方式**：在 `apps/web-ele/src/main.ts` 中导入 `#/mock`

#### 响应格式统一

**成功响应**：
```json
{
  "code": 0,
  "data": { ... },
  "error": null,
  "message": "ok"
}
```

**错误响应**：
```json
{
  "code": -1,
  "data": null,
  "error": "具体错误信息",
  "message": "错误提示信息"
}
```

**分页响应**：
```json
{
  "code": 0,
  "data": {
    "items": [ ... ],
    "total": 100
  },
  "error": null,
  "message": "ok"
}
```

#### Mock 工具函数（`_utils.ts`）

项目提供了统一的工具函数，位于 `apps/web-ele/mock/_utils.ts`：

- **`responseSuccess(data)`**：返回成功响应
- **`pageResponseSuccess(items, total)`**：返回分页响应
- **`responseError(message, error)`**：返回错误响应
- **`checkAuth()`**：验证用户权限（从 localStorage 读取 token）
- **`pagination(page, pageSize, array)`**：分页工具
- **`getQueryParams(url)`**：从 URL 提取查询参数
- **`extractPathParams(url, pattern)`**：从 URL 提取路径参数

#### Mock 接口编写规范

```typescript
// apps/web-ele/mock/user.ts
import Mock from 'mockjs';
import {
  checkAuth,
  extractPathParams,
  getQueryParams,
  pageResponseSuccess,
  pagination,
  responseSuccess,
  responseError
} from './_utils';

// 1. 生成 Mock 数据
function generateMockUserList(count: number) {
  const dataList: Record<string, any>[] = [];
  
  for (let i = 0; i < count; i++) {
    dataList.push({
      id: `user-${i + 1}`,
      username: Mock.Random.cname(),
      mobile: `1${Mock.Random.string('number', 10)}`,
      avatar: Mock.Random.image('200x200', '#50B347', '#FFF', 'Avatar'),
      status: Mock.Random.integer(0, 1),
      createdAt: new Date().toISOString(),
    });
  }
  
  return dataList;
}

const mockUserList = generateMockUserList(100);

// 2. 列表接口（支持分页、筛选）
Mock.mock(/\/api\/user\/list/, 'get', (options: any) => {
  const auth = checkAuth();
  if (!auth.authorized) return auth.error;
  
  const params = getQueryParams(options.url);
  const { page = 1, pageSize = 10, username, status } = params;
  
  let listData = [...mockUserList];
  
  // 筛选
  if (username) {
    listData = listData.filter((item) =>
      item.username.toLowerCase().includes(String(username).toLowerCase())
    );
  }
  if (['0', '1'].includes(status)) {
    listData = listData.filter((item) => item.status === Number(status));
  }
  
  // 分页
  const items = pagination(Number(page), Number(pageSize), listData);
  return pageResponseSuccess(items, listData.length);
});

// 3. 详情接口（路径参数）
Mock.mock(/\/api\/user\/[^/]+$/, 'get', (options: any) => {
  const auth = checkAuth();
  if (!auth.authorized) return auth.error;
  
  const params = extractPathParams(options.url, '/api/user/:id');
  const { id } = params;
  
  const user = mockUserList.find((item) => item.id === id);
  if (!user) {
    return responseError('用户不存在');
  }
  
  return responseSuccess(user);
});

// 4. 新增接口
Mock.mock(/\/api\/user$/, 'post', (options: any) => {
  const auth = checkAuth();
  if (!auth.authorized) return auth.error;
  
  const body = JSON.parse(options.body);
  const newUser = {
    id: `user-${Date.now()}`,
    ...body,
    createdAt: new Date().toISOString(),
  };
  
  mockUserList.push(newUser);
  return responseSuccess(newUser);
});

// 5. 编辑接口
Mock.mock(/\/api\/user\/[^/]+$/, 'put', (options: any) => {
  const auth = checkAuth();
  if (!auth.authorized) return auth.error;
  
  const params = extractPathParams(options.url, '/api/user/:id');
  const { id } = params;
  const body = JSON.parse(options.body);
  
  const index = mockUserList.findIndex((item) => item.id === id);
  if (index === -1) {
    return responseError('用户不存在');
  }
  
  mockUserList[index] = { ...mockUserList[index], ...body };
  return responseSuccess(mockUserList[index]);
});

// 6. 删除接口
Mock.mock(/\/api\/user\/[^/]+$/, 'delete', (options: any) => {
  const auth = checkAuth();
  if (!auth.authorized) return auth.error;
  
  const params = extractPathParams(options.url, '/api/user/:id');
  const { id } = params;
  
  const index = mockUserList.findIndex((item) => item.id === id);
  if (index === -1) {
    return responseError('用户不存在');
  }
  
  mockUserList.splice(index, 1);
  return responseSuccess(null);
});
```

#### Mock.Random 常用方法

```typescript
// 中文姓名
Mock.Random.cname()

// 中文标题
Mock.Random.ctitle(5, 15)

// 中文段落
Mock.Random.cparagraph()

// 中文句子
Mock.Random.csentence(5, 10)

// 整数
Mock.Random.integer(0, 100)

// 字符串
Mock.Random.string('number', 10)

// 邮箱
Mock.Random.email()

// 图片
Mock.Random.image('200x200', '#50B347', '#FFF', 'Avatar')

// 从数组中随机选择
Mock.Random.pick(['选项1', '选项2', '选项3'])
```

#### 注意事项

- 所有接口都需要使用 `checkAuth()` 进行权限验证
- 使用正则表达式匹配 URL，支持路径参数
- 列表接口必须支持分页和筛选
- 使用 `extractPathParams` 提取路径参数（如 `/api/user/:id`）
- 使用 `getQueryParams` 提取查询参数（如 `?page=1&pageSize=10`）
- Mock 数据应该尽量真实，使用 `Mock.Random` 生成随机数据


### 11. 路径别名
- `#/*` 指向 `apps/web-ele/src/*`
- `@vben/*` 指向 `packages/*`

```typescript
// 使用示例
import { useAuthStore } from '#/store';
import { VbenForm } from '@vben/common-ui';
```

### 12. 权限控制
- 路由权限：在 `meta.authority` 中配置权限码
- 按钮权限：使用 `v-access` 指令或 `<AccessControl>` 组件

```vue
<template>
  <!-- 使用指令 -->
  <el-button v-access:code="'system:user:add'">新增</el-button>
  
  <!-- 使用组件 -->
  <AccessControl :codes="['system:user:delete']">
    <el-button type="danger">删除</el-button>
  </AccessControl>
</template>
```

### 13. 枚举开发规范
- **原则**: 不在页面直接使用 `status===0` 这样的魔法数字判断，应单独定义枚举常量
- **位置**: `src/dict/` 目录下按模块组织
- **命名**: 采用大写蛇形，导出为常量对象
- **结构**: 每个枚举项包含 `name`（显示名称）、`value`（枚举值）、`tagUrl`（可选，标签图片）等字段
- **示例**:
  ```typescript
  // src/dict/user.ts
  export const USER_STATUS = {
    ENABLED: {
      name: '启用',
      value: 1,
      tagType: 'success',
    },
    DISABLED: {
      name: '禁用',
      value: 0,
      tagType: 'danger',
    },
  };
  
  export const GENDER = {
    MALE: {
      name: '男',
      value: 1,
    },
    FEMALE: {
      name: '女',
      value: 2,
    },
  };
  
  // 使用方式
  const userStatus = USER_STATUS.ENABLED.value; // 1
  const displayName = USER_STATUS.ENABLED.name; // '启用'
  const tagType = USER_STATUS.ENABLED.tagType; // 'success'
  ```
- **最佳实践**: 配合 Select 组件使用枚举字段选择，确保选项统一管理和用户体验一致
- **Table 表格集成**: 当 table 列需要渲染状态标签时，根据枚举值匹配显示

### 14. Dict 字典型弹窗规范
实现多种确认弹窗场景（成功、删除、警告等），使用字典对象管理弹窗配置，支持动态类型切换。

- **配置结构**: 使用 `reactive` 定义 `dict` 对象，每个弹窗类型包含 `title`、`content`、`confirmText`、`cancelText`、`value` 等字段
- **类型管理**: 定义 `visibleType` 和 `modalVisible` 两个 ref，分别控制弹窗类型和显示状态
- **列表转换**: 使用工具方法将字典对象转换为列表，通过 `visibleType` 索引获取对应配置
- **事件处理**: 在 `@success` 和 `@fail` 中根据 `visibleType` 判断操作类型，执行相应业务逻辑
- **示例结构**:
  ```typescript
  const dict = reactive({
    submitSuccess: {
      title: '提交成功',
      content: '您的提交已成功',
      value: 0,
      confirmText: '返回列表',
      cancelText: '继续编辑',
    },
    deleteConfirm: {
      title: '确认删除',
      content: `确定要删除选中的数据吗？`,
      value: 1,
      confirmText: '确定',
      cancelText: '取消',
    },
  });
  
  const modalVisible = ref(false);
  const visibleType = ref(0);
  
  // 根据类型显示弹窗
  const showModal = (type: string) => {
    visibleType.value = dict[type].value;
    modalVisible.value = true;
  };
  
  // 处理确认
  const handleSuccess = () => {
    modalVisible.value = false;
    if (visibleType.value === dict.submitSuccess.value) {
      // 处理提交成功
    } else if (visibleType.value === dict.deleteConfirm.value) {
      // 处理删除确认
    }
  };
  ```
- **规范示例**:
  ```vue
  <template>
    <div class="container p-4">
      <el-button @click="showModal('submitSuccess')">提交</el-button>
      <el-button type="danger" @click="showModal('deleteConfirm')">删除</el-button>

      <!-- Dict 类型弹窗 -->
      <el-dialog
        v-model="modalVisible"
        :title="dict[visibleType].title"
        width="400px"
      >
        <div class="p-4 text-center">
          <div class="text-lg font-medium">{{ dict[visibleType].title }}</div>
          <div class="mt-2 text-gray-500">{{ dict[visibleType].content }}</div>
        </div>
        <template #footer>
          <el-button @click="handleCancel">{{ dict[visibleType].cancelText }}</el-button>
          <el-button type="primary" @click="handleSuccess">{{ dict[visibleType].confirmText }}</el-button>
        </template>
      </el-dialog>
    </div>
  </template>
  
  <script setup lang="ts">
  import { ref, reactive } from 'vue';
  import { ElMessage } from 'element-plus';
  
  const modalVisible = ref(false);
  const visibleType = ref(0);
  
  const dict = reactive({
    submitSuccess: {
      title: '提交成功',
      content: '您的提交已成功',
      value: 0,
      confirmText: '返回列表',
      cancelText: '继续编辑',
    },
    deleteConfirm: {
      title: '确认删除',
      content: '确定要删除选中的数据吗？',
      value: 1,
      confirmText: '确定',
      cancelText: '取消',
    },
  });
  
  const showModal = (type: keyof typeof dict) => {
    visibleType.value = dict[type].value;
    modalVisible.value = true;
  };
  
  const handleSuccess = () => {
    modalVisible.value = false;
    if (visibleType.value === dict.submitSuccess.value) {
      ElMessage.success('操作成功');
    } else if (visibleType.value === dict.deleteConfirm.value) {
      ElMessage.success('删除成功');
    }
  };
  
  const handleCancel = () => {
    modalVisible.value = false;
  };
  </script>
  ```

### 15. Loading 加载状态规范
所有异步操作（请求、提交、删除等）都需要添加 loading 状态，防止用户重复操作。

- **按钮 Loading**: 提交、删除等操作按钮
- **表格 Loading**: 数据加载时显示
- **示例**:
  ```typescript
  // 定义 loading 状态
  const submitLoading = ref(false);
  const deleteLoadingMap = ref<Record<string, boolean>>({});
  
  // 提交时使用
  async function handleSubmit() {
    if (submitLoading.value) return; // 防止重复提交
    
    submitLoading.value = true;
    try {
      await createModuleApi(formData.value);
      ElMessage.success('提交成功');
    } catch (error) {
      ElMessage.error('提交失败');
    } finally {
      submitLoading.value = false; // 无论成功失败都重置
    }
  }
  ```
- **模板中使用**:
  ```vue
  <el-button type="primary" :loading="submitLoading" @click="handleSubmit">
    {{ submitLoading ? '提交中...' : '提交' }}
  </el-button>
  ```

### 16. 防抖（Debounce）规范
对于频繁触发的事件（搜索输入等），使用防抖减少不必要的请求。

- **使用 VueUse**: 项目已集成 VueUse，推荐使用 `useDebounceFn`
- **常见场景**: 搜索输入、表单验证、窗口调整
- **示例**:
  ```typescript
  import { useDebounceFn } from '@vueuse/core';
  
  const searchKeyword = ref('');
  
  // 防抖搜索（300ms 延迟）
  const handleSearch = useDebounceFn(() => {
    refreshTable();
  }, 300);
  
  // 监听输入变化
  function onKeywordChange() {
    handleSearch();
  }
  ```

### 17. 请求的 try/catch/finally 规范
所有 API 请求都必须使用 try/catch/finally 进行错误处理。

- **标准模式**:
  ```typescript
  const loading = ref(false);
  
  async function handleRequest() {
    if (loading.value) return; // 1. 检查是否正在请求
    
    loading.value = true; // 2. 开始请求，设置 loading
    try {
      const result = await someApi(); // 3. 执行请求
      ElMessage.success('操作成功'); // 4. 处理成功结果
      return result;
    } catch (error) {
      console.error('请求失败', error); // 5. 处理错误
      ElMessage.error('操作失败，请重试');
    } finally {
      loading.value = false; // 6. 无论成功失败，都重置 loading
    }
  }
  ```
- **错误处理最佳实践**:
  ```typescript
  function handleApiError(error: any, defaultMessage = '操作失败') {
    if (error.response) {
      const { status, data } = error.response;
      switch (status) {
        case 400: ElMessage.error(data.message || '请求参数错误'); break;
        case 401: ElMessage.error('登录已过期'); break;
        case 403: ElMessage.error('没有权限'); break;
        case 404: ElMessage.error('资源不存在'); break;
        case 500: ElMessage.error('服务器错误'); break;
        default: ElMessage.error(data.message || defaultMessage);
      }
    } else {
      ElMessage.error('网络错误，请检查网络');
    }
  }
  ```

### 18. 数据回显规范
在编辑表单或详情页面进行数据回显时，使用 `assignParentValuesToChild` 工具函数进行数据赋值。

- **函数位置**: [`apps/web-ele/src/utils/index.ts`](apps/web-ele/src/utils/index.ts)
- **使用场景**:
  - 编辑表单回显后端返回的数据
  - 详情页面展示数据
  - 需要将后端数据结构映射到前端表单结构
- **函数签名**:
  ```typescript
  function assignParentValuesToChild(
    parent: Record<string, any>,  // 父级对象（后端返回的数据）
    child: Record<string, any>,   // 子级对象（表单数据对象）
    config?: Record<string, string> // 可选的字段映射配置
  ): Record<string, any>
  ```
- **基础用法**:
  ```typescript
  import { assignParentValuesToChild } from '#/utils';
  
  // 后端返回的数据
  const apiData = {
    id: '123',
    username: 'admin',
    realName: '管理员',
    mobile: '13800138000',
    email: 'admin@example.com',
    status: 1,
  };
  
  // 表单数据对象
  const formData = reactive({
    username: '',
    realName: '',
    mobile: '',
    email: '',
    status: 0,
  });
  
  // 回显数据（自动匹配同名字段）
  assignParentValuesToChild(apiData, formData);
  ```
- **字段映射用法**:
  ```typescript
  // 当后端字段名与前端不一致时，使用 config 参数进行映射
  const apiData = {
    user_name: 'admin',      // 后端使用下划线命名
    real_name: '管理员',
    phone_number: '13800138000',
  };
  
  const formData = reactive({
    username: '',            // 前端使用驼峰命名
    realName: '',
    mobile: '',
  });
  
  // 配置字段映射: { 前端字段名: 后端字段名 }
  const fieldMapping = {
    username: 'user_name',
    realName: 'real_name',
    mobile: 'phone_number',
  };
  
  assignParentValuesToChild(apiData, formData, fieldMapping);
  ```
- **完整示例**:
  ```vue
  <script setup lang="ts">
  import { reactive, onMounted } from 'vue';
  import { getUserDetailApi } from '#/api/user';
  import { assignParentValuesToChild } from '#/utils';
  
  interface FormData {
    username: string;
    realName: string;
    mobile: string;
    email?: string;
    status: number;
  }
  
  const formData = reactive<FormData>({
    username: '',
    realName: '',
    mobile: '',
    email: '',
    status: 1,
  });
  
  // 获取用户详情并回显
  async function fetchUserDetail(id: string) {
    try {
      const data = await getUserDetailApi(id);
      // 使用工具函数进行数据回显
      assignParentValuesToChild(data, formData);
    } catch (error) {
      console.error('获取用户详情失败', error);
    }
  }
  
  onMounted(() => {
    const userId = '123';
    fetchUserDetail(userId);
  });
  </script>
  ```
- **注意事项**:
  - 该函数只会赋值 `child` 对象中已存在的字段，不会添加新字段
  - 如果 `parent` 中不存在对应字段，`child` 中的字段值保持不变
  - 使用 `config` 参数可以灵活处理前后端字段名不一致的情况
  - 建议在表单初始化时先定义好所有字段及默认值，再使用该函数进行回显

## 补充说明
- 若项目特性有变更（新增依赖、配置调整），需同步更新本规范
- 遇到 Element Plus 组件问题，优先查阅 Element Plus 官方文档
- 遇到 Vben 框架问题，优先查阅项目 CLAUDE.md 和 docs/ 目录
