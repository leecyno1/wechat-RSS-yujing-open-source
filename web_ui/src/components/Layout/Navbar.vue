<template>
  <a-menu
    class="app-nav"
    mode="horizontal"
    :selected-keys="selectedKeys"
    :ellipsis="false"
    @menu-item-click="handleMenuClick"
  >
    <a-menu-item key="/channels">
      <template #icon>
        <icon-compass />
      </template>
      频道
    </a-menu-item>
    <a-menu-item key="/favorites">
      <template #icon>
        <icon-star />
      </template>
      收藏
    </a-menu-item>

    <a-sub-menu key="manage">
      <template #icon>
        <icon-home />
      </template>
      <template #title>管理</template>
      <a-menu-item key="/">
        <template #icon><icon-file /></template>
        订阅管理
      </a-menu-item>
      <a-menu-item key="/tags">
        <template #icon><icon-tag /></template>
        专题
      </a-menu-item>
    </a-sub-menu>

    <a-menu-item key="/message-tasks">
      <template #icon>
        <icon-notification />
      </template>
      任务
    </a-menu-item>

    <a-menu-item key="/export/records">
      <template #icon>
        <icon-export />
      </template>
      导出
    </a-menu-item>

    <a-sub-menu key="info">
      <template #icon><icon-info-circle /></template>
      <template #title>信息</template>
      <a-menu-item key="/sys-info">
        <template #icon><icon-info-circle /></template>
        系统
      </a-menu-item>
      <a-menu-item key="/configs">
        <template #icon><icon-settings /></template>
        配置
      </a-menu-item>
    </a-sub-menu>
  </a-menu>
</template>

<script setup lang="ts">
import { ref, watchEffect } from 'vue'
import { useRouter, useRoute } from 'vue-router'

const router = useRouter()
const route = useRoute()
const selectedKeys = ref<string[]>(['/'])

watchEffect(() => {
  const path = route.path || '/'
  const normalized =
    path.startsWith('/channels') ? '/channels' :
    path.startsWith('/favorites') ? '/favorites' :
    path.startsWith('/tags') ? '/tags' :
    path.startsWith('/message-tasks') ? '/message-tasks' :
    path.startsWith('/export') ? '/export/records' :
    path.startsWith('/configs') ? '/configs' :
    path.startsWith('/sys-info') ? '/sys-info' :
    '/'
  selectedKeys.value = [normalized]
})

const handleMenuClick = (key: string) => {
  router.push(key)
}
</script>

<style scoped>
.app-nav {
  width: fit-content;
  max-width: 100%;
  background: transparent;
  border-bottom: none;
}

.app-nav :deep(.arco-menu-inner) {
  padding: 0;
}

.app-nav :deep(.arco-menu-item),
.app-nav :deep(.arco-menu-pop-header) {
  height: 40px;
  line-height: 40px;
  border-radius: 12px;
  margin: 0 4px;
}
</style>
