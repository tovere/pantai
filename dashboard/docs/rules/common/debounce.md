# 防抖（Debounce）规范

## 原则
对于频繁触发的事件（搜索输入、窗口调整等），使用防抖减少不必要的请求，提升性能。

## 常见防抖场景

1. **搜索输入**：用户输入时延迟搜索
2. **表单验证**：输入时延迟验证
3. **窗口调整**：resize 事件处理

## 使用 VueUse 的 useDebounceFn

项目已集成 VueUse，推荐使用 `useDebounceFn`：

```typescript
import { useDebounceFn } from '@vueuse/core';

// 创建防抖函数
const debouncedSearch = useDebounceFn(() => {
  // 执行搜索
  searchTable();
}, 300); // 300ms 延迟
```

## 示例：搜索防抖

```vue
<script lang="ts" setup>
import { ref } from 'vue';
import { useDebounceFn } from '@vueuse/core';
import { useVbenVxeGrid } from '#/adapter/vxe-table';
import type { VxeTableGridOptions } from '#/adapter/vxe-table';

// 搜索关键词
const searchKeyword = ref('');

// 使用 useVbenVxeGrid 创建表格
const [Grid, gridApi] = useVbenVxeGrid({
  gridOptions: {
    columns: [
      // ...列配置
    ] as VxeTableGridOptions['columns'],
    proxyConfig: {
      ajax: {
        query: async ({ page }) => {
          const res = await getListApi({
            pageNum: page.currentPage,
            pageSize: page.pageSize,
            keyword: searchKeyword.value, // 使用搜索关键词
          });
          return { items: res.items, total: res.total };
        },
      },
    },
  },
});

// 防抖搜索（300ms 延迟）
const handleSearch = useDebounceFn(() => {
  // 触发表格重新加载
  gridApi.reload();
}, 300);

// 监听输入变化，触发防抖搜索
function onKeywordChange() {
  handleSearch();
}
</script>

<template>
  <div class="p-4">
    <!-- 搜索栏 -->
    <div class="mb-4">
      <el-input
        v-model="searchKeyword"
        placeholder="请输入关键词搜索"
        clearable
        class="w-60"
        @input="onKeywordChange"
      >
        <template #prefix>
          <el-icon><Search /></el-icon>
        </template>
      </el-input>
    </div>

    <!-- 表格 -->
    <Grid />
  </div>
</template>
```

## 示例：表单提交防抖

```vue
<script lang="ts" setup>
import { ref } from 'vue';
import { useDebounceFn } from '@vueuse/core';
import { ElMessage } from 'element-plus';

const formData = ref({});
const submitLoading = ref(false);

// 防抖提交（防止用户快速多次点击）
const handleSubmit = useDebounceFn(async () => {
  if (submitLoading.value) return;
  
  submitLoading.value = true;
  try {
    await createApi(formData.value);
    ElMessage.success('提交成功');
  } catch (error) {
    ElMessage.error('提交失败');
  } finally {
    submitLoading.value = false;
  }
}, 200); // 200ms 防抖

// 或者使用 throttle 节流（更适合提交场景）
import { useThrottleFn } from '@vueuse/core';

const handleSubmitThrottled = useThrottleFn(async () => {
  // 提交逻辑
}, 1000); // 1秒内只能触发一次
</script>
```
