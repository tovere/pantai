
---
description: 商城/购物模块开发规范
globs:
alwaysApply: false
---

# 商城/购物模块开发规范

本规范适用于电商、购物相关的业务模块开发，包括商品、订单、购物车、支付等。

## 商品模块

### 功能规范模板

```markdown
# 功能规范：商品管理

## 1. 功能概述
管理商品的增删改查、上下架、库存管理等。

## 2. 页面布局
- 列表页：商品表格 + 搜索筛选 + 分类树
- 详情页：商品基本信息 + SKU 配置 + 图片管理
- 表单弹窗：新增/编辑商品

## 3. 数据结构

### 商品信息
| 字段名 | 类型 | 说明 |
|--------|------|------|
| id | string | 商品ID |
| name | string | 商品名称 |
| categoryId | string | 分类ID |
| brandId | string | 品牌ID |
| price | number | 销售价（分） |
| originalPrice | number | 原价（分） |
| stock | number | 库存数量 |
| sales | number | 销量 |
| status | number | 状态：1上架 0下架 |
| mainImage | string | 主图URL |
| images | string[] | 轮播图URLs |
| description | string | 商品描述 |
| skus | SkuItem[] | SKU列表 |

### SKU 信息
| 字段名 | 类型 | 说明 |
|--------|------|------|
| id | string | SKU ID |
| specValues | string | 规格值（如：红色-XL） |
| price | number | 价格（分） |
| stock | number | 库存 |
| image | string | SKU图片 |
```

### API 接口文件

位置：`apps/web-ele/src/api/product.ts`

```typescript
import { requestClient } from '#/api/request';

// 商品类型
export interface ProductItem {
  id: string;
  name: string;
  categoryId: string;
  categoryName?: string;
  brandId?: string;
  brandName?: string;
  price: number;
  originalPrice: number;
  stock: number;
  sales: number;
  status: number;
  mainImage: string;
  images: string[];
  description: string;
  skus: ProductSku[];
  createTime: string;
}

export interface ProductSku {
  id: string;
  productId: string;
  specValues: string;
  price: number;
  stock: number;
  image?: string;
}

export interface ProductListParams {
  page: number;
  pageSize: number;
  name?: string;
  categoryId?: string;
  status?: number;
}

export interface ProductFormData {
  id?: string;
  name: string;
  categoryId: string;
  brandId?: string;
  price: number;
  originalPrice: number;
  stock: number;
  status: number;
  mainImage: string;
  images: string[];
  description: string;
  skus: ProductSku[];
}

// 获取商品列表
export async function getProductListApi(params: ProductListParams) {
  return requestClient.get<{ items: ProductItem[]; total: number }>('/product/list', {
    params,
  });
}

// 获取商品详情
export async function getProductDetailApi(id: string) {
  return requestClient.get<ProductItem>(`/product/${id}`);
}

// 创建商品
export async function createProductApi(data: ProductFormData) {
  return requestClient.post<ProductItem>('/product', data);
}

// 更新商品
export async function updateProductApi(id: string, data: ProductFormData) {
  return requestClient.put<ProductItem>(`/product/${id}`, data);
}

// 删除商品
export async function deleteProductApi(id: string) {
  return requestClient.delete(`/product/${id}`);
}

// 上架商品
export async function publishProductApi(id: string) {
  return requestClient.put(`/product/${id}/publish`);
}

// 下架商品
export async function unpublishProductApi(id: string) {
  return requestClient.put(`/product/${id}/unpublish`);
}

// 批量上架
export async function batchPublishProductApi(ids: string[]) {
  return requestClient.put('/product/batch/publish', { ids });
}

// 批量下架
export async function batchUnpublishProductApi(ids: string[]) {
  return requestClient.put('/product/batch/unpublish', { ids });
}
```

### 商品列表页面

位置：`apps/web-ele/src/views/shop/product/index.vue`

```vue
<script lang="ts" setup>
import { ref } from 'vue';
import { useVbenVxeGrid } from '#/adapter/vxe-table';
import type { VxeTableGridOptions } from '#/adapter/vxe-table';
import { ElMessage, ElMessageBox } from 'element-plus';

import {
  getProductListApi,
  deleteProductApi,
  publishProductApi,
  unpublishProductApi,
} from '#/api/product';
import ProductForm from './ProductForm.vue';

const formVisible = ref(false);
const formData = ref<Record<string, any>>({});
const isEdit = ref(false);

// 使用 useVbenVxeGrid 创建表格
const [Grid, gridApi] = useVbenVxeGrid({
  gridOptions: {
    columns: [
      { type: 'checkbox', width: 50 },
      { field: 'mainImage', title: '主图', minWidth: 80, slots: { default: 'image' } },
      { field: 'name', title: '商品名称', minWidth: 200 },
      { field: 'categoryName', title: '分类', minWidth: 100 },
      { field: 'price', title: '价格', minWidth: 100, slots: { default: 'price' } },
      { field: 'stock', title: '库存', minWidth: 80 },
      { field: 'sales', title: '销量', minWidth: 80 },
      { field: 'status', title: '状态', minWidth: 80, slots: { default: 'status' } },
      { field: 'createTime', title: '创建时间', minWidth: 160 },
      { field: 'actions', title: '操作', minWidth: 200, fixed: 'right', slots: { default: 'actions' } },
    ] as VxeTableGridOptions['columns'],
    proxyConfig: {
      ajax: {
        query: async ({ page }) => {
          try {
            const res = await getProductListApi({
              page: page.currentPage,
              pageSize: page.pageSize,
            });
            return { items: res.items, total: res.total };
          } catch (error) {
            ElMessage.error('获取商品列表失败');
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
  formData.value = { status: 0, images: [], skus: [] };
  formVisible.value = true;
}

// 编辑
function handleEdit(row: any) {
  isEdit.value = true;
  formData.value = { ...row };
  formVisible.value = true;
}

// 上架
async function handlePublish(row: any) {
  try {
    await publishProductApi(row.id);
    ElMessage.success('上架成功');
    gridApi.reload();
  } catch (error) {
    ElMessage.error('上架失败');
  }
}

// 下架
async function handleUnpublish(row: any) {
  await ElMessageBox.confirm('确定要下架该商品吗？', '提示', { type: 'warning' });
  
  try {
    await unpublishProductApi(row.id);
    ElMessage.success('下架成功');
    gridApi.reload();
  } catch (error) {
    ElMessage.error('下架失败');
  }
}

// 删除
async function handleDelete(id: string) {
  await ElMessageBox.confirm('确定要删除该商品吗？', '提示', { type: 'warning' });
  
  try {
    await deleteProductApi(id);
    ElMessage.success('删除成功');
    gridApi.reload();
  } catch (error) {
    ElMessage.error('删除失败');
  }
}

// 格式化价格（分转元）
function formatPrice(price: number) {
  return (price / 100).toFixed(2);
}
</script>

<template>
  <div class="p-4">
    <div class="mb-4 flex gap-2">
      <el-button type="primary" @click="handleAdd">新增商品</el-button>
    </div>

    <Grid>
      <template #image="{ row }">
        <el-image 
          :src="row.mainImage" 
          class="h-12 w-12 rounded"
          fit="cover"
        />
      </template>
      
      <template #price="{ row }">
        <span class="text-red-500">¥{{ formatPrice(row.price) }}</span>
        <span v-if="row.originalPrice > row.price" class="ml-1 text-gray-400 text-sm line-through">
          ¥{{ formatPrice(row.originalPrice) }}
        </span>
      </template>
      
      <template #status="{ row }">
        <el-tag :type="row.status === 1 ? 'success' : 'info'">
          {{ row.status === 1 ? '已上架' : '已下架' }}
        </el-tag>
      </template>
      
      <template #actions="{ row }">
        <el-button type="primary" link @click="handleEdit(row)">编辑</el-button>
        <el-button 
          v-if="row.status === 0" 
          type="success" 
          link 
          @click="handlePublish(row)"
        >
          上架
        </el-button>
        <el-button 
          v-else 
          type="warning" 
          link 
          @click="handleUnpublish(row)"
        >
          下架
        </el-button>
        <el-button type="danger" link @click="handleDelete(row.id)">删除</el-button>
      </template>
    </Grid>

    <ProductForm 
      v-model:visible="formVisible" 
      v-model:data="formData" 
      :is-edit="isEdit"
      @success="gridApi.reload()"
    />
  </div>
</template>
```

---

## 订单模块

### 数据结构

```typescript
// 订单类型
export interface OrderItem {
  id: string;
  orderNo: string;
  userId: string;
  userName?: string;
  userPhone: string;
  totalPrice: number;       // 订单总价（分）
  payPrice: number;         // 实付金额（分）
  freightPrice: number;     // 运费（分）
  discountPrice: number;    // 优惠金额（分）
  status: number;           // 订单状态
  paymentStatus: number;    // 支付状态
  paymentType: number;      // 支付方式
  paymentTime?: string;     // 支付时间
  consigneeName: string;    // 收货人
  consigneePhone: string;   // 收货电话
  consigneeAddress: string; // 收货地址
  remark?: string;          // 备注
  items: OrderProduct[];    // 订单商品
  createTime: string;
}

export interface OrderProduct {
  id: string;
  productId: string;
  productName: string;
  productImage: string;
  skuId: string;
  specValues: string;
  price: number;
  quantity: number;
}

// 订单状态枚举
export const ORDER_STATUS = {
  PENDING: { value: 0, label: '待付款', color: 'warning' },
  PAID: { value: 1, label: '待发货', color: 'primary' },
  SHIPPED: { value: 2, label: '待收货', color: 'info' },
  COMPLETED: { value: 3, label: '已完成', color: 'success' },
  CANCELLED: { value: 4, label: '已取消', color: 'danger' },
  REFUNDING: { value: 5, label: '退款中', color: 'warning' },
  REFUNDED: { value: 6, label: '已退款', color: 'info' },
} as const;

// 支付方式枚举
export const PAYMENT_TYPE = {
  WECHAT: { value: 1, label: '微信支付' },
  ALIPAY: { value: 2, label: '支付宝' },
  BALANCE: { value: 3, label: '余额支付' },
} as const;
```

### API 接口

位置：`apps/web-ele/src/api/order.ts`

```typescript
import { requestClient } from '#/api/request';

export interface OrderListParams {
  page: number;
  pageSize: number;
  orderNo?: string;
  userId?: string;
  status?: number;
  startTime?: string;
  endTime?: string;
}

// 获取订单列表
export async function getOrderListApi(params: OrderListParams) {
  return requestClient.get<{ items: OrderItem[]; total: number }>('/order/list', {
    params,
  });
}

// 获取订单详情
export async function getOrderDetailApi(id: string) {
  return requestClient.get<OrderItem>(`/order/${id}`);
}

// 发货
export async function shipOrderApi(id: string, data: { expressCompany: string; expressNo: string }) {
  return requestClient.put(`/order/${id}/ship`, data);
}

// 取消订单
export async function cancelOrderApi(id: string, reason: string) {
  return requestClient.put(`/order/${id}/cancel`, { reason });
}

// 备注
export async function remarkOrderApi(id: string, remark: string) {
  return requestClient.put(`/order/${id}/remark`, { remark });
}
```

---

## 购物车模块

### 数据结构

```typescript
export interface CartItem {
  id: string;
  userId: string;
  productId: string;
  productName: string;
  productImage: string;
  skuId: string;
  specValues: string;
  price: number;
  quantity: number;
  selected: boolean;
  stock: number;
}
```

### API 接口

位置：`apps/web-ele/src/api/cart.ts`

```typescript
import { requestClient } from '#/api/request';

// 获取购物车列表
export async function getCartListApi() {
  return requestClient.get<CartItem[]>('/cart/list');
}

// 添加到购物车
export async function addToCartApi(data: { productId: string; skuId: string; quantity: number }) {
  return requestClient.post('/cart', data);
}

// 更新数量
export async function updateCartQuantityApi(id: string, quantity: number) {
  return requestClient.put(`/cart/${id}`, { quantity });
}

// 删除购物车项
export async function removeCartItemApi(id: string) {
  return requestClient.delete(`/cart/${id}`);
}

// 批量删除
export async function batchRemoveCartApi(ids: string[]) {
  return requestClient.delete('/cart/batch', { data: { ids } });
}

// 选择/取消选择
export async function selectCartItemApi(id: string, selected: boolean) {
  return requestClient.put(`/cart/${id}/select`, { selected });
}

// 全选/取消全选
export async function selectAllCartApi(selected: boolean) {
  return requestClient.put('/cart/select-all', { selected });
}
```

---

## 支付模块

### 数据结构

```typescript
export interface PaymentInfo {
  orderNo: string;
  payPrice: number;
  paymentType: number;
  qrCodeUrl?: string;    // 二维码支付链接
  wechatPayUrl?: string; // 微信支付跳转链接
  alipayUrl?: string;    // 支付宝跳转链接
}

export interface PaymentResult {
  success: boolean;
  orderNo: string;
  paymentNo: string;
  paymentTime: string;
}
```

### API 接口

位置：`apps/web-ele/src/api/payment.ts`

```typescript
import { requestClient } from '#/api/request';

// 创建支付
export async function createPaymentApi(data: { orderNo: string; paymentType: number }) {
  return requestClient.post<PaymentInfo>('/payment/create', data);
}

// 查询支付状态
export async function queryPaymentStatusApi(orderNo: string) {
  return requestClient.get<PaymentResult>(`/payment/status/${orderNo}`);
}

// 支付回调（通常由后端处理，前端只做跳转）
export async function paymentCallbackApi(params: Record<string, any>) {
  return requestClient.get('/payment/callback', { params });
}
```

---

## Mock 数据文件

位置：`apps/web-ele/src/mock/shop.ts`（或按子模块拆分为 `product.ts` / `order.ts` / `cart.ts`）

```typescript
// Mock 接口写法统一遵循：./common/mock-module.md
// Shop 场景补充：
// 1) 按产品/订单/购物车/支付拆分 endpoint
// 2) 列表接口支持分页、筛选、关键字搜索
// 3) 价格字段统一使用“分”
// 4) 订单状态流转接口（发货/取消）需模拟状态校验
```

详细实现参考：`./common/mock-module.md`

## 注意事项

1. **价格单位**：统一使用"分"为单位，避免浮点数精度问题，显示时除以100
2. **订单状态流转**：严格按照业务流程处理状态变更
3. **库存扣减**：下单时预扣库存，支付成功后正式扣减，取消订单后回滚
4. **支付安全**：支付相关接口必须使用HTTPS，敏感信息不要暴露给前端
5. **图片处理**：商品图片建议使用CDN，支持懒加载和占位图
6. **SKU组合**：前端需要处理SKU规格组合逻辑，确保库存准确

## 相关通用规范

- [枚举开发规范](./common/enum.md)
- [Loading 状态规范](./common/loading.md)
- [错误处理规范](./common/error-handling.md)
- [Mock 模块规范](./common/mock-module.md)
