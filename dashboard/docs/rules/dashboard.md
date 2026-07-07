---
description: Dashboard 仪表盘/数据统计页面开发规范
globs:
alwaysApply: false
---

# Dashboard 仪表盘开发规范

本规范适用于数据统计、可视化展示类的仪表盘页面开发。

## 功能规范模板

```markdown
# 功能规范：[仪表盘名称]

## 1. 功能概述
展示业务核心数据指标，提供可视化图表和数据概览。

## 2. 页面布局
- 顶部：统计卡片区域（4个核心指标）
- 中部：图表区域（折线图、柱状图、饼图等）
- 底部：数据列表/排行榜

## 3. 统计卡片
| 指标名称 | 字段名 | 图标 | 单位 | 说明 |
|----------|--------|------|------|------|
| 用户量 | userCount | lucide:users | 人 | 累计注册用户 |
| 访问量 | visitCount | lucide:eye | 次 | 今日访问量 |
| 订单量 | orderCount | lucide:shopping-cart | 单 | 今日订单数 |
| 收入 | revenue | lucide:dollar-sign | 元 | 今日收入 |

## 4. 图表配置
- 折线图：趋势数据（按天/周/月）
- 柱状图：对比数据
- 饼图：占比数据
- 数据表格：详细数据列表

## 5. 接口定义
| 接口名称 | 方法 | 路径 | 说明 |
|----------|------|------|------|
| 获取统计数据 | GET | /api/dashboard/stats | 获取核心指标 |
| 获取趋势数据 | GET | /api/dashboard/trends | 获取图表数据 |
| 获取排行数据 | GET | /api/dashboard/ranking | 获取排行榜 |
```

## 文件生成规范

### 1. API 接口文件

位置：`apps/web-ele/src/api/dashboard.ts`

```typescript
import { requestClient } from '#/api/request';

// 统计卡片数据
export interface DashboardStats {
  userCount: number;
  userGrowth: number;
  visitCount: number;
  visitGrowth: number;
  orderCount: number;
  orderGrowth: number;
  revenue: number;
  revenueGrowth: number;
}

// 趋势数据
export interface TrendItem {
  date: string;
  value: number;
  compare?: number;
}

// 排行数据
export interface RankingItem {
  rank: number;
  name: string;
  value: number;
  percentage?: number;
}

// 获取统计数据
export async function getDashboardStatsApi() {
  return requestClient.get<DashboardStats>('/dashboard/stats');
}

// 获取趋势数据
export async function getDashboardTrendsApi(params: { type: string; range: string }) {
  return requestClient.get<TrendItem[]>('/dashboard/trends', { params });
}

// 获取排行数据
export async function getDashboardRankingApi(params: { type: string; limit: number }) {
  return requestClient.get<RankingItem[]>('/dashboard/ranking', { params });
}
```

### 2. 仪表盘页面组件

位置：`apps/web-ele/src/views/dashboard/[name]/index.vue`

```vue
<script lang="ts" setup>
import type { AnalysisOverviewItem } from '@vben/common-ui';
import type { TabOption } from '@vben/types';

import { ref, onMounted } from 'vue';
import {
  AnalysisChartCard,
  AnalysisChartsTabs,
  AnalysisOverview,
} from '@vben/common-ui';
import {
  SvgBellIcon,
  SvgCakeIcon,
  SvgCardIcon,
  SvgDownloadIcon,
} from '@vben/icons';
import { ElMessage } from 'element-plus';

import { getDashboardStatsApi, getDashboardTrendsApi } from '#/api/dashboard';
import TrendChart from './TrendChart.vue';
import PieChart from './PieChart.vue';
import BarChart from './BarChart.vue';
import RankingTable from './RankingTable.vue';

// 统计卡片数据
const overviewItems = ref<AnalysisOverviewItem[]>([
  {
    icon: SvgCardIcon,
    title: '用户量',
    totalTitle: '总用户量',
    totalValue: 0,
    value: 0,
  },
  {
    icon: SvgCakeIcon,
    title: '访问量',
    totalTitle: '总访问量',
    totalValue: 0,
    value: 0,
  },
  {
    icon: SvgDownloadIcon,
    title: '订单量',
    totalTitle: '总订单量',
    totalValue: 0,
    value: 0,
  },
  {
    icon: SvgBellIcon,
    title: '收入',
    totalTitle: '总收入',
    totalValue: 0,
    value: 0,
  },
]);

// 图表 Tab 配置
const chartTabs: TabOption[] = [
  { label: '趋势图', value: 'trend' },
  { label: '对比图', value: 'compare' },
];

// 加载统计数据
async function loadStats() {
  try {
    const res = await getDashboardStatsApi();
    overviewItems.value = [
      {
        icon: SvgCardIcon,
        title: '用户量',
        totalTitle: '总用户量',
        totalValue: res.userCount,
        value: res.userGrowth,
      },
      // ... 更新其他卡片
    ];
  } catch (error) {
    ElMessage.error('加载统计数据失败');
  }
}

onMounted(() => {
  loadStats();
});
</script>

<template>
  <div class="p-5">
    <!-- 统计卡片 -->
    <AnalysisOverview :items="overviewItems" />

    <!-- 图表区域 -->
    <AnalysisChartsTabs :tabs="chartTabs" class="mt-5">
      <template #trend>
        <TrendChart />
      </template>
      <template #compare>
        <BarChart />
      </template>
    </AnalysisChartsTabs>

    <!-- 底部图表 -->
    <div class="mt-5 w-full md:flex">
      <AnalysisChartCard class="mt-5 md:mt-0 md:mr-4 md:w-1/2" title="分布统计">
        <PieChart />
      </AnalysisChartCard>
      <AnalysisChartCard class="mt-5 md:mt-0 md:w-1/2" title="排行榜">
        <RankingTable />
      </AnalysisChartCard>
    </div>
  </div>
</template>
```

### 3. 图表组件（使用 ECharts）

位置：`apps/web-ele/src/views/dashboard/[name]/TrendChart.vue`

```vue
<script lang="ts" setup>
import { ref, onMounted, onUnmounted } from 'vue';
import * as echarts from 'echarts';
import type { EChartsOption } from 'echarts';

import { getDashboardTrendsApi } from '#/api/dashboard';

const chartRef = ref<HTMLElement>();
let chartInstance: echarts.ECharts | null = null;

async function initChart() {
  if (!chartRef.value) return;

  chartInstance = echarts.init(chartRef.value);

  // 获取数据
  const data = await getDashboardTrendsApi({ type: 'daily', range: '7d' });

  const option: EChartsOption = {
    tooltip: {
      trigger: 'axis',
    },
    legend: {
      data: ['访问量', '订单量'],
    },
    grid: {
      left: '3%',
      right: '4%',
      bottom: '3%',
      containLabel: true,
    },
    xAxis: {
      type: 'category',
      boundaryGap: false,
      data: data.map((item) => item.date),
    },
    yAxis: {
      type: 'value',
    },
    series: [
      {
        name: '访问量',
        type: 'line',
        smooth: true,
        data: data.map((item) => item.value),
        areaStyle: {
          opacity: 0.3,
        },
      },
    ],
  };

  chartInstance.setOption(option);
}

// 响应式调整
function handleResize() {
  chartInstance?.resize();
}

onMounted(() => {
  initChart();
  window.addEventListener('resize', handleResize);
});

onUnmounted(() => {
  window.removeEventListener('resize', handleResize);
  chartInstance?.dispose();
});
</script>

<template>
  <div ref="chartRef" class="h-80 w-full" />
</template>
```

### 4. Mock 数据文件

位置：`apps/web-ele/src/mock/dashboard.ts`

```typescript
// Mock 接口写法统一遵循：./common/mock-module.md
// Dashboard 场景补充：
// 1) stats / trends / ranking 接口返回统计结构
// 2) 可直接使用 responseSuccess({ ...stats })
// 3) 趋势数据建议提供按日/周/月维度参数
```

详细实现参考：`./common/mock-module.md`

## 常用图表配置

### 折线图（趋势）

```typescript
const lineChartOption: EChartsOption = {
  tooltip: { trigger: 'axis' },
  xAxis: { type: 'category', data: dates },
  yAxis: { type: 'value' },
  series: [{
    type: 'line',
    smooth: true,
    data: values,
    areaStyle: { opacity: 0.3 },
  }],
};
```

### 柱状图（对比）

```typescript
const barChartOption: EChartsOption = {
  tooltip: { trigger: 'axis' },
  xAxis: { type: 'category', data: categories },
  yAxis: { type: 'value' },
  series: [{
    type: 'bar',
    data: values,
    itemStyle: { color: '#409EFF' },
  }],
};
```

### 饼图（占比）

```typescript
const pieChartOption: EChartsOption = {
  tooltip: { trigger: 'item' },
  legend: { orient: 'vertical', left: 'left' },
  series: [{
    type: 'pie',
    radius: '50%',
    data: [
      { value: 1048, name: '直接访问' },
      { value: 735, name: '邮件营销' },
      { value: 580, name: '联盟广告' },
    ],
  }],
};
```

## 注意事项

- 图表需要响应式处理，监听窗口 resize 事件
- 图表组件需要在 onUnmounted 中销毁实例
- 数据加载时显示 loading 状态
- 统计卡片使用 `@vben/common-ui` 的 `AnalysisOverview` 组件
- Mock 数据要真实感，数值要有合理范围

## 相关通用规范

- [Loading 状态规范](./common/loading.md)
- [错误处理规范](./common/error-handling.md)
- [防抖规范](./common/debounce.md)
- [Mock 模块规范](./common/mock-module.md)
