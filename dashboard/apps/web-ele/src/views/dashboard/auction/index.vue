<script lang="ts" setup>
import type { AuctionAction, AuctionOpenData, WatchJob } from '#/api/watch';

import { computed, onMounted, onUnmounted, ref } from 'vue';

import { ElMessage } from 'element-plus';

import { getAuctionOpenApi, getJobsApi, runAuctionOpenApi } from '#/api/watch';

const data = ref<AuctionOpenData | null>(null);
const jobs = ref<Record<string, WatchJob>>({});
const loading = ref(false);
const tab = ref<'all' | AuctionAction>('buy');

let timer: ReturnType<typeof setTimeout> | null = null;
const pending = new Set<string>();

type TagType = 'danger' | 'info' | 'primary' | 'success' | 'warning';
const GRADE_TYPE: Record<string, TagType> = {
  A: 'success',
  B: 'primary',
  C: 'info',
  D: 'danger',
};
const ACTION_TYPE: Record<string, TagType> = {
  buy: 'success',
  watch: 'warning',
  skip: 'info',
};
const ACTION_LABEL: Record<string, string> = {
  buy: '可买',
  watch: '观察',
  skip: '放弃',
};

const TAG_TYPE: Record<string, TagType> = {
  抢筹: 'danger',
  放量: 'success',
  均衡: 'info',
  真空: 'warning',
  抛压: 'info',
  无竞价: 'info',
  无数据: 'info',
};
const SETTLE_TYPE: Record<string, TagType> = {
  尾盘抢筹: 'danger',
  尾盘翻多: 'danger',
  尾盘放量: 'success',
  平稳撮合: 'info',
  尾盘砸盘: 'warning',
  尾盘翻空: 'warning',
  无对照: 'info',
  竞价中: 'info',
};

const running = computed(() => jobs.value.auction?.status === 'running');

const cards = computed(() => {
  const s = data.value?.summary;
  return [
    { label: '可买', value: s?.buy ?? 0, hint: '评级过关，竞价非真空/抛压', color: 'a' },
    { label: '观察', value: s?.watch ?? 0, hint: '真空开/抛压/尾盘砸盘/全量池/C档', color: 'b' },
    { label: '放弃', value: s?.skip ?? 0, hint: '涨停买不进或开盘破止损', color: '' },
    { label: '候选', value: s?.total ?? 0, hint: '昨晚命中去重后', color: '' },
  ];
});

const rows = computed(() => {
  const items = data.value?.items ?? [];
  if (tab.value === 'all') return items;
  return items.filter((it) => it.action === tab.value);
});

function chgClass(v?: null | number) {
  if (v == null) return '';
  return v > 0 ? 'up' : v < 0 ? 'down' : '';
}
function fmt(v?: null | number, digits = 2) {
  return v == null ? '-' : v.toFixed(digits);
}
function sign(v?: null | number, digits = 2) {
  if (v == null) return '-';
  return `${v > 0 ? '+' : ''}${v.toFixed(digits)}`;
}
function fmtAmt(v?: null | number) {
  if (v == null) return '-';
  if (Math.abs(v) >= 10000) return `${(v / 10000).toFixed(1)}万`;
  return v.toFixed(0);
}
function fmtVol(v?: null | number) {
  if (v == null) return '-';
  if (Math.abs(v) >= 10000) return `${(v / 10000).toFixed(1)}万`;
  return Math.round(v).toString();
}

async function load() {
  try {
    data.value = await getAuctionOpenApi();
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
      if (pending.has(j.key) && j.status !== 'running') {
        finished = true;
        pending.delete(j.key);
      }
    }
    jobs.value = next;
    if (finished) await load();
    else if (next.auction?.status === 'running') await load();
  } catch {
    // 后端未起时静默
  }
  const busy = Object.values(jobs.value).some((j) => j.status === 'running');
  timer = setTimeout(pollJobs, busy ? 1200 : 4000);
}

async function refresh(stage: 'final' | 'live' | 'watch') {
  pending.add('auction');
  await runAuctionOpenApi(stage);
  const msg =
    stage === 'watch'
      ? '盯竞价：9:15–9:25 连拍，9:25 对照终态'
      : stage === 'live'
        ? '正在拉竞价实时'
        : '正在拉竞价终态/开盘';
  ElMessage.info(msg);
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
    <div class="head">
      <div class="head-left">
        <h2>今早可买</h2>
        <div class="meta">
          <span>策略日 {{ data?.screenDate || '-' }}</span>
          <el-tag
            v-if="data?.watchSourceLabel"
            :type="data.watchFrozen ? 'success' : 'danger'"
            size="small"
            effect="plain"
          >
            {{ data.watchSourceLabel }}
          </el-tag>
          <el-tag size="small" effect="light">
            {{
              data?.stage === 'watch'
                ? '竞价连拍中'
                : data?.stage === 'live'
                  ? '竞价实时'
                  : '竞价终态/开盘'
            }}
          </el-tag>
          <span v-if="data?.tapeTicks" class="dim">
            tape {{ data.tapeTicks }} 拍
            <template v-if="data.preSettleAt">· 对照 {{ data.preSettleAt }}</template>
          </span>
          <span class="dim">生成于 {{ data?.generatedAt || '尚未跑过' }}</span>
          <span v-if="running && jobs.auction?.note" class="dim">{{ jobs.auction.note }}</span>
        </div>
      </div>
      <div class="head-right">
        <el-button :loading="running" @click="refresh('watch')">盯竞价</el-button>
        <el-button :loading="running" @click="refresh('live')">拉竞价实时</el-button>
        <el-button type="primary" :loading="running" @click="refresh('final')">
          {{ running ? '刷新中…' : '刷新今早清单' }}
        </el-button>
      </div>
    </div>

    <el-alert
      v-if="data?.error"
      :title="data.error"
      type="error"
      show-icon
      :closable="false"
      class="src-alert"
    />

    <div class="cards">
      <div v-for="c in cards" :key="c.label" class="card" :class="c.color">
        <div class="card-val">{{ c.value }}</div>
        <div class="card-label">{{ c.label }}</div>
        <div class="card-hint">{{ c.hint }}</div>
      </div>
    </div>

    <el-card shadow="never" class="tab-card">
      <el-tabs v-model="tab">
        <el-tab-pane label="可买" name="buy" />
        <el-tab-pane label="观察" name="watch" />
        <el-tab-pane label="放弃" name="skip" />
        <el-tab-pane label="全部" name="all" />
      </el-tabs>

      <el-empty
        v-if="!rows.length"
        :description="data?.generatedAt ? '这一档没有票' : '先点右上角刷新今早清单'"
      />
      <el-table v-else :data="rows" row-key="thscode" size="small" stripe>
        <el-table-column label="结论" width="72">
          <template #default="{ row }">
            <el-tag :type="ACTION_TYPE[row.action]" effect="dark" size="small">
              {{ ACTION_LABEL[row.action] }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="评级" width="56">
          <template #default="{ row }">
            <el-tag :type="GRADE_TYPE[row.grade]" effect="dark" size="small">
              {{ row.grade }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="代码" width="76" prop="code" />
        <el-table-column label="名称" width="96" prop="name" show-overflow-tooltip />
        <el-table-column label="竞价" width="72">
          <template #default="{ row }">
            <el-tag
              v-if="row.auction_tag"
              :type="TAG_TYPE[row.auction_tag] || 'info'"
              effect="plain"
              size="small"
            >
              {{ row.auction_tag }}
            </el-tag>
            <span v-else>-</span>
          </template>
        </el-table-column>
        <el-table-column label="结算" width="88">
          <template #default="{ row }">
            <el-tag
              v-if="row.settle_tag"
              :type="SETTLE_TYPE[row.settle_tag] || 'info'"
              effect="plain"
              size="small"
            >
              {{ row.settle_tag }}
            </el-tag>
            <span v-else>-</span>
          </template>
        </el-table-column>
        <el-table-column label="尾量" width="64" align="right">
          <template #default="{ row }">
            <span :class="chgClass(row.vol_delta_pct)">
              {{ row.vol_delta_pct == null ? '-' : sign(row.vol_delta_pct * 100, 0) + '%' }}
            </span>
          </template>
        </el-table-column>
        <el-table-column label="行业" width="88" prop="industry" show-overflow-tooltip>
          <template #default="{ row }">
            {{ row.industry || '-' }}
          </template>
        </el-table-column>
        <el-table-column label="开盘%" width="76" align="right">
          <template #default="{ row }">
            <span :class="chgClass(row.open_pct)">{{ sign(row.open_pct) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="开盘价" width="80" align="right">
          <template #default="{ row }">
            {{ fmt(row.ref_price ?? row.open_price ?? row.auction_price) }}
          </template>
        </el-table-column>
        <el-table-column label="收盘价" width="80" align="right">
          <template #default="{ row }">
            {{ fmt(row.close_price) }}
          </template>
        </el-table-column>
        <el-table-column label="收盘%" width="76" align="right">
          <template #default="{ row }">
            <span :class="chgClass(row.close_pct)">{{ sign(row.close_pct) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="量比" width="64" align="right">
          <template #default="{ row }">
            <span :class="row.auction_tag === '真空' ? 'down' : ''">
              {{ fmt(row.auction_volume_ratio, 2) }}
            </span>
          </template>
        </el-table-column>
        <el-table-column label="成交(手)" width="84" align="right">
          <template #default="{ row }">
            {{ fmtVol(row.auction_volume) }}
          </template>
        </el-table-column>
        <el-table-column label="未匹配" width="84" align="right">
          <template #default="{ row }">
            <span :class="chgClass(row.auction_unmatched)">
              {{ row.auction_unmatched == null ? '-' : fmtVol(row.auction_unmatched) }}
            </span>
          </template>
        </el-table-column>
        <el-table-column label="竞价额" width="80" align="right">
          <template #default="{ row }">
            {{ fmtAmt(row.auction_amount) }}
          </template>
        </el-table-column>
        <el-table-column label="止损" width="72" align="right">
          <template #default="{ row }">
            {{ fmt(row.stop) }}
          </template>
        </el-table-column>
        <el-table-column label="策略" min-width="160" show-overflow-tooltip>
          <template #default="{ row }">
            {{ row.strategies.join(' / ') }}
          </template>
        </el-table-column>
        <el-table-column label="原因" min-width="200" show-overflow-tooltip prop="reason" />
      </el-table>
    </el-card>

    <p class="foot">
      {{ data?.note || '昨晚策略命中 ∩ 今早开盘。近涨停买不进、破止损放弃。不构成投资建议。' }}
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
.head-right {
  display: flex;
  gap: 8px;
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
  border-left-color: #eab308;
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
.src-alert {
  margin-top: 12px;
}
.up {
  color: #ef4444;
}
.down {
  color: #22c55e;
}
.foot {
  margin-top: 14px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
  line-height: 1.6;
}
</style>
