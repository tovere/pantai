---
description: 树形结构模块开发规范
globs:
alwaysApply: false
---

# 树形结构模块开发规范

本规范适用于具有层级关系的数据模块开发，如部门管理、菜单管理、分类管理等。

## 功能规范模板

```markdown
# 功能规范：[树形模块名称]

## 1. 功能概述
管理具有层级关系的数据，支持无限级树形结构。

## 2. 页面布局
- 左侧：树形结构（可折叠、搜索）
- 右侧：选中节点的详情或子项列表
- 或者：纯树形表格展示

## 3. 数据结构

### 树形节点
| 字段名 | 类型 | 说明 |
|--------|------|------|
| id | string | 节点ID |
| parentId | string | 父节点ID（根节点为空或0） |
| name | string | 节点名称 |
| code | string | 节点编码 |
| sort | number | 排序值 |
| status | number | 状态 |
| children | TreeNode[] | 子节点列表 |

## 4. 功能清单
- [ ] 树形展示（展开/折叠）
- [ ] 节点搜索
- [ ] 新增节点（支持选择父节点）
- [ ] 编辑节点
- [ ] 删除节点（需检查是否有子节点）
- [ ] 拖拽排序
- [ ] 批量操作

## 5. 接口定义
| 接口名称 | 方法 | 路径 | 说明 |
|----------|------|------|------|
| 获取树形数据 | GET | /api/[module]/tree | 获取完整树 |
| 获取节点详情 | GET | /api/[module]/:id | - |
| 新增节点 | POST | /api/[module] | - |
| 编辑节点 | PUT | /api/[module]/:id | - |
| 删除节点 | DELETE | /api/[module]/:id | - |
| 更新排序 | PUT | /api/[module]/sort | 批量更新 |
```

## 文件生成规范

### 1. API 接口文件

位置：`apps/web-ele/src/api/[module].ts`

```typescript
import { requestClient } from '#/api/request';

// 树形节点类型
export interface TreeNode {
  id: string;
  parentId: string | null;
  name: string;
  code: string;
  sort: number;
  status: number;
  children?: TreeNode[];
  createTime?: string;
}

export interface TreeNodeFormData {
  id?: string;
  parentId: string | null;
  name: string;
  code: string;
  sort: number;
  status: number;
}

// 获取树形数据
export async function get[Module]TreeApi() {
  return requestClient.get<TreeNode[]>('/[module]/tree');
}

// 获取节点详情
export async function get[Module]DetailApi(id: string) {
  return requestClient.get<TreeNode>(`/[module]/${id}`);
}

// 新增节点
export async function create[Module]Api(data: TreeNodeFormData) {
  return requestClient.post<TreeNode>('/[module]', data);
}

// 编辑节点
export async function update[Module]Api(id: string, data: TreeNodeFormData) {
  return requestClient.put<TreeNode>(`/[module]/${id}`, data);
}

// 删除节点
export async function delete[Module]Api(id: string) {
  return requestClient.delete(`/[module]/${id}`);
}

// 更新排序
export async function update[Module]SortApi(data: { id: string; sort: number }[]) {
  return requestClient.put('/[module]/sort', data);
}
```

### 2. 树形页面（左右布局）

位置：`apps/web-ele/src/views/[module]/index.vue`

```vue
<script lang="ts" setup>
import { ref, onMounted } from 'vue';
import { ElMessage, ElMessageBox } from 'element-plus';
import type { FormInstance } from 'element-plus';

import { get[Module]TreeApi, create[Module]Api, update[Module]Api, delete[Module]Api } from '#/api/[module]';
import type { TreeNode, TreeNodeFormData } from '#/api/[module]';

// 树形数据
const treeData = ref<TreeNode[]>([]);
const expandedKeys = ref<string[]>([]);
const selectedNode = ref<TreeNode | null>(null);
const filterText = ref('');

// 表单控制
const formVisible = ref(false);
const formData = ref<TreeNodeFormData>({
  parentId: null,
  name: '',
  code: '',
  sort: 0,
  status: 1,
});
const isEdit = ref(false);
const formRef = ref<FormInstance>();

// 加载树形数据
async function loadTree() {
  try {
    const res = await get[Module]TreeApi();
    treeData.value = res;
    // 默认展开第一级
    expandedKeys.value = res.map((item) => item.id);
  } catch (error) {
    ElMessage.error('加载数据失败');
  }
}

// 过滤节点
function filterNode(value: string, data: TreeNode) {
  if (!value) return true;
  return data.name.includes(value);
}

// 选中节点
function handleNodeClick(data: TreeNode) {
  selectedNode.value = data;
}

// 新增根节点
function handleAddRoot() {
  isEdit.value = false;
  formData.value = {
    parentId: null,
    name: '',
    code: '',
    sort: 0,
    status: 1,
  };
  formVisible.value = true;
}

// 新增子节点
function handleAddChild(node: TreeNode) {
  isEdit.value = false;
  formData.value = {
    parentId: node.id,
    name: '',
    code: '',
    sort: 0,
    status: 1,
  };
  formVisible.value = true;
}

// 编辑节点
function handleEdit(node: TreeNode) {
  isEdit.value = true;
  formData.value = {
    id: node.id,
    parentId: node.parentId,
    name: node.name,
    code: node.code,
    sort: node.sort,
    status: node.status,
  };
  formVisible.value = true;
}

// 删除节点
async function handleDelete(node: TreeNode) {
  if (node.children && node.children.length > 0) {
    ElMessage.warning('请先删除子节点');
    return;
  }
  
  await ElMessageBox.confirm('确定要删除该节点吗？', '提示', { type: 'warning' });
  await delete[Module]Api(node.id);
  ElMessage.success('删除成功');
  loadTree();
}

// 提交表单
async function handleSubmit() {
  await formRef.value?.validate();
  
  if (isEdit.value && formData.value.id) {
    await update[Module]Api(formData.value.id, formData.value);
    ElMessage.success('编辑成功');
  } else {
    await create[Module]Api(formData.value);
    ElMessage.success('新增成功');
  }
  
  formVisible.value = false;
  loadTree();
}

onMounted(() => {
  loadTree();
});
</script>

<template>
  <div class="p-4 flex gap-4 h-full">
    <!-- 左侧树形结构 -->
    <div class="w-80 bg-white rounded-lg p-4 flex flex-col">
      <div class="mb-4 flex justify-between items-center">
        <span class="font-medium">组织架构</span>
        <el-button type="primary" size="small" @click="handleAddRoot">
          新增
        </el-button>
      </div>
      
      <el-input
        v-model="filterText"
        placeholder="搜索..."
        class="mb-4"
        clearable
      />
      
      <el-tree
        :data="treeData"
        :props="{ label: 'name', children: 'children' }"
        :expand-on-click-node="false"
        :filter-node-method="filterNode"
        :default-expanded-keys="expandedKeys"
        node-key="id"
        highlight-current
        class="flex-1 overflow-auto"
        @node-click="handleNodeClick"
      >
        <template #default="{ node, data }">
          <div class="flex items-center justify-between w-full group">
            <span>{{ data.name }}</span>
            <div class="opacity-0 group-hover:opacity-100">
              <el-button type="primary" link size="small" @click.stop="handleAddChild(data)">
                添加
              </el-button>
              <el-button type="primary" link size="small" @click.stop="handleEdit(data)">
                编辑
              </el-button>
              <el-button type="danger" link size="small" @click.stop="handleDelete(data)">
                删除
              </el-button>
            </div>
          </div>
        </template>
      </el-tree>
    </div>

    <!-- 右侧详情 -->
    <div class="flex-1 bg-white rounded-lg p-4">
      <template v-if="selectedNode">
        <h3 class="text-lg font-medium mb-4">{{ selectedNode.name }}</h3>
        <el-descriptions :column="2" border>
          <el-descriptions-item label="名称">{{ selectedNode.name }}</el-descriptions-item>
          <el-descriptions-item label="编码">{{ selectedNode.code }}</el-descriptions-item>
          <el-descriptions-item label="排序">{{ selectedNode.sort }}</el-descriptions-item>
          <el-descriptions-item label="状态">
            <el-tag :type="selectedNode.status === 1 ? 'success' : 'danger'">
              {{ selectedNode.status === 1 ? '启用' : '禁用' }}
            </el-tag>
          </el-descriptions-item>
        </el-descriptions>
      </template>
      <template v-else>
        <div class="text-gray-400 text-center py-20">
          请选择左侧节点查看详情
        </div>
      </template>
    </div>

    <!-- 表单弹窗 -->
    <el-dialog
      v-model="formVisible"
      :title="isEdit ? '编辑' : '新增'"
      width="500px"
      destroy-on-close
    >
      <el-form
        ref="formRef"
        :model="formData"
        :rules="{
          name: [{ required: true, message: '请输入名称', trigger: 'blur' }],
          code: [{ required: true, message: '请输入编码', trigger: 'blur' }],
        }"
        label-width="80px"
      >
        <el-form-item label="上级节点">
          <el-tree-select
            v-model="formData.parentId"
            :data="treeData"
            :props="{ label: 'name', children: 'children', value: 'id' }"
            placeholder="选择上级节点（不选则为根节点）"
            clearable
            check-strictly
          />
        </el-form-item>
        <el-form-item label="名称" prop="name">
          <el-input v-model="formData.name" placeholder="请输入名称" />
        </el-form-item>
        <el-form-item label="编码" prop="code">
          <el-input v-model="formData.code" placeholder="请输入编码" />
        </el-form-item>
        <el-form-item label="排序">
          <el-input-number v-model="formData.sort" :min="0" />
        </el-form-item>
        <el-form-item label="状态">
          <el-radio-group v-model="formData.status">
            <el-radio :value="1">启用</el-radio>
            <el-radio :value="0">禁用</el-radio>
          </el-radio-group>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="formVisible = false">取消</el-button>
        <el-button type="primary" @click="handleSubmit">确定</el-button>
      </template>
    </el-dialog>
  </div>
</template>
```

### 3. 树形表格页面

位置：`apps/web-ele/src/views/[module]/TreeTable.vue`

```vue
<script lang="ts" setup>
import { ref, onMounted } from 'vue';
import { useVbenVxeGrid } from '#/adapter/vxe-table';
import type { VxeTableGridOptions } from '#/adapter/vxe-table';
import { ElMessage, ElMessageBox } from 'element-plus';

import { get[Module]TreeApi, delete[Module]Api } from '#/api/[module]';
import type { TreeNode } from '#/api/[module]';

const formVisible = ref(false);
const formData = ref<Record<string, any>>({});
const isEdit = ref(false);

// 使用 useVbenVxeGrid 创建表格
const [Grid, gridApi] = useVbenVxeGrid({
  gridOptions: {
    columns: [
      { field: 'name', title: '名称', minWidth: 200, treeNode: true },
      { field: 'code', title: '编码', minWidth: 120 },
      { field: 'sort', title: '排序', minWidth: 80 },
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
        minWidth: 200, 
        slots: { default: 'actions' } 
      },
    ] as VxeTableGridOptions['columns'],
    treeConfig: {
      parentField: 'parentId',
      rowField: 'id',
      transform: true,
      expandAll: true,
    },
    proxyConfig: {
      ajax: {
        query: async () => {
          try {
            const res = await get[Module]TreeApi();
            return { items: res, total: res.length };
          } catch (error) {
            ElMessage.error('获取数据失败');
            return { items: [], total: 0 };
          }
        },
      },
    },
  },
});

// 新增
function handleAdd(row?: TreeNode) {
  isEdit.value = false;
  formData.value = {
    parentId: row?.id ?? null,
    name: '',
    code: '',
    sort: 0,
    status: 1,
  };
  formVisible.value = true;
}

// 编辑
function handleEdit(row: TreeNode) {
  isEdit.value = true;
  formData.value = { ...row };
  formVisible.value = true;
}

// 删除
async function handleDelete(row: TreeNode) {
  if (row.children && row.children.length > 0) {
    ElMessage.warning('请先删除子节点');
    return;
  }
  
  await ElMessageBox.confirm('确定要删除吗？', '提示', { type: 'warning' });
  
  try {
    await delete[Module]Api(row.id);
    ElMessage.success('删除成功');
    gridApi.reload();
  } catch (error) {
    ElMessage.error('删除失败');
  }
}

onMounted(() => {
  gridApi.reload();
});
</script>

<template>
  <div class="p-4">
    <div class="mb-4">
      <el-button type="primary" @click="handleAdd()">新增根节点</el-button>
    </div>

    <Grid>
      <template #status="{ row }">
        <el-tag :type="row.status === 1 ? 'success' : 'danger'">
          {{ row.status === 1 ? '启用' : '禁用' }}
        </el-tag>
      </template>
      
      <template #actions="{ row }">
        <el-button type="primary" link @click="handleAdd(row)">添加子节点</el-button>
        <el-button type="primary" link @click="handleEdit(row)">编辑</el-button>
        <el-button type="danger" link @click="handleDelete(row)">删除</el-button>
      </template>
    </Grid>
  </div>
</template>
```

### 4. Mock 数据文件

位置：`apps/web-ele/src/mock/[module].ts`

```typescript
// Mock 接口写法统一遵循：./common/mock-module.md
// Tree 场景补充：
// 1) 保留 parentId / children 字段
// 2) 提供 /api/[module]/tree 接口返回树结构
// 3) 详情/编辑/删除按路径参数实现
// 4) 排序接口可扩展 /api/[module]/sort
```

详细实现参考：`./common/mock-module.md`

## 常用场景

### 部门管理
- 左侧部门树 + 右侧部门成员列表
- 支持拖拽调整层级

### 菜单管理
- 树形表格展示
- 支持图标选择、权限配置

### 分类管理
- 商品分类、文章分类等
- 通常最多3级

### 区域管理
- 省市区三级联动
- 数据量较大，建议懒加载

## 注意事项

1. **删除前检查**：删除节点前必须检查是否有子节点
2. **循环引用**：编辑时不能将父节点设置为自己或自己的子节点
3. **数据量**：数据量大时使用懒加载，避免一次性加载过多
4. **排序**：同级节点需要支持排序功能
5. **搜索**：树形搜索需要展开匹配节点的所有父节点

## 相关通用规范

- [Loading 状态规范](./common/loading.md)
- [错误处理规范](./common/error-handling.md)
- [枚举开发规范](./common/enum.md)
- [Mock 模块规范](./common/mock-module.md)
