<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue';
import { requestClient } from '#/api/request';
interface Prediction { code: string; height: number; close: number; probability: null | number; samples: number; baseline: null | number; date: string; continued: null | boolean }
interface Result { poolItems?: {ticker: string; name: string; continue_day_cnt: number; limit_up_reason: string; seal_money: number}[]; currentSectors?: {name: string; members: number; limitCount: number; limitPct: number; maxHeight: number}[]; stale?: boolean; poolDate?: string; status?: {running: boolean; error: string | null}; themes?: {theme: string; count: number; maxHeight: number}[]; date?: string; warnings: string[]; items: Prediction[]; calibration: {range: string; samples: number; predicted: number; actual: number}[]; history: Prediction[]; brier?: number }
const data = ref<Result>();
const error = ref('');
let stopped = false;
let timer: ReturnType<typeof setTimeout>;
async function refresh() {
  try { data.value = await requestClient.get<Result>('/limit/summary'); error.value = ''; }
  catch { error.value = '加载失败，请检查后端'; }
  finally { if (!stopped) timer = setTimeout(refresh, 15000); }
}
async function run() { try { await requestClient.post('/limit/run'); } catch { error.value = '提交失败'; } }
onMounted(refresh);
onUnmounted(() => { stopped = true; clearTimeout(timer); });
</script>
<template>
  <div style="padding: 20px">
    <h2>主板连板概率 · 历史统计基线</h2>
    <el-button :loading="data?.status?.running" @click="run">更新本地分析</el-button>
    <el-alert v-if="error" :title="error" type="error" />
    <template v-if="data">
      <el-alert v-if="data.status?.error" :title="data.status.error" type="error" />
      <p>数据日期 {{ data.date || '—' }} · Brier {{ data.brier ?? '—' }}（越低越好）</p>
      <p>候选以同日真实涨停池为准；概率是同连板高度历史组统计，同组相同，不是个股独立预测。</p>
      <el-table :data="data.items">
        <el-table-column prop="name" label="名称" min-width="100" /><el-table-column label="封板时间"><template #default="{row}">{{ row.sealTime || '数据源未提供' }}</template></el-table-column><el-table-column label="封单金额"><template #default="{row}">{{ row.sealMoney == null ? '数据源未提供' : (row.sealMoney / 10000).toFixed(0) + '万' }}</template></el-table-column><el-table-column label="涨停原因" min-width="200"><template #default="{row}">{{ row.reason || '数据源未提供' }}</template></el-table-column>
        <el-table-column prop="code" label="代码" /><el-table-column prop="height" label="当前板数" /><el-table-column prop="close" label="收盘价" />
        <el-table-column label="同板数次日连板概率"><template #default="{row}">{{ row.probability == null ? '样本不足' : row.probability + '%' }}</template></el-table-column>
        <el-table-column prop="samples" label="历史同组样本" /><el-table-column prop="baseline" label="全样本基准(%，各股共用)" />
      </el-table>
      <h3>当日涨停池 {{ data.poolDate }}（独立于历史概率日期）</h3>
      <el-table :data="data.poolItems || []" max-height="400"><el-table-column prop="ticker" label="代码" /><el-table-column prop="name" label="名称" /><el-table-column prop="continue_day_cnt" label="板数" /><el-table-column prop="seal_money" label="封单金额" /><el-table-column prop="limit_up_reason" label="原因" min-width="240" /></el-table>
      <h3>当日正式行业成分聚合（不回填历史）</h3>
      <el-table :data="data.currentSectors || []"><el-table-column prop="name" label="行业" /><el-table-column prop="members" label="成分数量" /><el-table-column prop="limitCount" label="涨停数量" /><el-table-column prop="limitPct" label="涨停占比(%)" /><el-table-column prop="maxHeight" label="最高板" /></el-table>
      <h3>涨停原因聚合（非正式板块成分）</h3>
      <el-table :data="data.themes || []"><el-table-column prop="theme" label="题材文本" /><el-table-column prop="count" label="涨停数量" /><el-table-column prop="maxHeight" label="最高板" /></el-table>
      <h3>按时间向前预测的概率校准</h3>
      <el-table :data="data.calibration"><el-table-column prop="range" label="概率分组" /><el-table-column prop="samples" label="样本数" /><el-table-column prop="predicted" label="平均预测(%)" /><el-table-column prop="actual" label="实际晋级(%)" /></el-table>
    </template>
  </div>
</template>
