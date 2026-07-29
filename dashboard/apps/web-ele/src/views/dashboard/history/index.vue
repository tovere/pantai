<script lang="ts" setup>
import type { HistoryDay, HistoryItem } from '#/api/watch';

import { onMounted, ref } from 'vue';

import { getHistoryDayApi, getHistoryListApi } from '#/api/watch';

const list = ref<HistoryItem[]>([]);
const day = ref<HistoryDay | null>(null);
const activeDate = ref('');
const activeTab = ref('');

const GRADE_TYPE: Record<string, string> = {
  A: 'success',
  B: 'primary',
  C: 'info',
  D: 'danger',
};
const FLAG_TYPE: Record<string, string> = {
  good: 'success',
  warn: 'warning',
  bad: 'danger',
};

function chgClass(v?: number) {
  return v == null ? '' : v > 0 ? 'up' : v < 0 ? 'down' : '';
}

async function openDay(date: string) {
  activeDate.value = date;
  day.value = await getHistoryDayApi(date);
  const first = day.value?.sections.find((s) => s.count > 0);
  activeTab.value = first?.key ?? day.value?.sections[0]?.key ?? '';
}

onMounted(async () => {
  list.value = await getHistoryListApi();
  if (list.value.length) await openDay(list.value[0]!.date);
});
</script>

<template>
  <div class="hist-page">
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
