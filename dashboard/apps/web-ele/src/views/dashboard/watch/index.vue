<script lang="ts" setup>
import type { WatchData, WatchJob } from '#/api/watch';

import { computed, onMounted, onUnmounted, ref } from 'vue';

import { ElMessage } from 'element-plus';

import {
  getJobsApi,
  getWatchDataApi,
  runVariantApi,
} from '#/api/watch';

import HitTable from './HitTable.vue';

const data = ref<WatchData | null>(null);
const jobs = ref<Record<string, WatchJob>>({});
const loading = ref(false);
const activeTab = ref('');

let timer: any = null;
// 我主动发起、等待刷新的任务 key。用于捕捉 0.1s 秒退的 ETF —— 这类任务
// 完成得比一次轮询(1200ms)还快，仅靠"目击 running→done"会漏刷新。
const pending = new Set<string>();

const cards = computed(() => {
  const s = data.value?.summary;
  return [
    { label: '今日命中', value: s?.total ?? 0, hint: '全部策略去重前', color: '' },
    { label: 'A 下单级别', value: s?.gradeA ?? 0, hint: '干净回踩+转强', color: 'a' },
    { label: 'B 候选', value: s?.gradeB ?? 0, hint: '位置尚可待观察', color: 'b' },
  ];
});

const anyRunning = computed(() =>
  Object.values(jobs.value).some((j) => j.status === 'running'),
);

function jobOf(key: string): undefined | WatchJob {
  return jobs.value[key];
}

async function load() {
  try {
    data.value = await getWatchDataApi();
    if (!activeTab.value && data.value?.sections.length) {
      activeTab.value = data.value.sections[0]!.key;
    }
  } catch {
    ElMessage.error('取数据失败，确认 watch_server.py 是否已启动(:5320)');
  }
}

async function pollJobs() {
  try {
    const list = await getJobsApi();
    const next: Record<string, WatchJob> = {};
    let finished = false;
    for (const j of list) {
      next[j.key] = j;
      const prev = jobs.value[j.key];
      if (prev && prev.status === 'running' && j.status !== 'running') {
        finished = true;
      }
      // 我发起的任务已到终态（done/error）→ 刷新，即便从没目击到 running
      if (pending.has(j.key) && j.status !== 'running') {
        finished = true;
        pending.delete(j.key);
      }
    }
    jobs.value = next;
    if (finished) await load(); // 有任务刚跑完 → 刷新数据
  } catch {
    // 后端未起时静默
  }
  const running = Object.values(jobs.value).some((j) => j.status === 'running');
  timer = setTimeout(pollJobs, running ? 1200 : 4000);
}

async function runOne(key: string) {
  pending.add(key);
  await runVariantApi(key);
  ElMessage.info('已开始，进度见下方');
  await pollJobs();
}

async function runAll() {
  for (const s of data.value?.sections ?? []) pending.add(s.key);
  await runVariantApi('all');
  ElMessage.info('已开始全部重跑（顺序执行）');
  await pollJobs();
}

onMounted(async () => {
  loading.value = true;
  await load();
  await pollJobs();
  loading.value = false;
});

onUnmounted(() => timer && clearTimeout(timer));
</script>

<template>
  <div v-loading="loading" class="watch-page">
    <!-- 头部 -->
    <div class="head">
      <div class="head-left">
        <h2>📈 策略盯盘台</h2>
        <div class="meta">
          <span>数据 {{ data?.latestBar || '-' }}</span>
          <el-tag
            :type="data?.closed ? 'success' : 'warning'"
            size="small"
            effect="light"
          >
            {{ data?.closed ? '收盘定论' : '盘中快照' }}
          </el-tag>
          <span class="dim">生成于 {{ data?.generatedAt || '-' }}</span>
        </div>
      </div>
      <div class="head-right">
        <el-button
          type="primary"
          :loading="anyRunning"
          @click="runAll"
        >
          {{ anyRunning ? '重跑中…' : '全部重跑' }}
        </el-button>
      </div>
    </div>

    <!-- 统计卡 -->
    <div class="cards">
      <div v-for="c in cards" :key="c.label" class="card" :class="c.color">
        <div class="card-val">{{ c.value }}</div>
        <div class="card-label">{{ c.label }}</div>
        <div class="card-hint">{{ c.hint }}</div>
      </div>
    </div>

    <!-- 策略 Tab -->
    <el-card v-if="data" shadow="never" class="tab-card">
      <el-tabs v-model="activeTab">
        <el-tab-pane
          v-for="sec in data.sections"
          :key="sec.key"
          :name="sec.key"
        >
          <template #label>
            {{ sec.title }}
            <el-badge
              v-if="sec.count"
              :value="sec.count"
              :type="sec.hits.some((h) => h.grade === 'A') ? 'success' : 'primary'"
              class="tab-badge"
            />
            <el-icon
              v-if="jobOf(sec.key)?.status === 'running'"
              class="is-loading spin"
            >
              <svg viewBox="0 0 1024 1024" width="12" height="12">
                <path
                  fill="currentColor"
                  d="M512 64a32 32 0 0 1 32 32v192a32 32 0 0 1-64 0V96a32 32 0 0 1 32-32m0 640a32 32 0 0 1 32 32v192a32 32 0 1 1-64 0V736a32 32 0 0 1 32-32"
                />
              </svg>
            </el-icon>
          </template>

          <!-- 单策略操作条 + 进度 -->
          <div class="strat-bar">
            <el-button
              size="small"
              :loading="jobOf(sec.key)?.status === 'running'"
              @click="runOne(sec.key)"
            >
              重跑本策略
            </el-button>
            <span v-if="jobOf(sec.key)" class="job-meta">
              <template v-if="jobOf(sec.key)!.status === 'running'">
                <el-progress
                  :percentage="jobOf(sec.key)!.pct"
                  :stroke-width="10"
                  class="prog"
                />
                <span class="dim"
                  >{{ jobOf(sec.key)!.done }}/{{ jobOf(sec.key)!.total }}</span
                >
              </template>
              <template v-else-if="jobOf(sec.key)!.status === 'done'">
                <span class="dim"
                  >上次更新 {{ jobOf(sec.key)!.finishedAt }}</span
                >
              </template>
              <el-tag
                v-else-if="jobOf(sec.key)!.status === 'error'"
                type="danger"
                size="small"
                >出错: {{ jobOf(sec.key)!.error }}</el-tag
              >
            </span>
            <span v-if="sec.error" class="dim err">脚本错误: {{ sec.error }}</span>
          </div>

          <HitTable :section="sec" />
        </el-tab-pane>
      </el-tabs>
    </el-card>

    <p class="foot">
      评级规则见 <code>watch_grade.py</code>：中枢序号 / 距上沿 / 回踩天数 /
      放量滞涨 / 冲高回落 / 量能。红旗封顶 B，#3中枢直接剔除。仅供参考，不构成投资建议。
    </p>
  </div>
</template>

<style scoped>
.watch-page {
  padding: 16px 20px;
}
.head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 12px;
}
.head h2 {
  margin: 0;
  font-size: 20px;
  font-weight: 700;
}
.meta {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-top: 6px;
  font-size: 13px;
  color: var(--el-text-color-regular);
}
.dim {
  color: var(--el-text-color-secondary);
}
.cards {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  gap: 12px;
  margin: 16px 0;
}
.card {
  padding: 14px 16px;
  border-radius: 10px;
  background: var(--el-fill-color-light);
  border-left: 3px solid var(--el-border-color);
}
.card.a {
  border-left-color: #22c55e;
}
.card.b {
  border-left-color: #3b82f6;
}
.card-val {
  font-size: 26px;
  font-weight: 700;
  line-height: 1.1;
}
.card-label {
  margin-top: 2px;
  font-size: 13px;
  font-weight: 600;
}
.card-hint {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.tab-card {
  margin-top: 4px;
}
.tab-badge {
  margin-left: 6px;
}
.spin {
  margin-left: 4px;
  animation: rot 1s linear infinite;
}
@keyframes rot {
  to {
    transform: rotate(360deg);
  }
}
.strat-bar {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 10px;
}
.job-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
}
.prog {
  width: 180px;
}
.err {
  color: var(--el-color-danger);
}
.foot {
  margin-top: 14px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
  line-height: 1.6;
}
.foot code {
  padding: 1px 5px;
  border-radius: 4px;
  background: var(--el-fill-color);
}
</style>
