<script lang="ts" setup>
import type { EChartsOption } from 'echarts';

import type { WatchBar } from '#/api/watch';

import { onMounted, ref } from 'vue';

import { EchartsUI, type EchartsUIType, useEcharts } from '@vben/plugins/echarts';

const props = defineProps<{
  bars: WatchBar[];
  levels?: Record<string, null | number>;
}>();

const chartRef = ref<EchartsUIType>();
const { renderEcharts } = useEcharts(chartRef);

function ma(n: number, closes: number[]): (number | string)[] {
  return closes.map((_, i) => {
    if (i < n - 1) return '-';
    const sum = closes.slice(i - n + 1, i + 1).reduce((a, b) => a + b, 0);
    return +(sum / n).toFixed(2);
  });
}

onMounted(() => {
  const bars = props.bars || [];
  const dates = bars.map((b) => b[0].slice(5)); // MM-DD
  // ECharts 蜡烛图数据: [开, 收, 低, 高]
  const kdata = bars.map((b) => [b[1], b[2], b[4], b[3]]);
  const closes = bars.map((b) => b[2]);
  const vols = bars.map((b, i) => ({
    value: b[5],
    itemStyle: { color: b[2] >= b[1] ? '#ef4444' : '#22c55e' },
  }));

  const markLineData = Object.entries(props.levels || {})
    .filter(([, v]) => v != null)
    .map(([name, v]) => ({
      yAxis: v as number,
      name,
      label: {
        formatter: `${name} ${v}`,
        position: 'insideEndTop' as const,
        fontSize: 10,
      },
      lineStyle: {
        type: 'dashed' as const,
        color: name.includes('止损') || name.includes('三买') ? '#f59e0b' : '#3b82f6',
      },
    }));

  const option: EChartsOption = {
    animation: false,
    grid: [
      { left: 48, right: 16, top: 12, height: '62%' },
      { left: 48, right: 16, top: '76%', height: '16%' },
    ],
    tooltip: { trigger: 'axis', axisPointer: { type: 'cross' } },
    axisPointer: { link: [{ xAxisIndex: 'all' }] },
    xAxis: [
      {
        type: 'category',
        data: dates,
        boundaryGap: true,
        axisLabel: { fontSize: 10 },
        gridIndex: 0,
      },
      {
        type: 'category',
        data: dates,
        gridIndex: 1,
        axisLabel: { show: false },
        axisTick: { show: false },
      },
    ],
    yAxis: [
      { scale: true, gridIndex: 0, axisLabel: { fontSize: 10 }, splitNumber: 4 },
      { gridIndex: 1, axisLabel: { show: false }, splitLine: { show: false } },
    ],
    series: [
      {
        name: 'K线',
        type: 'candlestick',
        data: kdata,
        xAxisIndex: 0,
        yAxisIndex: 0,
        itemStyle: {
          color: '#ef4444', // 阳线 红
          color0: '#22c55e', // 阴线 绿
          borderColor: '#ef4444',
          borderColor0: '#22c55e',
        },
        markLine: {
          symbol: 'none',
          data: markLineData,
        },
      },
      {
        name: 'MA5',
        type: 'line',
        data: ma(5, closes),
        smooth: true,
        showSymbol: false,
        lineStyle: { width: 1, color: '#f59e0b' },
        xAxisIndex: 0,
        yAxisIndex: 0,
      },
      {
        name: 'MA10',
        type: 'line',
        data: ma(10, closes),
        smooth: true,
        showSymbol: false,
        lineStyle: { width: 1, color: '#3b82f6' },
        xAxisIndex: 0,
        yAxisIndex: 0,
      },
      {
        name: 'MA20',
        type: 'line',
        data: ma(20, closes),
        smooth: true,
        showSymbol: false,
        lineStyle: { width: 1, color: '#a855f7' },
        xAxisIndex: 0,
        yAxisIndex: 0,
      },
      {
        name: '成交量',
        type: 'bar',
        data: vols,
        xAxisIndex: 1,
        yAxisIndex: 1,
      },
    ],
  };
  renderEcharts(option);
});
</script>

<template>
  <EchartsUI ref="chartRef" height="340px" />
</template>
