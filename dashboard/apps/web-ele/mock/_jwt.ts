/**
 * JWT 工具（Mock 简化版）
 */

import type { UserInfo } from './_data';

// 模拟 token 存储（使用 localStorage 持久化）
const TOKEN_KEY = 'mock_token_store';

function getTokenStore(): Map<string, UserInfo> {
  const stored = localStorage.getItem(TOKEN_KEY);
  if (stored) {
    try {
      const obj = JSON.parse(stored);
      return new Map(Object.entries(obj));
    } catch {
      return new Map();
    }
  }
  return new Map();
}

function saveTokenStore(store: Map<string, UserInfo>): void {
  const obj = Object.fromEntries(store);
  localStorage.setItem(TOKEN_KEY, JSON.stringify(obj));
}

/**
 * 生成访问令牌
 */
export function generateAccessToken(user: UserInfo): string {
  const token = `mock_access_token_${user.username}_${Date.now()}`;
  const store = getTokenStore();
  store.set(token, user);
  saveTokenStore(store);
  return token;
}

/**
 * 生成刷新令牌
 */
export function generateRefreshToken(user: UserInfo): string {
  const token = `mock_refresh_token_${user.username}_${Date.now()}`;
  const store = getTokenStore();
  store.set(token, user);
  saveTokenStore(store);
  return token;
}

/**
 * 验证访问令牌
 */
export function verifyAccessToken(token: string): UserInfo | null {
  if (!token) return null;
  
  // 从 Authorization header 中提取 token
  const actualToken = token.replace('Bearer ', '').trim();
  const store = getTokenStore();
  return store.get(actualToken) || null;
}

/**
 * 清除令牌
 */
export function clearToken(token: string): void {
  const actualToken = token?.replace('Bearer ', '').trim();
  const store = getTokenStore();
  store.delete(actualToken);
  saveTokenStore(store);
}
