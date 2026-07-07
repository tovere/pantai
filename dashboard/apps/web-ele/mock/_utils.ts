/**
 * Mock 工具函数
 */

import { verifyAccessToken } from './_jwt';

/**
 * 成功响应
 */
export function responseSuccess<T = any>(data: T) {
  return {
    code: 0,
    data,
    error: null,
    message: 'ok',
  };
}

/**
 * 分页响应
 */
export function pageResponseSuccess<T = any>(items: T[], total: number) {
  return responseSuccess({
    items,
    total,
  });
}

/**
 * 错误响应
 */
export function responseError(message: string, error: any = null) {
  return {
    code: -1,
    data: null,
    error,
    message,
  };
}

/**
 * 验证用户权限（从 Pinia persist 的 localStorage 或 Mock token store 读取 token）
 */
export function checkAuth() {
  console.log('[Mock checkAuth] 开始验证权限');
  
  // 方案1：从 Pinia persist 的 localStorage 读取
  let accessToken = null;
  
  for (let i = 0; i < localStorage.length; i++) {
    const key = localStorage.key(i);
    if (key && key.includes('core-access')) {
      try {
        const data = JSON.parse(localStorage.getItem(key) || '{}');
        accessToken = data.accessToken;
        console.log('[Mock checkAuth] 从 Pinia localStorage 读取 token:', key, accessToken);
        break;
      } catch {
        // ignore
      }
    }
  }
  
  // 方案2：如果 Pinia 中没有，从 Mock token store 读取
  if (!accessToken) {
    console.log('[Mock checkAuth] Pinia 中没有 token，尝试从 Mock token store 读取');
    try {
      const mockTokenStore = JSON.parse(localStorage.getItem('mock_token_store') || '{}');
      console.log('[Mock checkAuth] Mock token store:', mockTokenStore);
      
      // 获取最新的 token（按时间戳排序）
      const tokens = Object.keys(mockTokenStore).filter(k => k.startsWith('mock_access_token'));
      console.log('[Mock checkAuth] 找到的 tokens:', tokens);
      
      if (tokens.length > 0) {
        // 取最新的 token
        tokens.sort((a, b) => {
          const timeA = parseInt(a.split('_').pop() || '0');
          const timeB = parseInt(b.split('_').pop() || '0');
          return timeB - timeA;
        });
        accessToken = tokens[0];
        console.log('[Mock checkAuth] 从 Mock token store 读取 token:', accessToken);
      }
    } catch (e) {
      console.error('[Mock checkAuth] 读取 Mock token store 失败:', e);
    }
  }
  
  console.log('[Mock checkAuth] 最终使用的 token:', accessToken);
  const userInfo = verifyAccessToken(accessToken || '');
  
  if (!userInfo) {
    console.log('[Mock checkAuth] Token 验证失败，未授权');
    return { authorized: false, userInfo: null, error: responseError('未授权') };
  }
  
  console.log('[Mock checkAuth] Token 验证成功:', userInfo.username);
  return { authorized: true, userInfo, error: null };
}

/**
 * 分页工具
 */
export function pagination<T = any>(
  pageNo: number,
  pageSize: number,
  array: T[],
): T[] {
  const offset = (pageNo - 1) * Number(pageSize);
  return offset + Number(pageSize) >= array.length
    ? array.slice(offset)
    : array.slice(offset, offset + Number(pageSize));
}

/**
 * 从 URL 中提取参数
 */
export function getQueryParams(url: string): Record<string, any> {
  const params: Record<string, any> = {};
  const queryString = url.split('?')[1];
  if (!queryString) return params;

  queryString.split('&').forEach((param) => {
    const [key, value] = param.split('=');
    params[decodeURIComponent(key)] = decodeURIComponent(value || '');
  });

  return params;
}

/**
 * 从 URL 中提取路径参数
 * @example extractPathParams('/api/user/123', '/api/user/:id') => { id: '123' }
 */
export function extractPathParams(
  url: string,
  pattern: string,
): Record<string, string> {
  const params: Record<string, string> = {};
  const urlParts = url.split('?')[0].split('/');
  const patternParts = pattern.split('/');

  patternParts.forEach((part, index) => {
    if (part.startsWith(':')) {
      const paramName = part.slice(1);
      params[paramName] = urlParts[index];
    }
  });

  return params;
}

/**
 * 延迟函数（模拟网络延迟）
 */
export function sleep(ms: number = 300) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}
