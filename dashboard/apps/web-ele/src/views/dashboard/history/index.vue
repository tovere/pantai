<script lang="ts" setup>
import type { HistoryDay, HistoryItem } from '#/api/watch';

import { computed, onMounted, ref } from 'vue';

import { getHistoryDayApi, getHistoryListApi } from '#/api/watch';

const list = ref<HistoryItem[]>([]);
const day = ref<HistoryDay | null>(null);
const activeDate = ref('');
const activeTab = ref('');
const compareDate = ref('');
const baseline = ref<HistoryDay | null>(null);
const error = ref('');
let requestId = 0;
const loading = ref(false);
const changes = computed(() => {
  const flatten = (value: HistoryDay | null) => {
    const map = new Map<string, { code: string; name: string; grade: string }>();
    for (const section of value?.sections ?? []) for (const hit of section.hits) {
      if (!hit.code) continue;
      const previous = map.get(hit.code);
      if (!previous || (hit.grade ?? 'D') < previous.grade)
        map.set(hit.code, { code: hit.code, name: hit.name ?? '', grade: hit.grade ?? 'D' });
    }
    return map;
  };
  const current = flatten(day.value);
  const prior = flatten(baseline.value);
  return [...new Set([...current.keys(), ...prior.keys()])].map(code => {
    const now = current.get(code);
    const before = prior.get(code);
    return { code, name: now?.name ?? before?.name, before: before?.grade ?? '—', after: now?.grade ?? '—',
      change: !before ? '新增' : !now ? '消失' : now.grade < before.grade ? '评级提升' : now.grade > before.grade ? '评级下降' : '连续命中' };
  });
});
async function compare() {
  const date = compareDate.value;
  baseline.value = null;
  if (!date) return;
  try {
    const result = await getHistoryDayApi(date);
    if (date === compareDate.value) baseline.value = result;
  } catch { error.value = '对比数据加载失败，请重新选择日期'; }
}

const GRADE_TYPE: Record<string, 'success' | 'primary' | 'info' | 'danger' | 'warning'> = {
  A: 'success',
  B: 'primary',
  C: 'info',
  D: 'danger',
};
const FLAG_TYPE: Record<string, 'success' | 'primary' | 'info' | 'danger' | 'warning'> = {
  good: 'success',
  warn: 'warning',
  bad: 'danger',
};

function chgClass(v?: number) {
  return v == null ? '' : v > 0 ? 'up' : v < 0 ? 'down' : '';
}

async function openDay(date: string) {
  const id = ++requestId;
  loading.value = true;
  error.value = '';
  try {
    const result = await getHistoryDayApi(date);
    if (id !== requestId) return;
    activeDate.value = date;
    day.value = result;
    const first = result.sections.find((s) => s.count > 0);
    activeTab.value = first?.key ?? result.sections[0]?.key ?? '';
  } catch { if (id === requestId) error.value = '历史加载失败，请重试'; }
  finally { if (id === requestId) loading.value = false; }
}

onMounted(async () => {
  try { list.value = await getHistoryListApi(); } catch { error.value = '日期列表加载失败，请刷新页面'; }
  if (list.value.length) await openDay(list.value[0]!.date);
});
</script>

<template>
  <div class="hist-page" v-loading="loading">
    <el-alert v-if="error" :title="error" type="error" :closable="false" />
    <el-card shadow="never" style="margin-bottom: 14px">
      <span>对比基准日期：</span>
      <el-select v-model="compareDate" clearable placeholder="选择另一个日期" style="width: 200px" @change="compare">
        <el-option v-for="item in list" :key="item.date" :value="item.date" :label="item.date" :disabled="item.date === activeDate" />
      </el-select>
      <p v-if="baseline">{{ baseline.date }} → {{ activeDate }}（各日期按代码去重、取最高评级）</p>
      <el-table v-if="baseline" :data="changes" max-height="320">
        <el-table-column prop="code" label="代码" />
        <el-table-column prop="name" label="名称" />
        <el-table-column prop="before" label="基准评级" />
        <el-table-column prop="after" label="当前评级" />
        <el-table-column prop="change" label="变化" :filters="['新增','消失','评级提升','评级下降','连续命中'].map(text => ({text, value:text}))" :filter-method="(value, row) => row.change === value" />
      </el-table>
    </el-card>
    <div class="layout">
      <!-- 左: 日期列表 -->
      <el-card shadow="never" class="side">
        <template #header><span class="hd">📅 命中记录</span></template>
        <el-empty v-if="!list.length" description="暂无历史" :image-size="60" />
        <div
          v-for="it in list"
          :key="it.date"
          class="day-item"
          :class="{ active: it.date === activeDate }"
          @click="openDay(it.date)"
        >
          <div class="day-date">
            {{ it.date }}
            <el-tag
              :type="it.closed ? 'success' : 'warning'"
              size="small"
              effect="plain"
            >
              {{ it.closed ? '收盘' : '盘中' }}
            </el-tag>
          </div>
          <div class="day-sum">
            命中 {{ it.summary.total }} · A{{ it.summary.gradeA }} · B{{
              it.summary.gradeB
            }}
          </div>
        </div>
      </el-card>

      <!-- 右: 当日明细 -->
      <el-card shadow="never" class="main">
        <template #header>
          <span class="hd">{{ activeDate || '—' }} 命中明细</span>
          <span v-if="day" class="dim">（生成于 {{ day.generatedAt }}）</span>
        </template>
        <el-empty v-if="!day" description="选择左侧日期" />
        <el-tabs v-else v-model="activeTab" tab-position="left" class="side-tabs">
          <el-tab-pane
            v-for="sec in day.sections"
            :key="sec.key"
            :name="sec.key"
            :label="`${sec.title} (${sec.count})`"
          >
            <el-empty
              v-if="!sec.hits.length"
              description="无命中"
              :image-size="50"
            />
            <el-table v-else :data="sec.hits" size="small" stripe>
              <el-table-column label="代码" width="76" prop="code" />
              <el-table-column label="名称" width="90" prop="name" />
              <el-table-column label="评级" width="70">
                <template #default="{ row }">
                  <el-tag :type="GRADE_TYPE[row.grade]" effect="dark" size="small">
                    {{ row.grade }}
                  </el-tag>
                </template>
              </el-table-column>
              <el-table-column label="现价" width="72" align="right">
                <template #default="{ row }">{{ row.close?.toFixed(2) }}</template>
              </el-table-column>
              <el-table-column label="当日%" width="72" align="right">
                <template #default="{ row }">
                  <span :class="chgClass(row.chg)">{{
                    row.chg > 0 ? '+' : ''
                  }}{{ row.chg?.toFixed(2) }}</span>
                </template>
              </el-table-column>
              <el-table-column label="盘口标签" min-width="220">
                <template #default="{ row }">
                  <el-tag
                    v-for="f in row.flags"
                    :key="f.text"
                    :type="FLAG_TYPE[f.type]"
                    size="small"
                    class="flag-tag"
                    :effect="f.type === 'bad' ? 'dark' : 'plain'"
                  >
                    {{ f.text }}
                  </el-tag>
                </template>
              </el-table-column>
            </el-table>
          </el-tab-pane>
        </el-tabs>
      </el-card>
    </div>
  </div>
</template>

<style scoped>
.hist-page {
  padding: 16px 20px;
}
@media (max-width: 760px) { .layout { flex-direction: column; } .side { width: 100% !important; } .main { width: 100%; } }
.layout {
  display: flex;
  gap: 14px;
  align-items: flex-start;
}
.side {
  width: 240px;
  flex-shrink: 0;
}
.main {
  flex: 1;
  min-width: 0;
}
.hd {
  font-weight: 600;
}
.dim {
  margin-left: 8px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.day-item {
  padding: 8px 10px;
  border-radius: 8px;
  cursor: pointer;
  margin-bottom: 4px;
}
.day-item:hover {
  background: var(--el-fill-color-light);
}
.day-item.active {
  background: var(--el-color-primary-light-9);
}
.day-date {
  display: flex;
  align-items: center;
  gap: 6px;
  font-weight: 600;
  font-size: 14px;
}
.day-sum {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  margin-top: 2px;
}
.flag-tag {
  margin: 2px 4px 2px 0;
}
.up {
  color: #ef4444;
  font-weight: 600;
}
.down {
  color: #22c55e;
  font-weight: 600;
}
</style>

<style src="../_shared/side-tabs.css"></style>
