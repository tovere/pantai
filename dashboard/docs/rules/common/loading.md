# Loading 加载状态规范

## 原则
所有异步操作（请求、提交、删除等）都需要添加 loading 状态，防止用户重复操作，提升用户体验。

## Loading 状态类型

1. **按钮 Loading**：提交、删除等操作按钮
2. **表格 Loading**：数据加载时显示
3. **页面 Loading**：整页数据加载时显示

## 示例：表单提交 Loading

```vue
<script lang="ts" setup>
import { ref } from 'vue';
import { ElMessage } from 'element-plus';

const submitLoading = ref(false);

async function handleSubmit() {
  // 防止重复提交
  if (submitLoading.value) return;
  
  submitLoading.value = true;
  try {
    await someApi();
    ElMessage.success('提交成功');
  } catch (error) {
    console.error('提交失败', error);
    ElMessage.error('操作失败，请重试');
  } finally {
    submitLoading.value = false;
  }
}
</script>

<template>
  <el-button type="primary" :loading="submitLoading" @click="handleSubmit">
    {{ submitLoading ? '提交中...' : '确定' }}
  </el-button>
</template>
```

## 示例：删除操作 Loading

```vue
<script lang="ts" setup>
import { ref } from 'vue';

// 删除按钮 loading 状态（记录每行的删除状态）
const deleteLoadingMap = ref<Record<string, boolean>>({});

async function handleDelete(id: string) {
  if (deleteLoadingMap.value[id]) return;
  
  deleteLoadingMap.value[id] = true;
  try {
    await deleteApi(id);
    ElMessage.success('删除成功');
  } catch (error) {
    ElMessage.error('删除失败，请重试');
  } finally {
    deleteLoadingMap.value[id] = false;
  }
}
</script>

<template>
  <el-button 
    type="danger" 
    link 
    :loading="deleteLoadingMap[row.id]"
    @click="handleDelete(row.id)"
  >
    删除
  </el-button>
</template>
```

## 示例：批量操作 Loading

```vue
<script lang="ts" setup>
const batchDeleteLoading = ref(false);

async function handleBatchDelete() {
  if (selectedIds.value.length === 0) {
    ElMessage.warning('请选择要删除的数据');
    return;
  }
  
  if (batchDeleteLoading.value) return;
  
  batchDeleteLoading.value = true;
  try {
    await batchDeleteApi(selectedIds.value);
    ElMessage.success('批量删除成功');
    selectedIds.value = [];
  } catch (error) {
    ElMessage.error('批量删除失败，请重试');
  } finally {
    batchDeleteLoading.value = false;
  }
}
</script>
```
