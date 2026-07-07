<script lang="ts" setup>
import { WorkbenchHeader } from '@vben/common-ui';
import { preferences } from '@vben/preferences';
import { useUserStore } from '@vben/stores';

const userStore = useUserStore();

const highlights = [
  ['平台能力', '登录、权限、路由、布局、请求、i18n 已保留在原体系中。'],
  ['扩展方式', '从 dashboard 或 example 模块复制页面与路由即可继续开发。'],
  ['模板边界', '业务数据已剥离，当前仓库只保留可复用后台骨架。'],
];
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
        这里展示精简后的后台模板首页，保留原始 Vben 布局与交互体系。
      </template>
    </WorkbenchHeader>

    <div class="mt-5 grid grid-cols-1 gap-4 xl:grid-cols-3">
      <el-card
        v-for="[title, desc] in highlights"
        :key="title"
        shadow="never"
      >
        <h3 class="text-base font-semibold">{{ title }}</h3>
        <p class="mt-3 text-sm leading-6 text-muted-foreground">{{ desc }}</p>
      </el-card>
    </div>
  </div>
</template>
