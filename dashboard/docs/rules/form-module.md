---
description: 复杂表单模块开发规范
globs:
alwaysApply: false
---

# 复杂表单模块开发规范

本规范适用于复杂表单场景，包括多步骤表单、动态表单、表单联动等。

## 功能规范模板

```markdown
# 功能规范：[表单模块名称]

## 1. 功能概述
[描述表单的业务场景和复杂度]

## 2. 表单类型
- [ ] 单页表单（字段较多）
- [ ] 分步表单（多个步骤）
- [ ] 动态表单（字段可增减）
- [ ] 表单联动（字段间有依赖关系）

## 3. 表单字段
| 字段名 | 显示名称 | 组件类型 | 是否必填 | 联动关系 | 验证规则 |
|--------|----------|----------|----------|----------|----------|
| name | 名称 | VbenInput | ✅ | - | 2-50字符 |
| type | 类型 | VbenSelect | ✅ | 控制显示字段 | - |
| amount | 金额 | VbenInputNumber | ✅ | - | 大于0 |

## 4. 表单联动
- 当 type = "个人" 时，显示身份证字段
- 当 type = "企业" 时，显示统一社会信用代码字段
- 当 amount > 10000 时，需要审批

## 5. 提交逻辑
- 表单验证通过后提交
- 提交成功后跳转/关闭弹窗
- 提交失败显示错误信息
```

## 文件生成规范

### 1. 复杂表单组件

位置：`apps/web-ele/src/views/[module]/Form.vue`

```vue
<script lang="ts" setup>
import { computed, ref, watch } from 'vue';
import { VbenForm, z } from '@vben/common-ui';
import type { VbenFormSchema } from '@vben/common-ui';
import { ElMessage } from 'element-plus';

import { create[Module]Api, update[Module]Api } from '#/api/[module]';

const props = defineProps<{
  isEdit?: boolean;
  initialData?: Record<string, any>;
}>();

const emit = defineEmits<{
  success: [];
  cancel: [];
}>();

// 表单数据
const formData = ref<Record<string, any>>({
  type: 'personal',
  ...props.initialData,
});

// 类型选项
const typeOptions = [
  { label: '个人', value: 'personal' },
  { label: '企业', value: 'enterprise' },
];

// 表单 Schema（带联动）
const formSchema = computed((): VbenFormSchema[] => {
  const schemas: VbenFormSchema[] = [
    // 基本信息
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
      component: 'VbenSelect',
      fieldName: 'type',
      label: '类型',
      rules: z.string().min(1, '请选择类型'),
      componentProps: {
        options: typeOptions,
        placeholder: '请选择类型',
      },
    },
  ];

  // 根据类型动态添加字段
  if (formData.value.type === 'personal') {
    schemas.push({
      component: 'VbenInput',
      fieldName: 'idCard',
      label: '身份证号',
      rules: z.string().regex(/^\d{17}[\dXx]$/, '请输入正确的身份证号'),
      componentProps: {
        placeholder: '请输入身份证号',
      },
    });
  } else if (formData.value.type === 'enterprise') {
    schemas.push({
      component: 'VbenInput',
      fieldName: 'creditCode',
      label: '统一社会信用代码',
      rules: z.string().regex(/^[0-9A-Z]{18}$/, '请输入正确的信用代码'),
      componentProps: {
        placeholder: '请输入统一社会信用代码',
      },
    });
    schemas.push({
      component: 'VbenInput',
      fieldName: 'legalPerson',
      label: '法人代表',
      rules: z.string().min(2, '请输入法人代表'),
      componentProps: {
        placeholder: '请输入法人代表',
      },
    });
  }

  // 通用字段
  schemas.push(
    {
      component: 'VbenInputNumber',
      fieldName: 'amount',
      label: '金额',
      rules: z.number().positive('金额必须大于0'),
      componentProps: {
        placeholder: '请输入金额',
        min: 0,
        precision: 2,
      },
    },
    {
      component: 'VbenTextarea',
      fieldName: 'remark',
      label: '备注',
      componentProps: {
        placeholder: '请输入备注',
        maxlength: 500,
        showWordLimit: true,
      },
    },
  );

  return schemas;
});

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
    emit('success');
  } catch (error) {
    console.error('提交失败', error);
  }
}

// 取消
function handleCancel() {
  emit('cancel');
}
</script>

<template>
  <div class="p-4">
    <VbenForm :schema="formSchema" :values="formData" />
    
    <div class="mt-4 flex justify-end gap-2">
      <el-button @click="handleCancel">取消</el-button>
      <el-button type="primary" @click="handleSubmit">提交</el-button>
    </div>
  </div>
</template>
```

### 2. 分步表单组件

位置：`apps/web-ele/src/views/[module]/StepForm.vue`

```vue
<script lang="ts" setup>
import { ref, computed } from 'vue';
import { VbenForm, z } from '@vben/common-ui';
import type { VbenFormSchema } from '@vben/common-ui';
import { ElMessage } from 'element-plus';

import { create[Module]Api } from '#/api/[module]';

const emit = defineEmits<{
  success: [];
  cancel: [];
}>();

// 当前步骤
const currentStep = ref(0);

// 表单数据
const formData = ref<Record<string, any>>({});

// 步骤配置
const steps = [
  { title: '基本信息', key: 'basic' },
  { title: '详细信息', key: 'detail' },
  { title: '确认提交', key: 'confirm' },
];

// 步骤1：基本信息
const basicSchema = computed((): VbenFormSchema[] => [
  {
    component: 'VbenInput',
    fieldName: 'name',
    label: '名称',
    rules: z.string().min(2, '名称至少2个字符'),
  },
  {
    component: 'VbenSelect',
    fieldName: 'type',
    label: '类型',
    rules: z.string().min(1, '请选择类型'),
    componentProps: {
      options: [
        { label: '类型A', value: 'a' },
        { label: '类型B', value: 'b' },
      ],
    },
  },
  {
    component: 'VbenInput',
    fieldName: 'contact',
    label: '联系人',
    rules: z.string().min(1, '请输入联系人'),
  },
  {
    component: 'VbenInput',
    fieldName: 'phone',
    label: '联系电话',
    rules: z.string().regex(/^1[3-9]\d{9}$/, '请输入正确的手机号'),
  },
]);

// 步骤2：详细信息
const detailSchema = computed((): VbenFormSchema[] => [
  {
    component: 'VbenInput',
    fieldName: 'address',
    label: '地址',
    rules: z.string().min(1, '请输入地址'),
  },
  {
    component: 'VbenInputNumber',
    fieldName: 'amount',
    label: '金额',
    rules: z.number().positive('金额必须大于0'),
  },
  {
    component: 'VbenTextarea',
    fieldName: 'description',
    label: '描述',
  },
]);

// 当前步骤的 Schema
const currentSchema = computed(() => {
  switch (currentStep.value) {
    case 0:
      return basicSchema.value;
    case 1:
      return detailSchema.value;
    default:
      return [];
  }
});

// 下一步
function handleNext() {
  if (currentStep.value < steps.length - 1) {
    currentStep.value++;
  }
}

// 上一步
function handlePrev() {
  if (currentStep.value > 0) {
    currentStep.value--;
  }
}

// 提交
async function handleSubmit() {
  try {
    await create[Module]Api(formData.value);
    ElMessage.success('提交成功');
    emit('success');
  } catch (error) {
    console.error('提交失败', error);
  }
}

// 取消
function handleCancel() {
  emit('cancel');
}
</script>

<template>
  <div class="p-4">
    <!-- 步骤条 -->
    <el-steps :active="currentStep" align-center class="mb-8">
      <el-step v-for="step in steps" :key="step.key" :title="step.title" />
    </el-steps>

    <!-- 表单内容 -->
    <div class="mb-8">
      <!-- 步骤1和2：表单 -->
      <template v-if="currentStep < 2">
        <VbenForm :schema="currentSchema" :values="formData" />
      </template>

      <!-- 步骤3：确认信息 -->
      <template v-else>
        <el-descriptions :column="2" border>
          <el-descriptions-item label="名称">{{ formData.name }}</el-descriptions-item>
          <el-descriptions-item label="类型">{{ formData.type }}</el-descriptions-item>
          <el-descriptions-item label="联系人">{{ formData.contact }}</el-descriptions-item>
          <el-descriptions-item label="联系电话">{{ formData.phone }}</el-descriptions-item>
          <el-descriptions-item label="地址">{{ formData.address }}</el-descriptions-item>
          <el-descriptions-item label="金额">{{ formData.amount }}</el-descriptions-item>
          <el-descriptions-item label="描述" :span="2">{{ formData.description }}</el-descriptions-item>
        </el-descriptions>
      </template>
    </div>

    <!-- 操作按钮 -->
    <div class="flex justify-between">
      <el-button v-if="currentStep > 0" @click="handlePrev">上一步</el-button>
      <div v-else />

      <div class="flex gap-2">
        <el-button @click="handleCancel">取消</el-button>
        <el-button 
          v-if="currentStep < steps.length - 1" 
          type="primary" 
          @click="handleNext"
        >
          下一步
        </el-button>
        <el-button v-else type="primary" @click="handleSubmit">
          提交
        </el-button>
      </div>
    </div>
  </div>
</template>
```

### 3. 动态表单（字段可增减）

位置：`apps/web-ele/src/views/[module]/DynamicForm.vue`

```vue
<script lang="ts" setup>
import { ref } from 'vue';
import { VbenForm, z } from '@vben/common-ui';
import type { VbenFormSchema } from '@vben/common-ui';
import { ElMessage } from 'element-plus';
import { Plus, Delete } from '@element-plus/icons-vue';

interface DynamicItem {
  id: string;
  name: string;
  value: string;
}

const emit = defineEmits<{
  success: [];
}>();

// 动态列表
const dynamicItems = ref<DynamicItem[]>([
  { id: '1', name: '', value: '' },
]);

// 基础表单数据
const baseFormData = ref({
  title: '',
  description: '',
});

// 基础表单 Schema
const baseFormSchema: VbenFormSchema[] = [
  {
    component: 'VbenInput',
    fieldName: 'title',
    label: '标题',
    rules: z.string().min(1, '请输入标题'),
  },
  {
    component: 'VbenTextarea',
    fieldName: 'description',
    label: '描述',
  },
];

// 添加项
function addItem() {
  dynamicItems.value.push({
    id: Date.now().toString(),
    name: '',
    value: '',
  });
}

// 删除项
function removeItem(index: number) {
  if (dynamicItems.value.length > 1) {
    dynamicItems.value.splice(index, 1);
  } else {
    ElMessage.warning('至少保留一项');
  }
}

// 提交
async function handleSubmit() {
  // 验证动态项
  const valid = dynamicItems.value.every((item) => item.name && item.value);
  if (!valid) {
    ElMessage.warning('请完整填写所有项');
    return;
  }

  const submitData = {
    ...baseFormData.value,
    items: dynamicItems.value,
  };

  console.log('提交数据', submitData);
  ElMessage.success('提交成功');
  emit('success');
}
</script>

<template>
  <div class="p-4">
    <!-- 基础表单 -->
    <VbenForm :schema="baseFormSchema" :values="baseFormData" />

    <!-- 动态列表 -->
    <div class="mt-6">
      <div class="flex justify-between items-center mb-4">
        <span class="font-medium">动态项列表</span>
        <el-button type="primary" :icon="Plus" @click="addItem">
          添加项
        </el-button>
      </div>

      <div v-for="(item, index) in dynamicItems" :key="item.id" class="flex gap-4 mb-4">
        <el-input v-model="item.name" placeholder="名称" class="flex-1" />
        <el-input v-model="item.value" placeholder="值" class="flex-1" />
        <el-button 
          type="danger" 
          :icon="Delete" 
          circle 
          @click="removeItem(index)"
        />
      </div>
    </div>

    <!-- 提交按钮 -->
    <div class="mt-6 flex justify-end">
      <el-button type="primary" @click="handleSubmit">提交</el-button>
    </div>
  </div>
</template>
```

### 4. 表单联动示例

```vue
<script lang="ts" setup>
import { computed, ref, watch } from 'vue';
import { VbenForm, z } from '@vben/common-ui';
import type { VbenFormSchema } from '@vben/common-ui';

const formData = ref({
  orderType: 'normal',
  deliveryType: 'express',
  paymentType: 'online',
});

// 是否显示物流信息
const showExpressInfo = computed(() => formData.value.deliveryType === 'express');

// 是否显示自提信息
const showPickupInfo = computed(() => formData.value.deliveryType === 'pickup');

// 是否需要审批
const needApproval = computed(() => formData.value.orderType === 'bulk');

const formSchema = computed((): VbenFormSchema[] => {
  const schemas: VbenFormSchema[] = [
    {
      component: 'VbenSelect',
      fieldName: 'orderType',
      label: '订单类型',
      componentProps: {
        options: [
          { label: '普通订单', value: 'normal' },
          { label: '批量订单', value: 'bulk' },
          { label: '预售订单', value: 'presale' },
        ],
      },
    },
    {
      component: 'VbenSelect',
      fieldName: 'deliveryType',
      label: '配送方式',
      componentProps: {
        options: [
          { label: '快递配送', value: 'express' },
          { label: '到店自提', value: 'pickup' },
          { label: '无需配送', value: 'none' },
        ],
      },
    },
  ];

  // 快递配送时显示地址信息
  if (showExpressInfo.value) {
    schemas.push(
      {
        component: 'VbenInput',
        fieldName: 'consignee',
        label: '收货人',
        rules: z.string().min(1, '请输入收货人'),
      },
      {
        component: 'VbenInput',
        fieldName: 'address',
        label: '收货地址',
        rules: z.string().min(1, '请输入收货地址'),
      },
    );
  }

  // 到店自提时显示自提点
  if (showPickupInfo.value) {
    schemas.push({
      component: 'VbenSelect',
      fieldName: 'pickupPoint',
      label: '自提点',
      rules: z.string().min(1, '请选择自提点'),
      componentProps: {
        options: [
          { label: '门店A', value: 'a' },
          { label: '门店B', value: 'b' },
        ],
      },
    });
  }

  // 批量订单需要审批
  if (needApproval.value) {
    schemas.push({
      component: 'VbenTextarea',
      fieldName: 'approvalNote',
      label: '审批说明',
      rules: z.string().min(10, '审批说明至少10个字符'),
    });
  }

  return schemas;
});
</script>

<template>
  <VbenForm :schema="formSchema" :values="formData" />
</template>
```

## 常用验证规则

```typescript
// 手机号
z.string().regex(/^1[3-9]\d{9}$/, '请输入正确的手机号')

// 邮箱
z.string().email('请输入正确的邮箱')

// 身份证
z.string().regex(/^\d{17}[\dXx]$/, '请输入正确的身份证号')

// 统一社会信用代码
z.string().regex(/^[0-9A-Z]{18}$/, '请输入正确的信用代码')

// 银行卡号
z.string().regex(/^\d{16,19}$/, '请输入正确的银行卡号')

// 密码（8-20位，包含字母和数字）
z.string().regex(/^(?=.*[A-Za-z])(?=.*\d)[A-Za-z\d]{8,20}$/, '密码需8-20位，包含字母和数字')

// 金额（正数，最多2位小数）
z.number().positive('金额必须大于0')

// URL
z.string().url('请输入正确的URL')

// 中文姓名
z.string().regex(/^[\u4e00-\u9fa5]{2,20}$/, '请输入正确的中文姓名')
```

## 注意事项

1. **表单联动**：使用 computed 动态生成 schema，实现字段显示/隐藏
2. **分步表单**：数据需要持久化，切换步骤时保留已填写的数据
3. **动态表单**：注意删除项时的数据校验
4. **验证时机**：合理设置验证触发时机（blur/change）
5. **提交防抖**：防止重复提交

## 相关通用规范

- [Loading 状态规范](./common/loading.md)
- [防抖规范](./common/debounce.md)
- [错误处理规范](./common/error-handling.md)
- [数据回显规范](./common/data-echo.md)
