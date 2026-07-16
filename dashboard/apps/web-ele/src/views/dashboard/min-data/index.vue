<script lang="ts" setup>
import type { MinStatus } from '#/api/min';
import type { WatchJob } from '#/api/watch';

import { computed, onMounted, onUnmounted, ref } from 'vue';

import { ElMessage } from 'element-plus';

import { getMinStatusApi, runMinUpdateApi } from '#/api/min';
import { getJobsApi } from '#/api/watch';

// 30f 数据刷新的后台 job key
const CACHE_JOB_KEY = 'm30:cache';

const job = ref<null | WatchJob>(null);
const status = ref<MinStatus | null>(null);
let timer: any = null;

const running = computed(() => job.value?.status === 'running');

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

async function pull() {
  try {
    const list = await getJobsApi();
    job.value = list.find((j) => j.key === CACHE_JOB_KEY) ?? job.value;
  } catch {
    // 后端未起
  }
  try {
    status.value = await getMinStatusApi();
  } catch {
    // ignore
  }
  timer = setTimeout(pull, running.value ? 1000 : 8000);
}

async function update() {
  await runMinUpdateApi();
  ElMessage.info('全市场30分K线重拉中…');
  await pull();
}

onMounted(async () => {
  await pull();
});
onUnmounted(() => timer && clearTimeout(timer));
</script>

<template>
  <div class="market-page">
    <el-card shadow="never">
      <template #header>
        <div class="hd">
          <span>⏱️ 30分K线数据</span>
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
          <div class="stat-val">{{ status?.latest || '-' }}</div>
          <div class="stat-label">最新交易日</div>
        </div>
        <div class="stat">
          <div class="stat-val big">{{ status?.lastBar || '-' }}</div>
          <div class="stat-label">最新30分bar</div>
        </div>
        <div class="stat">
          <div class="stat-val" :style="{ color: covColor }">
            {{ status?.coveragePct ?? '-' }}%
          </div>
          <div
            class="stat-label"
            :title="`从磁盘缓存中固定随机抽 ${status?.sampleSize ?? 0} 只，其中最新30分bar对齐的占比。抽样估计，非全量逐只统计。`"
          >
            覆盖率<span class="dim">（抽样 {{ status?.sampleSize ?? 0 }}）</span>
          </div>
        </div>
        <div class="stat">
          <div class="stat-val">{{ status?.count ?? '-' }}</div>
          <div class="stat-label">缓存标的数</div>
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
      </div>

      <el-divider />

      <div class="modes">
        <div class="mode-card">
          <div class="mode-title">🔄 刷新30分<span class="src">全市场</span></div>
          <div class="mode-desc">
            全市场每只拉<b>最近约40天30分K线</b>并累积(约1分钟)。30分只有这一种刷新——既非日线快照、也非重下历史,单次接口本就只给约320根。刷完到「30F盯盘」点「重跑本策略/全部重跑」用最新数据评级。
          </div>
          <el-button
            type="primary"
            :loading="running"
            :disabled="running"
            @click="update"
          >
            刷新30分
          </el-button>
        </div>
      </div>

      <div v-if="job" class="prog-wrap">
        <template v-if="running">
          <span class="dim mode-tag">刷新30分</span>
          <el-progress :percentage="job.pct" :stroke-width="14" class="prog" />
          <span class="dim">{{ job.done }}/{{ job.total }} 只</span>
        </template>
        <el-tag v-else-if="job.status === 'done'" type="success" size="small">
          上次刷新完成 {{ job.finishedAt }}
        </el-tag>
        <el-tag v-else-if="job.status === 'error'" type="danger" size="small">
          出错: {{ job.error }}
        </el-tag>
      </div>

      <p class="tip">
        更新的是<b>30分行情缓存</b>，不自动重跑策略。刷新完到「30F盯盘」重跑策略用最新数据评级。
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
.stat-label {
  margin-top: 4px;
  font-size: 13px;
  font-weight: 600;
}
.dim {
  color: var(--el-text-color-secondary);
  font-weight: 400;
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
.tip code {
  padding: 1px 5px;
  border-radius: 4px;
  background: var(--el-fill-color);
}
</style>
