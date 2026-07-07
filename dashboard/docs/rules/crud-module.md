---
description: 通用 CRUD 模块开发规范
globs:
alwaysApply: false
---

# 通用 CRUD 模块开发规范

本规范适用于标准的增删改查（CRUD）业务模块开发。

## 功能规范模板

当需要开发一个新的 CRUD 模块时，请按以下结构描述需求：

```markdown
# 功能规范：[模块名称]

## 1. 功能概述
[一句话描述模块功能]

## 2. 页面布局
- 顶部：搜索栏 + 操作按钮
- 中间：数据表格
- 底部：分页器
- 弹窗：新增/编辑表单

## 3. 功能清单
- [ ] 列表查询（分页、搜索、筛选）
- [ ] 新增数据
- [ ] 编辑数据
- [ ] 删除数据（单条/批量）
- [ ] 状态切换（如有）
- [ ] 导出功能（如需）

## 4. 字段定义

### 表格列
| 字段名 | 显示名称 | 宽度 | 是否排序 | 其他 |
|--------|----------|------|----------|------|
| id | ID | 80px | ✅ | - |
| name | 名称 | 150px | - | - |
| status | 状态 | 80px | - | Tag 显示 |
| createTime | 创建时间 | 160px | ✅ | 格式化显示 |
| actions | 操作 | 150px | - | 编辑、删除 |

### 表单字段
| 字段名 | 显示名称 | 组件类型 | 是否必填 | 验证规则 |
|--------|----------|----------|----------|----------|
| name | 名称 | VbenInput | ✅ | 2-50字符 |
| code | 编码 | VbenInput | ✅ | 字母数字 |
| status | 状态 | VbenSelect | - | 默认启用 |
| remark | 备注 | VbenTextarea | - | 最多200字 |

## 5. 接口定义

### 接口列表
| 接口名称 | 方法 | 路径 | 说明 |
|----------|------|------|------|
| 获取列表 | GET | /api/[module]/list | 支持分页和筛选 |
| 获取详情 | GET | /api/[module]/:id | - |
| 新增 | POST | /api/[module] | - |
| 编辑 | PUT | /api/[module]/:id | - |
| 删除 | DELETE | /api/[module]/:id | - |
| 批量删除 | DELETE | /api/[module]/batch | - |

### 响应格式
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "items": [...],
    "total": 100
  }
}
```

## 6. 权限配置
- 菜单权限：[module]:list
- 新增权限：[module]:add
- 编辑权限：[module]:edit
- 删除权限：[module]:delete
```

## 文件生成规范

### 1. API 接口文件

位置：`apps/web-ele/src/api/[module].ts`

```typescript
import { requestClient } from '#/api/request';

// 类型定义
export interface [Module]Item {
  id: string;
  name: string;
  code: string;
  status: number;
  remark?: string;
  createTime: string;
  updateTime?: string;
}

export interface [Module]ListParams {
  page: number;
  pageSize: number;
  name?: string;
  status?: number;
}

export interface [Module]FormData {
  id?: string;
  name: string;
  code: string;
  status: number;
  remark?: string;
}

// 获取列表
export async function get[Module]ListApi(params: [Module]ListParams) {
  return requestClient.get<{ items: [Module]Item[]; total: number }>('/[module]/list', {
    params,
  });
}

// 获取详情
export async function get[Module]DetailApi(id: string) {
  return requestClient.get<[Module]Item>(`/[module]/${id}`);
}

// 新增
export async function create[Module]Api(data: [Module]FormData) {
  return requestClient.post<[Module]Item>('/[module]', data);
}

// 编辑
export async function update[Module]Api(id: string, data: [Module]FormData) {
  return requestClient.put<[Module]Item>(`/[module]/${id}`, data);
}

// 删除
export async function delete[Module]Api(id: string) {
  return requestClient.delete(`/[module]/${id}`);
}

// 批量删除
export async function batchDelete[Module]Api(ids: string[]) {
  return requestClient.delete('/[module]/batch', { data: { ids } });
}
```

### 2. 路由配置文件

位置：`apps/web-ele/src/router/routes/modules/[module].ts`

```typescript
import type { RouteRecordRaw } from 'vue-router';

import { $t } from '#/locales';

const routes: RouteRecordRaw[] = [
  {
    meta: {
      icon: 'lucide:[icon-name]',
      title: $t('routes.[module].title'),
      order: 1,
    },
    name: '[Module]Management',
    path: '/[module-path]',
    children: [
      {
        name: '[Module]List',
        path: '/[module-path]/list',
        component: () => import('#/views/[module]/index.vue'),
        meta: {
          icon: 'lucide:list',
          title: $t('routes.[module].list'),
          authority: ['[module]:list'],
        },
      },
    ],
  },
];

export default routes;
```

### 3. 列表页面组件

位置：`apps/web-ele/src/views/[module]/index.vue`

```vue
<script lang="ts" setup>
import { ref } from 'vue';
import { useVbenVxeGrid } from '#/adapter/vxe-table';
import type { VxeTableGridOptions } from '#/adapter/vxe-table';
import { ElMessage, ElMessageBox } from 'element-plus';

import {
  get[Module]ListApi,
  delete[Module]Api,
  batchDelete[Module]Api,
} from '#/api/[module]';
import FormModal from './FormModal.vue';

// 弹窗控制
const formVisible = ref(false);
const formData = ref<Record<string, any>>({});
const isEdit = ref(false);

// 使用 useVbenVxeGrid 创建表格
const [Grid, gridApi] = useVbenVxeGrid({
  gridOptions: {
    columns: [
      { type: 'checkbox', width: 50 },
      { field: 'name', title: '名称', minWidth: 150 },
      { field: 'code', title: '编码', minWidth: 120 },
      { 
        field: 'status', 
        title: '状态', 
        minWidth: 80, 
        slots: { default: 'status' } 
      },
      { field: 'createTime', title: '创建时间', minWidth: 160 },
      { 
        field: 'actions', 
        title: '操作', 
        minWidth: 150, 
        fixed: 'right',
        slots: { default: 'actions' } 
      },
    ] as VxeTableGridOptions['columns'],
    proxyConfig: {
      ajax: {
        query: async ({ page }) => {
          try {
            const res = await get[Module]ListApi({
              pageNum: page.currentPage,
              pageSize: page.pageSize,
            });
            return { items: res.items, total: res.total };
          } catch (error) {
            ElMessage.error('获取列表失败');
            return { items: [], total: 0 };
          }
        },
      },
    },
    pagerConfig: {
      pageSize: 20,
      pageSizes: [10, 20, 50, 100],
    },
    checkboxConfig: {
      reserve: true,
    },
  },
});

// 新增
function handleAdd() {
  isEdit.value = false;
  formData.value = { status: 1 };
  formVisible.value = true;
}

// 编辑
function handleEdit(row: any) {
  isEdit.value = true;
  formData.value = { ...row };
  formVisible.value = true;
}

// 删除
async function handleDelete(id: string) {
  await ElMessageBox.confirm('确定要删除该记录吗？', '提示', {
    type: 'warning',
  });
  
  try {
    await delete[Module]Api(id);
    ElMessage.success('删除成功');
    gridApi.reload();
  } catch (error) {
    ElMessage.error('删除失败');
  }
}

// 批量删除
async function handleBatchDelete() {
  const selectedRows = gridApi.getCheckboxRecords();
  if (selectedRows.length === 0) {
    ElMessage.warning('请选择要删除的数据');
    return;
  }
  
  await ElMessageBox.confirm(`确定要删除选中的 ${selectedRows.length} 条记录吗？`, '提示', {
    type: 'warning',
  });
  
  try {
    const ids = selectedRows.map((row: any) => row.id);
    await batchDelete[Module]Api(ids);
    ElMessage.success('批量删除成功');
    gridApi.reload();
  } catch (error) {
    ElMessage.error('批量删除失败');
  }
}
</script>

<template>
  <div class="p-4">
    <!-- 操作栏 -->
    <div class="mb-4 flex gap-2">
      <el-button type="primary" @click="handleAdd">新增</el-button>
      <el-button type="danger" @click="handleBatchDelete">批量删除</el-button>
    </div>

    <!-- 表格 -->
    <Grid>
      <template #status="{ row }">
        <el-tag :type="row.status === 1 ? 'success' : 'danger'">
          {{ row.status === 1 ? '启用' : '禁用' }}
        </el-tag>
      </template>
      
      <template #actions="{ row }">
        <el-button type="primary" link @click="handleEdit(row)">编辑</el-button>
        <el-button type="danger" link @click="handleDelete(row.id)">删除</el-button>
      </template>
    </Grid>

    <!-- 表单弹窗 -->
    <FormModal 
      v-model:visible="formVisible" 
      v-model:data="formData" 
      :is-edit="isEdit"
      @success="gridApi.reload()"
    />
  </div>
</template>
```

### 4. 表单弹窗组件

位置：`apps/web-ele/src/views/[module]/FormModal.vue`

```vue
<script lang="ts" setup>
import { computed } from 'vue';
import { VbenForm, z } from '@vben/common-ui';
import type { VbenFormSchema } from '@vben/common-ui';
import { ElMessage } from 'element-plus';

import { create[Module]Api, update[Module]Api } from '#/api/[module]';

const props = defineProps<{
  isEdit: boolean;
}>();

const visible = defineModel<boolean>('visible');
const formData = defineModel<Record<string, any>>('data');

const emit = defineEmits<{
  success: [];
}>();

const formSchema = computed((): VbenFormSchema[] => [
  {
    component: 'VbenInput',
    fieldName: 'name',
    label: '名称',
    rules: z.string().min(2, '名称至少2个字符').max(50, '名称最多50个字符'),
    componentProps: {
      placeholder: '请输入名称',
    },
  },
  {
    component: 'VbenInput',
    fieldName: 'code',
    label: '编码',
    rules: z.string().regex(/^[a-zA-Z0-9]+$/, '编码只能包含字母和数字'),
    componentProps: {
      placeholder: '请输入编码',
      disabled: props.isEdit,
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
  {
    component: 'VbenTextarea',
    fieldName: 'remark',
    label: '备注',
    componentProps: {
      placeholder: '请输入备注',
      maxlength: 200,
      showWordLimit: true,
    },
  },
]);

// 提交表单
async function handleSubmit() {
  try {
    if (props.isEdit && formData.value.id) {
      await update[Module]Api(formData.value.id, formData.value);
      ElMessage.success('编辑成功');
    } else {
      await create[Module]Api(formData.value);
      ElMessage.success('新增成功');
    }
    visible.value = false;
    emit('success');
  } catch (error) {
    console.error('提交失败', error);
  }
}

// 取消
function handleCancel() {
  visible.value = false;
}
</script>

<template>
  <el-dialog
    v-model="visible"
    :title="isEdit ? '编辑' : '新增'"
    width="500px"
    destroy-on-close
  >
    <VbenForm :schema="formSchema" :values="formData" />
    
    <template #footer>
      <el-button @click="handleCancel">取消</el-button>
      <el-button type="primary" @click="handleSubmit">确定</el-button>
    </template>
  </el-dialog>
</template>
```

### 5. Mock 数据文件

位置：`apps/web-ele/src/mock/modules/[module].ts`

```typescript
// Mock 接口写法统一遵循：./common/mock-module.md
// 包含：checkAuth / responseSuccess / pageResponseSuccess / pagination / getQueryParams / extractPathParams
// CRUD 场景建议至少实现：list / detail / create / update / delete / batch-delete
```

**注册 Mock 模块**

在 `apps/web-ele/src/mock/index.ts` 中导入并注册：

```typescript
import { setup[Module]Mock } from './modules/[module]';

// 注册所有 Mock
setup[Module]Mock();
```

详细实现参考：`./common/mock-module.md`

## 开发流程

1. **定义接口类型**：在 `apps/web-ele/src/api/[module].ts` 中定义类型和接口函数
2. **配置路由**：在 `apps/web-ele/src/router/routes/modules/[module].ts` 中添加路由
3. **创建页面**：在 `apps/web-ele/src/views/[module]/index.vue` 中实现列表页
4. **创建表单**：在 `apps/web-ele/src/views/[module]/FormModal.vue` 中实现表单弹窗
5. **添加 Mock**：在 `apps/web-ele/src/mock/modules/[module].ts` 中添加 Mock 接口
6. **注册 Mock**：在 `apps/web-ele/src/mock/index.ts` 中导入并调用 setup 函数
7. **添加国际化**（可选）：在 `apps/web-ele/src/locales/langs/zh-CN/` 中添加文案

## 注意事项

- 所有文件使用 TypeScript，禁止 any 类型
- 使用 Element Plus 组件，不要使用 Ant Design Vue
- 表格使用 `useVbenVxeGrid` 创建 `<Grid>` 组件，不要使用 `VbenVxeTable`
- 使用 `gridApi.reload()` 刷新表格，使用 `gridApi.getCheckboxRecords()` 获取选中行
- 表单验证使用 zod
- 删除操作需要二次确认
- Mock 数据要真实感，使用 `Mock.Random` 生成真实的中文数据
- Mock 接口必须使用 `checkAuth()` 进行权限验证
- Mock 响应格式统一使用 `responseSuccess()` 和 `responseError()`

## 相关通用规范

开发 CRUD 模块时，还需要遵循以下通用规范：

- [枚举开发规范](./common/enum.md) - 避免魔法数字，统一枚举管理
- [Loading 状态规范](./common/loading.md) - 防止重复操作，提升用户体验
- [防抖规范](./common/debounce.md) - 优化高频事件处理
- [错误处理规范](./common/error-handling.md) - 统一 try/catch/finally 模式
- [Dict 弹窗规范](./common/dict-modal.md) - 字典型弹窗管理
- [数据回显规范](./common/data-echo.md) - 使用 assignParentValuesToChild 工具函数
- [Mock 模块规范](./common/mock-module.md) - 统一 web-ele + mockjs Mock 实现
