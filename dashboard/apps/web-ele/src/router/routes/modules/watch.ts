import type { RouteRecordRaw } from 'vue-router';

const routes: RouteRecordRaw[] = [
  {
    meta: {
      icon: 'lucide:line-chart',
      order: -2,
      title: '策略盯盘',
    },
    name: 'Watch',
    path: '/watch',
    children: [
      {
        name: 'WatchBoard',
        path: '/watch/board',
        component: () => import('#/views/dashboard/watch/index.vue'),
        meta: {
          affixTab: true,
          icon: 'lucide:line-chart',
          title: '盯盘台',
        },
      },
      {
        name: 'WatchMarket',
        path: '/watch/market',
        component: () => import('#/views/dashboard/market/index.vue'),
        meta: {
          icon: 'lucide:database',
          title: '大盘数据',
        },
      },
      {
        name: 'WatchHistory',
        path: '/watch/history',
        component: () => import('#/views/dashboard/history/index.vue'),
        meta: {
          icon: 'lucide:history',
          title: '历史命中',
        },
      },
    ],
  },
];

export default routes;
