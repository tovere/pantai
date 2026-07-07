# 数据回显规范

## 原则
在编辑页、详情页数据回显时，统一使用工具函数，避免手动赋值导致的字段遗漏或多余字段注入。

## 工具函数

- **函数名**：`assignParentValuesToChild`
- **位置**：`apps/web-ele/src/utils/index.ts`

## 使用要求

1. 表单初始化先定义完整默认字段
2. 回显时调用 `assignParentValuesToChild(parent, child, mapping?)`
3. 前后端字段不一致时，通过 `mapping` 映射

## 函数说明

- 只会赋值 `child` 中已存在的字段
- 不会向 `child` 注入多余字段
- 不存在映射键时保持原值

## 基础示例

```typescript
import { assignParentValuesToChild } from '#/utils';

// 1. 定义表单初始数据（包含所有字段）
const formData = ref({
  id: '',
  name: '',
  code: '',
  status: 1,
  remark: '',
});

// 2. 获取后端数据
const apiData = await getUserDetailApi(id);

// 3. 使用工具函数回显
assignParentValuesToChild(apiData, formData.value);

// formData.value 现在包含了 apiData 中对应的值
// 但不会有 apiData 中多余的字段
```

## 字段映射示例

当前后端字段名不一致时：

```typescript
const formData = ref({
  userName: '',
  userPhone: '',
  userEmail: '',
});

const apiData = {
  name: '张三',
  phone: '13800138000',
  email: 'test@example.com',
  extraField: 'ignored', // 这个字段不会被赋值
};

// 使用映射
assignParentValuesToChild(apiData, formData.value, {
  name: 'userName',
  phone: 'userPhone',
  email: 'userEmail',
});

// 结果：
// formData.value = {
//   userName: '张三',
//   userPhone: '13800138000',
//   userEmail: 'test@example.com',
// }
```

## 完整示例：编辑表单

```vue
<script lang="ts" setup>
import { ref } from 'vue';
import { assignParentValuesToChild } from '#/utils';
import { getUserDetailApi, updateUserApi } from '#/api/user';

const props = defineProps<{
  userId?: string;
}>();

// 1. 定义完整的表单结构
const formData = ref({
  id: '',
  username: '',
  realName: '',
  mobile: '',
  email: '',
  status: 1,
  remark: '',
});

// 2. 加载数据并回显
async function loadUserData() {
  if (!props.userId) return;
  
  try {
    const data = await getUserDetailApi(props.userId);
    
    // 使用工具函数回显
    assignParentValuesToChild(data, formData.value);
    
    // 如果需要映射，可以这样：
    // assignParentValuesToChild(data, formData.value, {
    //   name: 'username',
    //   phone: 'mobile',
    // });
  } catch (error) {
    console.error('加载用户数据失败', error);
  }
}

// 3. 提交时使用 formData
async function handleSubmit() {
  await updateUserApi(formData.value.id, formData.value);
}

onMounted(() => {
  loadUserData();
});
</script>
```

## 注意事项

1. **先定义结构**：必须先定义 `formData` 的完整结构，包含所有需要的字段
2. **类型安全**：建议使用 TypeScript 接口定义表单数据类型
3. **默认值**：为字段设置合理的默认值，避免 undefined
4. **映射关系**：映射对象的 key 是源字段名，value 是目标字段名
5. **嵌套对象**：工具函数只处理第一层字段，嵌套对象需要单独处理

## 错误示例

❌ **不要这样做**：

```typescript
// 错误：直接赋值整个对象
formData.value = apiData; // 会丢失响应式，且可能有多余字段

// 错误：手动逐个赋值
formData.value.name = apiData.name;
formData.value.code = apiData.code;
// ... 容易遗漏字段
```

✅ **正确做法**：

```typescript
// 使用工具函数
assignParentValuesToChild(apiData, formData.value);
```
