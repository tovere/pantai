# 错误处理规范（try/catch/finally）

## 原则
所有 API 请求都必须使用 try/catch/finally 进行错误处理，确保：
1. 错误能被捕获并提示用户
2. Loading 状态能正确重置
3. 用户能得到明确的反馈

## 标准请求处理模式

```typescript
// 定义 loading 状态
const loading = ref(false);

async function handleRequest() {
  // 1. 检查是否正在请求中
  if (loading.value) return;
  
  // 2. 开始请求，设置 loading
  loading.value = true;
  
  try {
    // 3. 执行请求
    const result = await someApi();
    
    // 4. 处理成功结果
    ElMessage.success('操作成功');
    return result;
    
  } catch (error) {
    // 5. 处理错误
    console.error('请求失败', error);
    ElMessage.error('操作失败，请重试');
    
    // 可选：根据错误类型进行不同处理
    // if (error.response?.status === 401) {
    //   // 处理未授权
    // }
    
  } finally {
    // 6. 无论成功失败，都重置 loading
    loading.value = false;
  }
}
```

## 统一错误处理函数

```typescript
// 统一错误处理函数
function handleApiError(error: any, defaultMessage = '操作失败') {
  console.error('API Error:', error);
  
  // 根据错误类型返回不同提示
  if (error.response) {
    const { status, data } = error.response;
    
    switch (status) {
      case 400:
        ElMessage.error(data.message || '请求参数错误');
        break;
      case 401:
        ElMessage.error('登录已过期，请重新登录');
        // 跳转登录页
        break;
      case 403:
        ElMessage.error('没有权限执行此操作');
        break;
      case 404:
        ElMessage.error('请求的资源不存在');
        break;
      case 500:
        ElMessage.error('服务器错误，请稍后重试');
        break;
      default:
        ElMessage.error(data.message || defaultMessage);
    }
  } else if (error.request) {
    // 请求已发出但没有收到响应
    ElMessage.error('网络错误，请检查网络连接');
  } else {
    // 其他错误
    ElMessage.error(defaultMessage);
  }
}

// 使用示例
async function handleDelete(id: string) {
  try {
    await deleteApi(id);
    ElMessage.success('删除成功');
  } catch (error) {
    handleApiError(error, '删除失败');
  }
}
```

## 完整示例：CRUD 操作

```vue
<script lang="ts" setup>
import { ref } from 'vue';
import { ElMessage, ElMessageBox } from 'element-plus';

// 各种 loading 状态
const tableLoading = ref(false);
const submitLoading = ref(false);
const deleteLoadingMap = ref<Record<string, boolean>>({});

// 列表查询
async function loadList() {
  if (tableLoading.value) return;
  
  tableLoading.value = true;
  try {
    const res = await getListApi({ page: 1, pageSize: 20 });
    // 处理数据
    return res;
  } catch (error) {
    console.error('获取列表失败', error);
    ElMessage.error('获取数据失败，请刷新重试');
    return { items: [], total: 0 };
  } finally {
    tableLoading.value = false;
  }
}

// 提交表单
async function handleSubmit() {
  if (submitLoading.value) return;
  
  submitLoading.value = true;
  try {
    await createApi(formData.value);
    ElMessage.success('提交成功');
    // 刷新列表
    loadList();
  } catch (error) {
    console.error('提交失败', error);
    ElMessage.error('操作失败，请重试');
  } finally {
    submitLoading.value = false;
  }
}

// 删除操作
async function handleDelete(id: string) {
  if (deleteLoadingMap.value[id]) return;
  
  try {
    await ElMessageBox.confirm('确定要删除该记录吗？', '提示', { type: 'warning' });
  } catch {
    // 用户取消
    return;
  }
  
  deleteLoadingMap.value[id] = true;
  try {
    await deleteApi(id);
    ElMessage.success('删除成功');
    loadList();
  } catch (error) {
    console.error('删除失败', error);
    ElMessage.error('删除失败，请重试');
  } finally {
    deleteLoadingMap.value[id] = false;
  }
}
</script>
```

## 注意事项

1. **必须使用 finally**：确保 loading 状态一定会被重置
2. **防止重复请求**：在请求开始前检查 loading 状态
3. **明确的用户反馈**：成功和失败都要有明确的提示
4. **错误日志**：使用 console.error 记录错误信息，便于调试
5. **二次确认**：删除等危险操作需要用户确认
