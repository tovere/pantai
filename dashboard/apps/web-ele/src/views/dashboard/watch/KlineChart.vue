<script lang="ts" setup>
import type { WatchBar } from '#/api/watch';

import { onMounted, ref } from 'vue';

import { EchartsUI, type EchartsUIType, useEcharts } from '@vben/plugins/echarts';

// 从 renderEcharts 的参数反推 option 类型, 避免直接 import 'echarts'(web-ele 未直依赖)
type EChartsOption = Parameters<ReturnType<typeof useEcharts>['renderEcharts']>[0];

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
  const vols = bars.map((b) => ({
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
      { left: 48, right: 16, top: 12, height: '58%' },
      { left: 48, right: 16, top: '72%', height: '14%' },
    ],
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'cross' },
      confine: true, // 锁在图表框内, 避免靠右/靠上时被容器边界裁掉
    },
    axisPointer: { link: [{ xAxisIndex: 'all' }] },
    // 缩放: 滚轮/拖拽(inside) + 底部滑块(slider); K线与成交量 x 轴联动
    dataZoom: [
      { type: 'inside', xAxisIndex: [0, 1], start: 0, end: 100 },
      {
        type: 'slider',
        xAxisIndex: [0, 1],
        bottom: 6,
        height: 16,
        start: 0,
        end: 100,
        brushSelect: false,
      },
    ],
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
  <EchartsUI ref="chartRef" height="370px" />
</template>
