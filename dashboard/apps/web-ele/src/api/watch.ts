import { requestClient } from '#/api/request';

export interface WatchFlag {
  text: string;
  type: 'bad' | 'good' | 'warn';
}

/** 一根K线: [日期, 开, 收, 高, 低, 量] */
export type WatchBar = [string, number, number, number, number, number];

export interface WatchHit {
  code: string;
  name: string;
  secid: string;
  close: number;
  chg: number;
  amt: number;
  grade: 'A' | 'B' | 'C' | 'D';
  gradeScore: number;
  gradeNote: string;
  flags: WatchFlag[];
  levels: Record<string, null | number>;
  bars: WatchBar[];
  // 策略五(三买)字段
  box?: string;
  dist?: number;
  wbias10?: number;
  buy_low?: number;
  sos_date?: string;
  pull_days?: number;
  vol_shrink?: number;
  runup?: number;
  stage?: number;
  // 策略六(压缩蓄势)字段
  score?: number;
  band?: number;
  dist_high?: number;
  bias60?: number;
  vol_ratio?: number;
  coil?: string;
  stop?: number;
}

export interface WatchSection {
  key: string;
  strategy: 'chan_wyckoff_3buy' | 'squeeze_launch' | string;
  title: string;
  is_etf: boolean;
  count: number;
  hits: WatchHit[];
  error?: null | string;
}

export interface WatchData {
  generatedAt: string;
  screenDate: string;
  latestBar: string;
  closed: boolean;
  summary: { total: number; gradeA: number; gradeB: number };
  sections: WatchSection[];
}

export interface WatchJob {
  key: string;
  label: string;
  kind: 'cache' | 'variant';
  mode?: 'fast' | 'full';
  status: 'done' | 'error' | 'idle' | 'running';
  done: number;
  total: number;
  pct: number;
  startedAt?: string;
  finishedAt?: string;
  error?: null | string;
  note?: null | string;
}

export interface HistoryItem {
  date: string;
  generatedAt: string;
  closed: boolean;
  summary: { total: number; gradeA: number; gradeB: number };
}

export interface HistoryDay {
  date: string;
  generatedAt: string;
  closed: boolean;
  summary: { total: number; gradeA: number; gradeB: number };
  sections: {
    key: string;
    title: string;
    count: number;
    hits: Partial<WatchHit>[];
  }[];
}

/** 取最近一次盯盘结果 */
export async function getWatchDataApi() {
  return requestClient.get<WatchData>('/watch/data');
}

/** 异步跑单个策略变体; key='all' 跑全部 */
export async function runVariantApi(key: string) {
  return requestClient.post<{ started: string }>(`/watch/run?key=${key}`);
}

export interface CacheStatus {
  dailyCount: number;
  etfCount: number;
  latestDay: string;
  coveragePct: number;
  sampleSize: number;
  lastFetched: string;
  agoMinutes: number;
  breakdown: { date: string; n: number }[];
}

/** 更新大盘K线缓存。mode=fast 只补缺最新交易日的票(轻/防反爬); full 全市场重拉 */
export async function updateCacheApi(mode: 'fast' | 'full' = 'fast') {
  return requestClient.post<{ started: string; mode: string }>(
    `/cache/update?mode=${mode}`,
  );
}

/** 读磁盘真实缓存状态(含命令行拉取) */
export async function getCacheStatusApi() {
  return requestClient.get<CacheStatus>('/cache/status');
}

export interface MarketIndex {
  name: string;
  secid: string;
  bars: WatchBar[];
  close: number;
  chg: number;
  date: string;
}

/** 主要大盘指数K线(现拉最新)。klt: 101 日线 / 30 / 5 分钟 */
export async function getIndicesApi(klt: number | string = 101) {
  return requestClient.get<MarketIndex[]>(`/market/indices?klt=${klt}`);
}

/** 所有后台任务进度(轮询用) */
export async function getJobsApi() {
  return requestClient.get<WatchJob[]>('/jobs');
}

/** 历史命中日期列表 */
export async function getHistoryListApi() {
  return requestClient.get<HistoryItem[]>('/watch/history');
}

/** 某日命中快照 */
export async function getHistoryDayApi(date: string) {
  return requestClient.get<HistoryDay>(`/watch/history?date=${date}`);
}
