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
  industry?: string;
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
  // 策略七(超跌放量回踩二买；兼容旧Spring字段)
  l1?: number;
  l2?: number;
  higher_low?: number;
  rebound_vr?: number;
  pull_vol_ratio?: number;
  oversold20?: number;
  rebound_date?: string;
  range_low?: number;
  spring_low?: number;
  spring_date?: string;
  up_from_spring?: number;
  div_pct?: number;
  // 策略八(N字反包)字段
  peak?: number;
  pull_low?: number;
  shrink?: number;
  vexp?: number;
  // 策略九(蒸馏版)字段
  kind?: 'chan_3buy' | 'coil_launch' | 'spring_2buy' | string;
  setup?: string;
  s9_priority?: number;
  // 策略十(严格笔中枢·缠论三买)字段
  zg?: number;
  zd?: number;
  risk?: number;
  lag?: number;
  /** 30分钟次级别共振命中的买点类型, 空串=无共振 */
  sub?: string;
  /** 建议仓位系数(一买0.3/二买0.6/三买1.0) */
  pos?: number;
  type?: number;
  /** 策略十市场联合分档使用的沪深300ETF趋势输入 */
  marketRet5?: number;
  marketRet20?: number;
  marketRet60?: number;
  marketAbove20?: boolean;
  marketAbove60?: boolean;
  marketMa20Above60?: boolean;
  // 策略十一(VDB后缩量回踩)字段
  vdb_date?: string;
  vdb_low?: number;
  vdb_high?: number;
  chain?: number;
  dist_vdb?: number;
  ret20?: number;
  reclaim?: number;
  reversal?: number;
  /** 总市值(亿元) */
  mktcap?: number;
  // 策略十二(全A主板连小阳)字段
  streak?: number;
  yang_n?: number;
  small_n?: number;
  net?: number;
  avg_chg?: number;
  avg_body?: number;
  max_chg?: number;
  win_low?: number;
  vol_base?: number;
  window?: number;
  above_ma20?: number;
  dist_ma20?: number;
  tier?: number;
  // 策略十四(底部放量第一根大阳)字段
  body?: number;
  pos60?: number;
  base_low?: number;
  sig_low?: number;
  // 策略十五(昨大涨今缩量回踩)
  prev_chg?: number;
  prev_close?: number;
  prev_low?: number;
  prev_high?: number;
  limit?: number;
}

export interface WatchSection {
  key: string;
  strategy: 'chan_wyckoff_3buy' | 'squeeze_launch' | string;
  title: string;
  is_etf: boolean;
  count: number;
  hits: WatchHit[];
  error?: null | string;
  btNote?: string;
  gradeBtNote?: string;
  conclusionNote?: string;
}

export interface WatchData {
  generatedAt: string;
  screenDate: string;
  latestBar: string;
  closed: boolean;
  frozenDate?: string;
  frozenAt?: string;
  summary: { total: number; gradeA: number; gradeB: number };
  sections: WatchSection[];
}

export interface WatchJob {
  key: string;
  label: string;
  kind: 'auction' | 'cache' | 'variant';
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

export type AuctionAction = 'buy' | 'skip' | 'watch';

export type AuctionSettleTag =
  | '竞价中'
  | '无对照'
  | '平稳撮合'
  | '尾盘放量'
  | '尾盘抢筹'
  | '尾盘砸盘'
  | '尾盘翻多'
  | '尾盘翻空';

export type AuctionTag =
  | '均衡'
  | '放量'
  | '无数据'
  | '无竞价'
  | '抢筹'
  | '抛压'
  | '真空';

export interface AuctionOpenItem {
  action: AuctionAction;
  auction_amount?: null | number;
  auction_pct?: null | number;
  auction_price?: null | number;
  auction_strength?: null | number;
  auction_tag?: AuctionTag | string;
  auction_turnover_pct?: null | number;
  auction_unmatched?: null | number;
  auction_volume?: null | number;
  auction_volume_ratio?: null | number;
  auction_yesterday_ratio_pct?: null | number;
  close?: null | number;
  close_pct?: null | number;
  close_price?: null | number;
  code: string;
  grade: 'A' | 'B' | 'C' | 'D';
  gradeNote?: string;
  industry?: string;
  is_etf: boolean;
  last_price?: null | number;
  name: string;
  open_pct?: null | number;
  open_price?: null | number;
  prev_price?: null | number;
  pre_settle_at?: null | string;
  price_delta?: null | number;
  reason: string;
  ref_price?: null | number;
  section_keys: string[];
  settle_strength?: null | number;
  settle_tag?: AuctionSettleTag | string;
  stop?: null | number;
  strategies: string[];
  thscode: string;
  unmatched_delta?: null | number;
  unmatched_ratio?: null | number;
  vol_delta?: null | number;
  vol_delta_pct?: null | number;
}

export interface AuctionOpenData {
  auctionMeta?: Record<string, unknown>;
  benchmark?: null | {
    count: number;
    date?: string;
    item: {
      auction_pct?: number;
      name?: string;
      tags?: string[];
      thscode?: string;
      ticker?: string;
    }[];
  };
  error?: null | string;
  frozenDate?: string;
  generatedAt: string;
  items: AuctionOpenItem[];
  latestBar?: string;
  note?: string;
  preSettleAt?: null | string;
  screenDate: string;
  stage: 'final' | 'live' | 'watch';
  summary: { buy: number; skip: number; total: number; watch: number };
  tapeDate?: string;
  tapeTicks?: number;
  watchFrozen?: boolean;
  watchSkipped?: string;
  watchSource?: string;
  watchSourceLabel?: string;
}

export async function getAuctionOpenApi() {
  return requestClient.get<AuctionOpenData>('/auction/open');
}

export async function runAuctionOpenApi(stage: 'final' | 'live' | 'watch' = 'final') {
  return requestClient.post<{ stage: string; started: string }>(
    `/auction/run?stage=${stage}`,
  );
}
