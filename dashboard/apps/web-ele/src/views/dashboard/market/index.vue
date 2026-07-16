<script lang="ts" setup>
import type { CacheStatus, MarketIndex, WatchJob } from '#/api/watch';

import { computed, onMounted, onUnmounted, ref } from 'vue';

import { ElMessage } from 'element-plus';

import {
  getCacheStatusApi,
  getIndicesApi,
  getJobsApi,
  updateCacheApi,
} from '#/api/watch';

import KlineChart from '../watch/KlineChart.vue';

const job = ref<null | WatchJob>(null);
const status = ref<CacheStatus | null>(null);
const indices = ref<MarketIndex[]>([]);
const activeSecid = ref('');
const klt = ref<number>(101);
const chartLoading = ref(false);
const PERIODS = [
  { label: '日线', value: 101 },
  { label: '30分', value: 30 },
  { label: '5分', value: 5 },
];
let timer: any = null;
let prevStatus = '';

const running = computed(() => job.value?.status === 'running');
const activeIndex = computed(
  () =>
    indices.value.find((i) => i.secid === activeSecid.value) ?? indices.value[0],
);

function chgClass(v: number) {
  return v > 0 ? 'up' : v < 0 ? 'down' : '';
}

async function fetchIndices() {
  chartLoading.value = true;
  try {
    indices.value = await getIndicesApi(klt.value);
    if (!activeSecid.value && indices.value.length) {
      activeSecid.value = indices.value[0]!.secid;
    }
  } catch {
    // ignore
  } finally {
    chartLoading.value = false;
  }
}

async function switchPeriod(v: number) {
  if (klt.value === v) return;
  klt.value = v;
  await fetchIndices();
}

function agoText(min: number) {
  if (min < 1) return '刚刚';
  if (min < 60) return `约 ${min} 分钟前`;
  const h = Math.floor(min / 60);
  if (h < 24) return `约 ${h} 小时前`;
  return `约 ${Math.floor(h / 24)} 天前`;
}

// 覆盖率颜色: 高绿、中橙、低红
const covColor = computed(() => {
  const c = status.value?.coveragePct ?? 0;
  return c >= 95 ? '#22c55e' : c >= 80 ? '#f59e0b' : '#ef4444';
});
// 新鲜度: 30分钟内算新鲜
const fresh = computed(() => (status.value?.agoMinutes ?? 9999) <= 30);
// 个股缓存数 = 磁盘缓存总数 − ETF 数(缓存标的数分列展示用)
const stockCount = computed(() => {
  const total = status.value?.dailyCount;
  if (total == null) return null;
  return total - (status.value?.etfCount ?? 0);
});

async function pull() {
  try {
    const list = await getJobsApi();
    job.value = list.find((j) => j.key === 'cache') ?? job.value;
  } catch {
    // 后端未起
  }
  try {
    status.value = await getCacheStatusApi();
  } catch {
    // ignore
  }
  // 缓存更新刚跑完 → 刷新指数K线
  if (prevStatus === 'running' && job.value?.status === 'done') {
    await fetchIndices();
  }
  prevStatus = job.value?.status ?? '';
  timer = setTimeout(pull, running.value ? 1000 : 8000);
}

async function update(mode: 'fast' | 'full') {
  await updateCacheApi(mode);
  ElMessage.info(
    mode === 'fast' ? '快速补最新中（只补缺票，很快）' : '全量重拉中，约 1 分钟',
  );
  await pull();
}

onMounted(async () => {
  await fetchIndices();
  await pull();
});
onUnmounted(() => timer && clearTimeout(timer));
</script>

<template>
  <div class="market-page">
    <el-card shadow="never">
      <template #header>
        <div class="hd">
          <span>🗄️ 大盘K线数据</span>
          <el-tag
            v-if="status"
            :type="fresh ? 'success' : 'warning'"
            size="small"
            effect="light"
          >
            {{ fresh ? '数据新鲜' : '可能偏旧' }}
          </el-tag>
        </div>
      </template>

      <!-- 真实缓存状态 -->
      <div class="stat-grid">
        <div class="stat">
          <div class="stat-val">{{ status?.latestDay || '-' }}</div>
          <div class="stat-label">最新交易日</div>
        </div>
        <div class="stat">
          <div class="stat-val" :style="{ color: covColor }">
            {{ status?.coveragePct ?? '-' }}%
          </div>
          <div
            class="stat-label"
            :title="`从磁盘缓存中固定随机抽 ${status?.sampleSize ?? 0} 只，其中最新K线日期=最新交易日(${status?.latestDay || '-'})的占比。其余多为停牌/退市。抽样估计，非全量逐只统计。`"
          >
            覆盖率<span class="dim">（抽样 {{ status?.sampleSize ?? 0 }}）</span>
          </div>
        </div>
        <div class="stat">
          <div class="stat-val big">{{ status?.lastFetched || '-' }}</div>
          <div class="stat-label">
            最后拉取
            <span class="dim">{{
              status ? agoText(status.agoMinutes) : ''
            }}</span>
          </div>
        </div>
        <div class="stat">
          <div class="stat-val">
            {{ stockCount ?? '-' }}<span class="dim sm"> 个股</span>
            <span class="sep">/</span>
            {{ status?.etfCount ?? 0 }}<span class="dim sm"> ETF</span>
          </div>
          <div class="stat-label">缓存标的数</div>
        </div>
      </div>

      <!-- 日期分布 -->
      <div v-if="status?.breakdown?.length" class="breakdown">
        <span class="dim">分布：</span>
        <el-tag
          v-for="b in status.breakdown"
          :key="b.date"
          size="small"
          :type="b.date === status.latestDay ? 'success' : 'info'"
          effect="plain"
          class="bd-tag"
        >
          {{ b.date }} · {{ b.n }}
        </el-tag>
      </div>

      <!-- 大盘指数K线: 最后一根蜡烛即数据到哪天, 最直观 -->
      <div v-if="indices.length" class="index-block">
        <div class="index-tabs">
          <button
            v-for="idx in indices"
            :key="idx.secid"
            class="idx-btn"
            :class="{ active: idx.secid === activeSecid }"
            @click="activeSecid = idx.secid"
          >
            <span class="idx-name">{{ idx.name }}</span>
            <span class="idx-chg" :class="chgClass(idx.chg)">
              {{ idx.chg > 0 ? '+' : '' }}{{ idx.chg.toFixed(2) }}%
            </span>
          </button>
        </div>
        <div v-if="activeIndex" class="index-head">
          <span class="idx-close">{{ activeIndex.close.toFixed(2) }}</span>
          <span class="idx-chg big" :class="chgClass(activeIndex.chg)">
            {{ activeIndex.chg > 0 ? '+' : '' }}{{ activeIndex.chg.toFixed(2) }}%
          </span>
          <span class="dim">最后K线 {{ activeIndex.date }}</span>
          <div class="period-seg">
            <button
              v-for="pd in PERIODS"
              :key="pd.value"
              class="pd-btn"
              :class="{ active: klt === pd.value }"
              @click="switchPeriod(pd.value)"
            >
              {{ pd.label }}
            </button>
          </div>
        </div>
        <div v-loading="chartLoading">
          <KlineChart
            v-if="activeIndex"
            :key="`${activeSecid}-${klt}`"
            :bars="activeIndex.bars"
          />
        </div>
      </div>

      <el-divider />

      <div class="modes">
        <div class="mode-card">
          <div class="mode-title">⚡ 快速刷新<span class="reco">推荐日常用</span></div>
          <div class="mode-desc">
            走<b>腾讯批量实时</b>(全市场约15次请求、秒级)，只覆盖每只<b>今天那根bar</b>——盘中反复点能刷最新价。量单位逐只自动校准。历史与前复权不动。<b>日常保鲜用它</b>。
          </div>
          <el-button
            type="primary"
            :loading="running && job?.mode === 'fast'"
            :disabled="running"
            @click="update('fast')"
          >
            快速刷新
          </el-button>
        </div>
        <div class="mode-card">
          <div class="mode-title">🔄 全量重拉<span class="src">腾讯</span></div>
          <div class="mode-desc">
            每只从 2025 至今<b>整段重下</b>（腾讯前复权），约 1 分钟。用于重建历史/补新标的；<b>日常保鲜用左边快速刷新即可</b>。
          </div>
          <el-button
            :loading="running && job?.mode === 'full'"
            :disabled="running"
            @click="update('full')"
          >
            全量重拉
          </el-button>
        </div>
      </div>

      <div v-if="job" class="prog-wrap">
        <template v-if="running">
          <span class="dim mode-tag">{{
            job.mode === 'fast' ? '快速刷新(腾讯)' : '全量重拉(腾讯)'
          }}</span>
          <el-progress :percentage="job.pct" :stroke-width="14" class="prog" />
          <span class="dim">{{ job.done }}/{{ job.total }} 只</span>
        </template>
        <el-tag v-else-if="job.status === 'done' && job.note" type="warning" size="small">
          ⚠️ {{ job.note }}
        </el-tag>
        <el-tag v-else-if="job.status === 'done'" type="success" size="small">
          上次{{ job.mode === 'full' ? '全量' : '快速' }}更新完成 {{ job.finishedAt }}
        </el-tag>
        <el-tag v-else-if="job.status === 'error'" type="danger" size="small">
          出错: {{ job.error }}
        </el-tag>
      </div>

      <p class="tip">
        更新的是<b>行情缓存</b>，不自动重跑策略。刷新完到「盯盘台」点「重跑本策略/全部重跑」用最新数据评级。命令行
        <code>python3 cache_data.py</code> 拉的也会在上方反映。
      </p>
    </el-card>
  </div>
</template>

<style scoped>
.market-page {
  padding: 16px 20px;
}
.hd {
  display: flex;
  align-items: center;
  gap: 10px;
  font-weight: 600;
}
.stat-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
  gap: 12px;
}
.stat {
  padding: 14px 16px;
  border-radius: 10px;
  background: var(--el-fill-color-light);
}
.stat-val {
  font-size: 24px;
  font-weight: 700;
  line-height: 1.15;
}
.stat-val.big {
  font-size: 18px;
}
.stat-val .sm {
  font-size: 13px;
  font-weight: 500;
}
.stat-val .sep {
  margin: 0 6px;
  font-weight: 400;
  color: var(--el-text-color-secondary);
}
.stat-label {
  margin-top: 4px;
  font-size: 13px;
  font-weight: 600;
}
.dim {
  color: var(--el-text-color-secondary);
  font-weight: 400;
}
.tiny {
  font-size: 11px;
  margin-left: 6px;
}
.breakdown {
  margin-top: 14px;
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 6px;
  font-size: 13px;
}
.bd-tag {
  font-variant-numeric: tabular-nums;
}
.desc {
  font-size: 14px;
  line-height: 1.7;
  color: var(--el-text-color-regular);
  margin-bottom: 14px;
}
.desc code {
  padding: 1px 5px;
  border-radius: 4px;
  background: var(--el-fill-color);
}
.modes {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
  gap: 14px;
}
.mode-card {
  padding: 14px 16px;
  border-radius: 10px;
  background: var(--el-fill-color-light);
  border: 1px solid var(--el-border-color-lighter);
}
.mode-title {
  font-size: 15px;
  font-weight: 700;
  display: flex;
  align-items: center;
  gap: 8px;
}
.reco {
  font-size: 11px;
  font-weight: 500;
  color: #fff;
  background: var(--el-color-primary);
  padding: 1px 6px;
  border-radius: 4px;
}
.src {
  font-size: 11px;
  font-weight: 500;
  color: var(--el-text-color-secondary);
  background: var(--el-fill-color);
  padding: 1px 6px;
  border-radius: 4px;
}
.mode-desc {
  font-size: 12px;
  line-height: 1.6;
  color: var(--el-text-color-regular);
  margin: 8px 0 12px;
  min-height: 48px;
}
.prog-wrap {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-top: 14px;
}
.mode-tag {
  font-weight: 600;
}
.prog {
  width: 260px;
}
.tip {
  margin-top: 18px;
  font-size: 12px;
  line-height: 1.7;
  color: var(--el-text-color-secondary);
}
.index-block {
  margin-top: 18px;
}
.index-tabs {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.idx-btn {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 2px;
  padding: 6px 12px;
  border-radius: 8px;
  border: 1px solid var(--el-border-color);
  background: var(--el-fill-color-light);
  cursor: pointer;
  transition: all 0.15s;
}
.idx-btn:hover {
  border-color: var(--el-color-primary);
}
.idx-btn.active {
  border-color: var(--el-color-primary);
  background: var(--el-color-primary-light-9);
}
.idx-name {
  font-size: 13px;
  font-weight: 600;
  color: var(--el-text-color-primary);
}
.idx-chg {
  font-size: 12px;
  font-variant-numeric: tabular-nums;
}
.idx-chg.big {
  font-size: 18px;
  font-weight: 700;
}
.index-head {
  display: flex;
  align-items: baseline;
  gap: 12px;
  margin: 12px 0 2px;
}
.period-seg {
  margin-left: auto;
  display: flex;
  gap: 0;
  align-self: center;
}
.pd-btn {
  padding: 4px 14px;
  font-size: 13px;
  border: 1px solid var(--el-border-color);
  background: var(--el-fill-color-light);
  cursor: pointer;
  color: var(--el-text-color-regular);
}
.pd-btn:first-child {
  border-radius: 6px 0 0 6px;
}
.pd-btn:last-child {
  border-radius: 0 6px 6px 0;
}
.pd-btn:not(:first-child) {
  border-left: none;
}
.pd-btn.active {
  background: var(--el-color-primary);
  color: #fff;
  border-color: var(--el-color-primary);
}
.idx-close {
  font-size: 22px;
  font-weight: 700;
}
.up {
  color: #ef4444;
}
.down {
  color: #22c55e;
}
</style>
