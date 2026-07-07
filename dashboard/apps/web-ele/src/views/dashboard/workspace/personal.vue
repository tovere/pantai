<script lang="ts" setup>
import { useRouter } from 'vue-router';

import { WorkbenchHeader } from '@vben/common-ui';
import { preferences } from '@vben/preferences';
import { useUserStore } from '@vben/stores';

const router = useRouter();
const userStore = useUserStore();

const quickActions = [
  {
    desc: '查看精简后的后台首页结构。',
    label: '工作台总览',
    path: '/workspace',
  },
  {
    desc: '查看模板示例模块，作为新页面开发参考。',
    label: '模板示例',
    path: '/example/index',
  },
  {
    desc: '查看系统保留的兜底页与权限页。',
    label: '敬请期待页',
    path: '/coming-soon',
  },
];

const cards = [
  {
    desc: '保留原登录态、权限、路由守卫、标签栏和顶部 widgets。',
    title: '保留的能力',
  },
  {
    desc: '删除 `perf` 业务模块和业务数据，只保留可复用骨架。',
    title: '当前状态',
  },
  {
    desc: '新增业务时优先复制 example 模块，再补 API 和菜单。',
    title: '扩展建议',
  },
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
        欢迎回来，{{ userStore.userInfo?.realName }}
      </template>
      <template #description>
        个人工作台现在作为模板首页入口，帮助你快速进入可复用的后台骨架。
      </template>
    </WorkbenchHeader>

    <div class="mt-5 grid grid-cols-1 gap-4 xl:grid-cols-3">
      <el-card v-for="card in cards" :key="card.title" shadow="never">
        <h3 class="text-base font-semibold">{{ card.title }}</h3>
        <p class="mt-3 text-sm leading-6 text-muted-foreground">{{ card.desc }}</p>
      </el-card>
    </div>

    <div class="mt-5 rounded-md border p-4">
      <h3 class="text-base font-semibold">快捷操作</h3>
      <div class="mt-3 grid grid-cols-1 gap-3 md:grid-cols-3">
        <button
          v-for="action in quickActions"
          :key="action.path"
          class="rounded-md border bg-background p-3 text-left transition-all hover:border-primary hover:shadow-sm"
          type="button"
          @click="goTo(action.path)"
        >
          <p class="text-sm font-semibold">{{ action.label }}</p>
          <p class="mt-1 text-xs text-muted-foreground">{{ action.desc }}</p>
        </button>
      </div>
    </div>
  </div>
</template>
