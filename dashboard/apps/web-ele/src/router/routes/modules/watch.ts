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
      {
        name: 'WatchReadme',
        path: '/watch/readme',
        component: () => import('#/views/dashboard/readme/index.vue'),
        meta: {
          icon: 'lucide:book-open-text',
          title: '策略说明',
        },
      },
    ],
  },
  {
    meta: {
      icon: 'lucide:timer',
      order: -1,
      title: '30F',
    },
    name: 'Min30',
    path: '/min',
    children: [
      {
        name: 'Min30Board',
        path: '/min/board',
        component: () => import('#/views/dashboard/min-watch/index.vue'),
        meta: {
          icon: 'lucide:line-chart',
          title: '30F盯盘',
        },
      },
      {
        name: 'Min30Data',
        path: '/min/data',
        component: () => import('#/views/dashboard/min-data/index.vue'),
        meta: {
          icon: 'lucide:database',
          title: '30F数据',
        },
      },
    ],
  },
];

export default routes;
