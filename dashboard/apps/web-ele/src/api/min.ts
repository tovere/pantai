import type { WatchData, WatchJob } from '#/api/watch';

import { requestClient } from '#/api/request';

/** 30分缓存状态 */
export interface MinStatus {
  count: number;
  latest: string;
  lastBar: string;
  coveragePct: number;
  sampleSize: number;
  lastFetched: string;
  agoMinutes: number;
}

/** 取最近一次30分盯盘结果(与 /watch/data 同构) */
export async function getMinDataApi() {
  return requestClient.get<WatchData>('/min/data');
}

/** 30分缓存状态 */
export async function getMinStatusApi() {
  return requestClient.get<MinStatus>('/min/status');
}

/** 异步跑单个30f策略变体; key='all' 跑全部。后台 job key 带 "m30:" 前缀 */
export async function runMinVariantApi(key: string) {
  return requestClient.post<{ started: string }>(`/min/run?key=${key}`);
}

/** 刷新全市场30分K线(后台 job key = m30:cache) */
export async function runMinUpdateApi() {
  return requestClient.post<{ started: string }>('/min/update');
}

export type { WatchData, WatchJob };
