# web-ele MockJS 规则参考

## 1. 目录与入口

- Mock 目录：`apps/web-ele/src/mock/`
- 模块目录：`apps/web-ele/src/mock/modules/`
- 工具文件：`apps/web-ele/src/mock/_utils.ts`
- 入口文件：`apps/web-ele/src/mock/index.ts`
- 新增模块时，在模块目录创建文件并在入口调用 setup 函数

入口标准：

```ts
import Mock from 'mockjs';

Mock.setup({
  timeout: '200-600',
});

import { setupAuthMock } from './modules/auth';
import { setupSystemMock } from './modules/system';
import { setupBusinessMock } from './modules/business';

setupAuthMock();
setupSystemMock();
setupBusinessMock();
```

## 2. 统一工具函数（`_utils.ts`）

统一使用以下函数，禁止平行封装：

- `responseSuccess(data)`
- `pageResponseSuccess(items, total)`
- `responseError(message, error?)`
- `checkAuth(options)` - 返回 `{ authorized: boolean, userInfo: UserInfo | null }`
- `pagination(page, pageSize, array)`
- `getQueryParams(url)`
- `parseBody<T>(options)` - 解析请求体

### 响应结构

成功：

```json
{
  "code": 0,
  "data": {},
  "error": null,
  "message": "ok"
}
```

错误：

```json
{
  "code": -1,
  "data": null,
  "error": "optional_error",
  "message": "错误信息"
}
```

分页：

```json
{
  "code": 0,
  "data": {
    "items": [],
    "total": 0
  },
  "error": null,
  "message": "ok"
}
```

## 3. 鉴权规范

受保护接口统一加：

```ts
if (!checkAuth(options).authorized) {
  return responseError('Unauthorized Exception');
}
```

说明：`checkAuth(options)` 会从请求头或本地存储读取 token，并通过 `_jwt.ts` 校验。

## 4. URL 匹配与参数解析

### 列表/普通查询

```ts
Mock.mock(/\/api\/xxx\/list/, 'get', (options: MockRequestOptions) => {
  const params = getQueryParams(options.url);
  const page = Number(params.page || '1');
  const pageSize = Number(params.pageSize || '20');
});
```

### 详情/更新/删除（路径参数）

```ts
Mock.mock(/\/api\/xxx\/[^/]+$/, 'get', (options: MockRequestOptions) => {
  const id = (options.url.split('/').pop() || '').split('?')[0];
});
```

## 5. CRUD 推荐模板

```ts
import Mock from 'mockjs';
import {
  checkAuth,
  getQueryParams,
  type MockRequestOptions,
  pageResponseSuccess,
  pagination,
  parseBody,
  responseError,
  responseSuccess,
} from '../_utils';

// 生成 Mock 数据
function generateMockModuleList(count: number) {
  return Array.from({ length: count }).map((_, index) => ({
    id: `${index + 1}`,
    name: Mock.Random.ctitle(5, 10),
    code: `CODE${String(index + 1).padStart(3, '0')}`,
    status: index % 2,
    remark: Mock.Random.csentence(10, 20),
    createTime: new Date().toISOString().replace('T', ' ').slice(0, 19),
    updateTime: new Date().toISOString().replace('T', ' ').slice(0, 19),
  }));
}

const mockModuleList = generateMockModuleList(100);

export function setupModuleMock() {
  // 列表接口（支持分页、筛选）
  Mock.mock(/\/api\/module\/list/, 'get', (options: MockRequestOptions) => {
    if (!checkAuth(options).authorized) {
      return responseError('Unauthorized Exception');
    }
    
    const params = getQueryParams(options.url);
    const page = Number(params.page || '1');
    const pageSize = Number(params.pageSize || '20');
    const name = params.name;
    const status = params.status;
    
    let listData = [...mockModuleList];
    
    // 筛选
    if (name) {
      listData = listData.filter((item) =>
        item.name.toLowerCase().includes(String(name).toLowerCase())
      );
    }
    if (['0', '1'].includes(status)) {
      listData = listData.filter((item) => item.status === Number(status));
    }
    
    // 分页
    const items = pagination(page, pageSize, listData);
    return pageResponseSuccess(items, listData.length);
  });

  // 详情接口
  Mock.mock(/\/api\/module\/[^/]+$/, 'get', (options: MockRequestOptions) => {
    if (!checkAuth(options).authorized) {
      return responseError('Unauthorized Exception');
    }
    
    const id = (options.url.split('/').pop() || '').split('?')[0];
    const item = mockModuleList.find((item) => item.id === id);
    
    if (!item) {
      return responseError('数据不存在');
    }
    
    return responseSuccess(item);
  });

  // 新增接口
  Mock.mock(/\/api\/module$/, 'post', (options: MockRequestOptions) => {
    if (!checkAuth(options).authorized) {
      return responseError('Unauthorized Exception');
    }
    
    const body = parseBody(options);
    const newItem = {
      id: String(Date.now()),
      ...body,
      createTime: new Date().toISOString().replace('T', ' ').slice(0, 19),
      updateTime: new Date().toISOString().replace('T', ' ').slice(0, 19),
    };
    
    mockModuleList.push(newItem);
    return responseSuccess(newItem);
  });

  // 编辑接口
  Mock.mock(/\/api\/module\/[^/]+$/, 'put', (options: MockRequestOptions) => {
    if (!checkAuth(options).authorized) {
      return responseError('Unauthorized Exception');
    }
    
    const id = (options.url.split('/').pop() || '').split('?')[0];
    const body = parseBody(options);
    
    const index = mockModuleList.findIndex((item) => item.id === id);
    if (index === -1) {
      return responseError('数据不存在');
    }
    
    mockModuleList[index] = {
      ...mockModuleList[index],
      ...body,
      updateTime: new Date().toISOString().replace('T', ' ').slice(0, 19),
    };
    
    return responseSuccess(mockModuleList[index]);
  });

  // 删除接口
  Mock.mock(/\/api\/module\/[^/]+$/, 'delete', (options: MockRequestOptions) => {
    if (!checkAuth(options).authorized) {
      return responseError('Unauthorized Exception');
    }
    
    const id = (options.url.split('/').pop() || '').split('?')[0];
    const index = mockModuleList.findIndex((item) => item.id === id);
    
    if (index === -1) {
      return responseError('数据不存在');
    }
    
    mockModuleList.splice(index, 1);
    return responseSuccess(null);
  });

  // 批量删除接口
  Mock.mock(/\/api\/module\/batch/, 'delete', (options: MockRequestOptions) => {
    if (!checkAuth(options).authorized) {
      return responseError('Unauthorized Exception');
    }
    
    const body = parseBody<{ ids: string[] }>(options);
    const ids = body.ids || [];
    
    ids.forEach((id) => {
      const index = mockModuleList.findIndex((item) => item.id === id);
      if (index !== -1) {
        mockModuleList.splice(index, 1);
      }
    });
    
    return responseSuccess(null);
  });
}
```

## 6. 模块注册规范

在 `apps/web-ele/src/mock/index.ts` 中注册新模块：

```ts
import { setupModuleMock } from './modules/module';

// 注册所有 Mock
setupModuleMock();
```

## 7. 迁移清单（backend-mock -> web-ele/src/mock）

1. 删除 Nitro/Server handler 写法
2. 改为 `Mock.mock(regex, method, handler)` 声明式注册
3. 把旧响应包装替换成 `_utils.ts` 统一函数
4. 把分页返回规范化为 `pageResponseSuccess(items, total)`
5. 受保护接口补齐 `checkAuth(options)`
6. 使用 `parseBody(options)` 解析请求体
7. 将模块封装为 `setup${Module}Mock()` 导出函数

## 8. 常见问题排查

### Mock 不生效

- 确认 `src/main.ts` 已导入 `#/mock`
- 确认 `apps/web-ele/src/mock/index.ts` 已调用模块的 setup 函数
- 确认路径正则与请求真实 URL 一致

### 返回格式不一致

- 统一改为 `_utils.ts` 的响应函数
- 禁止直接手写 ad-hoc JSON 返回

### 列表分页异常

- 确认 `page/pageSize` 转 number
- 确认先筛选后分页

### 鉴权失败

- 确认使用 `checkAuth(options)` 而不是 `checkAuth()`
- 确认返回 `responseError('Unauthorized Exception')`

