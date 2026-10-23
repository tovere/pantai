<script lang="ts" setup>
import type { WatchData, WatchJob } from '#/api/watch';

import { computed, onMounted, onUnmounted, ref } from 'vue';

import { ElMessage } from 'element-plus';

import { getJobsApi, getWatchDataApi, runVariantApi } from '#/api/watch';

import CandidatePool from '../_shared/CandidatePool.vue';
import HitTable from './HitTable.vue';

const data = ref<WatchData | null>(null);
const jobs = ref<Record<string, WatchJob>>({});
const loading = ref(false);
const activeTab = ref('');

let timer: ReturnType<typeof setTimeout> | undefined;
let disposed = false;
let polling = false;
const submitting = ref(false);
const refreshError = ref('');
const refreshedAt = ref('');
// 我主动发起、等待刷新的任务 key。用于捕捉 0.1s 秒退的 ETF —— 这类任务
// 完成得比一次轮询(1200ms)还快，仅靠"目击 running→done"会漏刷新。
const pending = new Set<string>();

const cards = computed(() => {
  const s = data.value?.summary;
  return [
    {
      label: '今日命中',
      value: s?.total ?? '—',
      hint: '全部策略去重前',
      color: '',
    },
    {
      label: 'A 级候选',
      value: s?.gradeA ?? '—',
      hint: '干净回踩+转强',
      color: 'a',
    },
    {
      label: 'B 候选',
      value: s?.gradeB ?? '—',
      hint: '位置尚可待观察',
      color: 'b',
    },
  ];
});

const anyRunning = computed(() =>
  submitting.value || Object.values(jobs.value).some((j) => j.status === 'running'),
);

function jobOf(key: string): undefined | WatchJob {
  return jobs.value[key];
}

async function load() {
  try {
    data.value = await getWatchDataApi();
    refreshError.value = '';
    refreshedAt.value = new Date().toLocaleTimeString('zh-CN');
    if (!activeTab.value && data.value?.sections.length) {
      activeTab.value = data.value.sections[0]!.key;
    }
  } catch {
    refreshError.value = '数据刷新失败，当前保留上次成功结果';
  }
}

async function pollJobs() {
  if (disposed || polling) return;
  clearTimeout(timer);
  polling = true;
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
    refreshError.value = '任务连接异常，当前结果可能不是最新数据';
  }
  const running = Object.values(jobs.value).some((j) => j.status === 'running');
  polling = false;
  if (!disposed) timer = setTimeout(pollJobs, document.hidden ? 30000 : running ? 1200 : 4000);
}

async function submit(key: string) {
  if (anyRunning.value) return;
  submitting.value = true;
  const keys = key === 'all' ? (data.value?.sections ?? []).map((s) => s.key) : [key];
  try {
    await runVariantApi(key);
    keys.forEach((item) => pending.add(item));
    ElMessage.info('任务已提交');
    await pollJobs();
  } catch {
    keys.forEach((item) => pending.delete(item));
    ElMessage.error('提交失败，请重试');
  } finally {
    submitting.value = false;
  }
}
const runOne = (key: string) => submit(key);
const runAll = () => submit('all');

onMounted(async () => {
  loading.value = true;
  await load();
  await pollJobs();
  loading.value = false;
});

onUnmounted(() => { disposed = true; clearTimeout(timer); });
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
            {{ data?.closed ? '收盘定论' : '盘中预览' }}
          </el-tag>
          <el-tag
            v-if="data?.frozenDate"
            type="success"
            size="small"
            effect="plain"
          >
            已锁收盘 {{ data.frozenDate }}
          </el-tag>
          <span class="dim">生成于 {{ data?.generatedAt || '-' }}</span>
        </div>
      </div>
      <div class="head-right">
        <el-button type="primary" :loading="anyRunning" @click="runAll">
          {{ anyRunning ? '重跑中…' : '全部重跑' }}
        </el-button>
      </div>
    </div>

    <el-alert v-if="refreshError" :title="refreshError" type="warning" :closable="false">
      <el-button size="small" @click="load">重试刷新</el-button>
    </el-alert>
    <p v-if="refreshedAt" class="dim">最近成功刷新 {{ refreshedAt }}</p>
    <CandidatePool v-if="data" :data="data" />
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
      <el-tabs v-model="activeTab" tab-position="left" class="side-tabs">
        <el-tab-pane
          v-for="sec in data.sections"
          :key="sec.key"
          :name="sec.key"
        >
          <template #label>
            <span class="tab-title">{{ sec.title }}</span>
            <el-badge
              v-if="sec.count"
              :value="sec.count"
              :type="
                sec.hits.some((h) => h.grade === 'A') ? 'success' : 'primary'
              "
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
              :disabled="submitting"
              :loading="jobOf(sec.key)?.status === 'running'"
              @click="runOne(sec.key)"
            >
              重跑本策略
            </el-button>
            <span v-if="sec.btNote" class="bt-note"
              >回测 {{ sec.btNote }}</span
            >
            <span v-if="sec.gradeBtNote" class="grade-bt-note">
              ABC {{ sec.gradeBtNote }}
            </span>
            <span v-if="sec.conclusionNote" class="conclusion-note">
              用法 {{ sec.conclusionNote }}
            </span>
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
            <span v-if="sec.error" class="dim err"
              >脚本错误: {{ sec.error }}</span
            >
          </div>

          <HitTable :section="sec" />
        </el-tab-pane>
      </el-tabs>
    </el-card>

    <p class="foot">
      评级规则见 <code>watch_grade.py</code>：中枢序号 / 距上沿 / 回踩天数 /
      放量滞涨 / 冲高回落 / 量能。红旗封顶
      B，#3中枢直接剔除。仅供参考，不构成投资建议。
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
  flex-wrap: wrap;
  gap: 12px;
  margin-bottom: 10px;
}
.grade-bt-note {
  padding: 2px 8px;
  border: 1px solid var(--el-color-success-light-7);
  border-radius: 4px;
  background: var(--el-color-success-light-9);
  color: var(--el-text-color-regular);
  font-size: 12px;
}
.conclusion-note {
  padding: 2px 8px;
  border-left: 3px solid var(--el-color-warning);
  color: var(--el-text-color-primary);
  background: var(--el-color-warning-light-9);
  font-size: 12px;
}
.bt-note {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  background: var(--el-fill-color-light);
  padding: 2px 8px;
  border-radius: 4px;
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

<style src="../_shared/side-tabs.css"></style>
