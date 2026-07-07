# Mock 模块通用规范（web-ele + MockJS）

## 适用范围

- `apps/web-ele/src/mock/*.ts` 业务 Mock 文件
- 统一采用 `mockjs` + `./_utils` 工具函数
- 不再使用 `apps/backend-mock/api/*.get.ts` 的 `h3` 示例风格

## 统一要求

1. 所有接口先做鉴权：`checkAuth(options)`
2. 成功响应统一：`responseSuccess(data)` / `pageResponseSuccess(items, total)`
3. 失败响应统一：`responseError(message)`
4. 列表接口必须支持分页与筛选
5. 路径参数使用 `extractPathParams(url, pattern)`
6. 查询参数使用 `getQueryParams(url)`

## 标准模板

```typescript
import Mock from 'mockjs';

import {
  checkAuth,
  extractPathParams,
  getQueryParams,
  pageResponseSuccess,
  pagination,
  responseError,
  responseSuccess,
} from './_utils';

interface Item {
  id: string;
  name: string;
  status: number;
  createTime: string;
}

const mockList: Item[] = Array.from({ length: 80 }).map((_, i) => ({
  id: `item-${i + 1}`,
  name: Mock.Random.ctitle(3, 8),
  status: i % 2,
  createTime: new Date().toISOString(),
}));

// 列表
Mock.mock(/\/api\/[module]\/list$/, 'get', (options: any) => {
  const auth = checkAuth(options);
  if (!auth.authorized) return auth.error;

  const params = getQueryParams(options.url);
  const page = Number(params.page || 1);
  const pageSize = Number(params.pageSize || 20);
  const keyword = String(params.keyword || '');

  let list = [...mockList];
  if (keyword) {
    list = list.filter((item) => item.name.includes(keyword));
  }

  return pageResponseSuccess(pagination(page, pageSize, list), list.length);
});

// 详情
Mock.mock(/\/api\/[module]\/[^/]+$/, 'get', (options: any) => {
  const auth = checkAuth(options);
  if (!auth.authorized) return auth.error;

  const { id } = extractPathParams(options.url, '/api/[module]/:id');
  const item = mockList.find((x) => x.id === id);
  if (!item) return responseError('数据不存在');
  return responseSuccess(item);
});

// 新增
Mock.mock(/\/api\/[module]$/, 'post', (options: any) => {
  const auth = checkAuth(options);
  if (!auth.authorized) return auth.error;

  const body = JSON.parse(options.body || '{}');
  const item: Item = {
    id: `item-${Date.now()}`,
    name: body.name || Mock.Random.ctitle(3, 8),
    status: Number(body.status ?? 1),
    createTime: new Date().toISOString(),
  };
  mockList.unshift(item);
  return responseSuccess(item);
});

// 编辑
Mock.mock(/\/api\/[module]\/[^/]+$/, 'put', (options: any) => {
  const auth = checkAuth(options);
  if (!auth.authorized) return auth.error;

  const { id } = extractPathParams(options.url, '/api/[module]/:id');
  const body = JSON.parse(options.body || '{}');
  const index = mockList.findIndex((x) => x.id === id);
  if (index < 0) return responseError('数据不存在');

  mockList[index] = { ...mockList[index], ...body };
  return responseSuccess(mockList[index]);
});

// 删除
Mock.mock(/\/api\/[module]\/[^/]+$/, 'delete', (options: any) => {
  const auth = checkAuth(options);
  if (!auth.authorized) return auth.error;

  const { id } = extractPathParams(options.url, '/api/[module]/:id');
  const index = mockList.findIndex((x) => x.id === id);
  if (index < 0) return responseError('数据不存在');

  mockList.splice(index, 1);
  return responseSuccess(null);
});
```

## 各业务模块补充方式

- CRUD：直接复用模板，按字段改造
- Tree：保留树结构字段（`parentId`/`children`），列表可返回树或平铺
- Shop：按产品/订单/购物车拆分多个 endpoint，价格字段统一“分”
- Dashboard：统计类接口可直接 `responseSuccess({ ...stats })`
