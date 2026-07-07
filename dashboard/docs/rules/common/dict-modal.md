# Dict 字典型弹窗规范

实现多种确认弹窗场景（成功、删除、警告等），使用字典对象管理弹窗配置，支持动态类型切换。

## 配置结构
使用 `reactive` 定义 `dict` 对象，每个弹窗类型包含 `title`、`content`、`confirmText`、`cancelText`、`value` 等字段

## 类型管理
定义 `visibleType` 和 `modalVisible` 两个 ref，分别控制弹窗类型和显示状态

## 事件处理
在确认/取消回调中根据 `visibleType` 判断操作类型，执行相应业务逻辑

## 完整示例

```vue
<script lang="ts" setup>
import { ref, reactive } from 'vue';
import { useVbenVxeGrid } from '#/adapter/vxe-table';
import { ElMessage } from 'element-plus';

// 使用 useVbenVxeGrid 创建表格
const [Grid, gridApi] = useVbenVxeGrid({
  gridOptions: {
    // ...表格配置
  },
});

const selectedIds = ref<string[]>([]);

// Dict 弹窗配置
const modalVisible = ref(false);
const visibleType = ref(0);

const dict = reactive({
  deleteConfirm: {
    title: '确认删除',
    content: '确定要删除该记录吗？删除后无法恢复。',
    value: 0,
    confirmText: '确定删除',
    cancelText: '取消',
    type: 'danger' as const,
  },
  batchDeleteConfirm: {
    title: '批量删除确认',
    content: `确定要删除选中的 ${selectedIds.value.length} 条记录吗？`,
    value: 1,
    confirmText: '确定删除',
    cancelText: '取消',
    type: 'danger' as const,
  },
  submitSuccess: {
    title: '操作成功',
    content: '数据已成功保存',
    value: 2,
    confirmText: '确定',
    cancelText: '',
    type: 'success' as const,
  },
});

// 根据类型显示弹窗
function showModal(type: keyof typeof dict) {
  visibleType.value = dict[type].value;
  modalVisible.value = true;
}

// 确认处理
async function handleConfirm() {
  modalVisible.value = false;
  
  if (visibleType.value === dict.deleteConfirm.value) {
    // 执行单条删除
    await deleteApi(currentDeleteId.value);
    ElMessage.success('删除成功');
    refreshTable();
  } else if (visibleType.value === dict.batchDeleteConfirm.value) {
    // 执行批量删除
    await batchDeleteApi(selectedIds.value);
    ElMessage.success('批量删除成功');
    selectedIds.value = [];
    refreshTable();
  } else if (visibleType.value === dict.submitSuccess.value) {
    // 成功后的操作
    // 可以跳转或关闭页面
  }
}

// 取消处理
function handleCancel() {
  modalVisible.value = false;
}

// 删除单条
const currentDeleteId = ref('');
function handleDelete(id: string) {
  currentDeleteId.value = id;
  showModal('deleteConfirm');
}

// 批量删除
function handleBatchDelete() {
  if (selectedIds.value.length === 0) {
    ElMessage.warning('请选择要删除的数据');
    return;
  }
  // 更新批量删除的内容
  dict.batchDeleteConfirm.content = `确定要删除选中的 ${selectedIds.value.length} 条记录吗？`;
  showModal('batchDeleteConfirm');
}

function refreshTable() {
  // 刷新表格数据
  gridApi.reload();
}
</script>

<template>
  <div class="p-4">
    <!-- 操作栏 -->
    <div class="mb-4 flex gap-2">
      <el-button type="primary">新增</el-button>
      <el-button type="danger" @click="handleBatchDelete">批量删除</el-button>
    </div>

    <!-- 表格 -->
    <Grid>
      <template #actions="{ row }">
        <el-button type="primary" link>编辑</el-button>
        <el-button type="danger" link @click="handleDelete(row.id)">删除</el-button>
      </template>
    </Grid>

    <!-- Dict 类型弹窗 -->
    <el-dialog
      v-model="modalVisible"
      :title="Object.values(dict).find((d) => d.value === visibleType)?.title"
      width="400px"
      :close-on-click-modal="false"
    >
      <div class="p-4 text-center">
        <el-icon 
          v-if="Object.values(dict).find((d) => d.value === visibleType)?.type === 'danger'" 
          class="text-red-500 text-4xl mb-4"
        >
          <WarningFilled />
        </el-icon>
        <el-icon 
          v-else-if="Object.values(dict).find((d) => d.value === visibleType)?.type === 'success'" 
          class="text-green-500 text-4xl mb-4"
        >
          <CircleCheckFilled />
        </el-icon>
        <div class="text-base text-gray-600">
          {{ Object.values(dict).find((d) => d.value === visibleType)?.content }}
        </div>
      </div>
      
      <template #footer>
        <el-button 
          v-if="Object.values(dict).find((d) => d.value === visibleType)?.cancelText"
          @click="handleCancel"
        >
          {{ Object.values(dict).find((d) => d.value === visibleType)?.cancelText }}
        </el-button>
        <el-button 
          :type="Object.values(dict).find((d) => d.value === visibleType)?.type === 'danger' ? 'danger' : 'primary'"
          @click="handleConfirm"
        >
          {{ Object.values(dict).find((d) => d.value === visibleType)?.confirmText }}
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>
```

## 工具函数封装

可以封装一个通用的 Dict 弹窗 Hook：

```typescript
// apps/web-ele/src/hooks/useDictModal.ts
import { ref, computed } from 'vue';

export interface DictModalItem {
  title: string;
  content: string;
  value: number;
  confirmText: string;
  cancelText: string;
  type?: 'danger' | 'success' | 'warning' | 'info';
}

export function useDictModal<T extends Record<string, DictModalItem>>(dictConfig: T) {
  const visible = ref(false);
  const visibleType = ref<number>(0);

  const currentConfig = computed(() => {
    return Object.values(dictConfig).find((item) => item.value === visibleType.value);
  });

  const show = (type: keyof T) => {
    visibleType.value = dictConfig[type].value;
    visible.value = true;
  };

  const hide = () => {
    visible.value = false;
  };

  return {
    visible,
    visibleType,
    currentConfig,
    show,
    hide,
    dict: dictConfig,
  };
}
```

使用 Hook 的示例：

```vue
<script lang="ts" setup>
import { reactive } from 'vue';
import { useDictModal } from '#/hooks/useDictModal';

const dict = reactive({
  delete: {
    title: '确认删除',
    content: '确定要删除吗？',
    value: 0,
    confirmText: '删除',
    cancelText: '取消',
    type: 'danger' as const,
  },
  success: {
    title: '操作成功',
    content: '操作已完成',
    value: 1,
    confirmText: '确定',
    cancelText: '',
    type: 'success' as const,
  },
});

const { visible, currentConfig, show, hide } = useDictModal(dict);

function handleDelete() {
  show('delete');
}

async function handleConfirm() {
  // 根据当前类型执行不同操作
  hide();
}
</script>
```
