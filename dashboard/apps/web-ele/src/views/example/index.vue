<script lang="ts" setup>
import { WorkbenchHeader } from '@vben/common-ui';
import { preferences } from '@vben/preferences';
import { useUserStore } from '@vben/stores';

const userStore = useUserStore();

const cards = [
  {
    desc: '复制现有路由模块，新增自己的菜单组和页面。',
    title: '扩展路由',
  },
  {
    desc: '沿用 `#/api` 和 `@vben/request` 的模式接入真实接口。',
    title: '接入 API',
  },
  {
    desc: '通过 preferences 与 locales 统一维护品牌和文案。',
    title: '模板化配置',
  },
];
</script>

<template>
  <div class="p-5">
    <WorkbenchHeader
      :avatar="userStore.userInfo?.avatar || preferences.app.defaultAvatar"
    >
      <template #title>
        模板示例页面
      </template>
      <template #description>
        这里是保留原 layout 体系下的最小业务模块示例，供新项目继续复制扩展。
      </template>
    </WorkbenchHeader>

    <div class="mt-5 grid grid-cols-1 gap-4 lg:grid-cols-3">
      <el-card v-for="card in cards" :key="card.title" shadow="never">
        <h3 class="text-base font-semibold">{{ card.title }}</h3>
        <p class="mt-3 text-sm leading-6 text-muted-foreground">
          {{ card.desc }}
        </p>
      </el-card>
    </div>
  </div>
</template>
