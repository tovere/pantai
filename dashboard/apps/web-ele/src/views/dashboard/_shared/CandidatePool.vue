<script setup lang="ts">
import type { WatchData, WatchFlag, WatchHit } from '#/api/watch';
import { computed, ref } from 'vue';
import HitTable from '../watch/HitTable.vue';

const props = defineProps<{ data: WatchData }>();
const query = ref('');
const grade = ref('');
const strategy = ref('');
const riskOnly = ref(false);
const selected = ref<WatchHit>();
const rows = computed(() => {
  const map = new Map<string, { hit: WatchHit; titles: string[]; keys: string[] }>();
  for (const section of props.data.sections) {
    for (const hit of section.hits) {
      const item = map.get(hit.code);
      if (item) {
        item.titles.push(section.title);
        item.keys.push(section.key);
        if (hit.grade < item.hit.grade) item.hit = hit;
      } else map.set(hit.code, { hit, titles: [section.title], keys: [section.key] });
    }
  }
  return [...map.values()].sort((a, b) => a.hit.grade.localeCompare(b.hit.grade) || b.keys.length - a.keys.length);
});
const filtered = computed(() => rows.value.filter(({ hit, keys }) =>
  (!query.value || (hit.code + hit.name).includes(query.value.trim())) &&
  (!grade.value || hit.grade === grade.value) &&
  (!strategy.value || keys.includes(strategy.value)) &&
  (!riskOnly.value || hit.flags.some((f) => f.type !== 'good'))));
const risky = computed(() => rows.value.filter(({ hit }) => hit.flags.some((f) => f.type !== 'good')).length);
</script>

<template>
  <el-card shadow="never" class="pool">
    <template #header><strong>综合候选池</strong><span class="note">按代码去重 · 多策略评级取最高，详情保留各策略结果</span></template>
    <div class="toolbar">
      <el-button @click="grade = ''; riskOnly = false">去重候选 {{ rows.length }}</el-button>
      <el-button @click="grade = 'A'; riskOnly = false">A 级候选 {{ rows.filter(r => r.hit.grade === 'A').length }}</el-button>
      <el-button @click="grade = ''; riskOnly = true">风险标记 {{ risky }}</el-button>
      <el-input v-model="query" placeholder="代码 / 名称" clearable style="width: 180px" />
      <el-select v-model="grade" clearable placeholder="全部评级" style="width: 130px">
        <el-option v-for="g in ['A','B','C','D']" :key="g" :label="g + ' 级'" :value="g" />
      </el-select>
      <el-select v-model="strategy" clearable placeholder="全部策略" style="width: 220px">
        <el-option v-for="s in data.sections" :key="s.key" :label="s.title" :value="s.key" />
      </el-select>
      <el-checkbox v-model="riskOnly">仅风险标记</el-checkbox>
    </div>
    <el-table :data="filtered" row-key="hit.code" max-height="420" @row-click="(row) => selected = row.hit">
      <el-table-column prop="hit.code" label="代码" width="90" fixed />
      <el-table-column prop="hit.name" label="名称" width="110" fixed />
      <el-table-column prop="hit.grade" label="最高评级" width="90" sortable />
      <el-table-column prop="hit.close" label="现价" width="90" />
      <el-table-column prop="hit.chg" label="涨跌幅 (%)" width="110" sortable />
      <el-table-column label="命中策略" min-width="240"><template #default="{ row }">{{ row.titles.join(' / ') }}</template></el-table-column>
      <el-table-column label="风险因素" min-width="220"><template #default="{ row }">{{ row.hit.flags.filter((f: WatchFlag) => f.type !== 'good').map((f: WatchFlag) => f.text).join(' / ') || '无已标记风险' }}</template></el-table-column>
    </el-table>
    <el-drawer :model-value="!!selected" :title="selected?.name + ' · 策略详情'" size="85%" @close="selected = undefined">
      <template v-if="selected">
        <section v-for="s in data.sections.filter(s => s.hits.some(h => h.code === selected?.code))" :key="s.key">
          <h3>{{ s.title }}</h3>
          <p>{{ s.conclusionNote }} {{ s.btNote }}</p>
          <HitTable :section="{ ...s, hits: s.hits.filter(h => h.code === selected?.code) }" />
        </section>
      </template>
    </el-drawer>
  </el-card>
</template>

<style scoped>
.pool { margin-top: 16px; }
.toolbar { display: flex; flex-wrap: wrap; gap: 10px; margin-bottom: 14px; }
.note { margin-left: 12px; color: var(--el-text-color-secondary); font-size: 12px; }
</style>
