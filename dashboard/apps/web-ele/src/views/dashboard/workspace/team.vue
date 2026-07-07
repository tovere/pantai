<script lang="ts" setup>
import { useRouter } from 'vue-router';

import { WorkbenchHeader } from '@vben/common-ui';
import { preferences } from '@vben/preferences';
import { useUserStore } from '@vben/stores';

const router = useRouter();
const userStore = useUserStore();

const quickActions = [
  { label: '工作台总览', path: '/workspace' },
  { label: '模板示例', path: '/example/index' },
  { label: '个人工作台', path: '/workspace/personal' },
];

const cards = [
  { title: '路由模块', value: 'dashboard / example' },
  { title: '运行模式', value: 'pnpm workspace + turbo' },
  { title: '保留能力', value: 'auth / layout / widgets / i18n' },
  { title: '当前目标', value: '去业务化脚手架' },
];

function goTo(path: string) {
  router.push(path);
}
</script>

<template>
  <div class="p-5">
    <WorkbenchHeader
      :avatar="userStore.userInfo?.avatar || preferences.app.defaultAvatar"
    >
      <template #title>
        团队工作台
      </template>
      <template #description>
        团队工作台现在作为模板级概览页，展示当前脚手架的结构和扩展方向。
      </template>
    </WorkbenchHeader>

    <div class="mt-5 grid grid-cols-2 gap-4 xl:grid-cols-4">
      <el-card v-for="card in cards" :key="card.title" shadow="never">
        <div class="text-xs text-muted-foreground">{{ card.title }}</div>
        <div class="mt-2 text-lg font-bold">{{ card.value }}</div>
      </el-card>
    </div>

    <div class="mt-5 rounded-md border p-4">
      <h3 class="text-base font-semibold">管理快捷入口</h3>
      <div class="mt-3 grid grid-cols-1 gap-3 md:grid-cols-4">
        <button
          v-for="action in quickActions"
          :key="action.path"
          class="rounded-md border bg-background p-3 text-left transition-all hover:border-primary hover:shadow-sm"
          type="button"
          @click="goTo(action.path)"
        >
          <p class="text-sm font-semibold">{{ action.label }}</p>
          <p class="mt-1 text-xs text-muted-foreground">进入{{ action.label }}页面</p>
        </button>
      </div>
    </div>
  </div>
</template>
