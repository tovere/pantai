<script setup lang="ts">
import { onMounted, ref, watch } from 'vue';
import { EchartsUI, type EchartsUIType, useEcharts } from '@vben/plugins/echarts';
import type { PaperAccount } from '#/api/paper';
const props = defineProps<{ accounts: Record<string, PaperAccount> }>();
const chart = ref<EchartsUIType>();
const { renderEcharts } = useEcharts(chart);
const labels: Record<string, string> = { agent: 'Agent', rules: '固定规则', benchmark: '20% ETF + 80%现金' };
function paint() {
  const dates = [...new Set(Object.values(props.accounts).flatMap(a => a.curve.map(p => p.date)))].sort();
  renderEcharts({
    tooltip: { trigger: 'axis' }, legend: { top: 0 },
    grid: { left: 65, right: 25, top: 40, bottom: 35 },
    xAxis: { type: 'category', data: dates },
    yAxis: { type: 'value', scale: true, name: '资产（元）' },
    series: Object.entries(props.accounts).map(([key, a]) => ({
      name: labels[key], type: 'line' as const, connectNulls: false,
      data: dates.map(d => a.curve.find(p => p.date === d)?.equity ?? null),
    })),
  });
}
onMounted(paint);
watch(() => props.accounts, paint, { deep: true });
</script>
<template><EchartsUI ref="chart" style="height: 320px" /></template>
