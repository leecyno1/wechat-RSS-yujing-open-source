<template>
  <a-layout-header>
    <a-menu
      mode="horizontal"
      :selected-keys="selectedKeys"
      @menu-item-click="handleMenuClick"
    >
      <a-menu-item key="/">
        <template #icon>
          <icon-home />
        </template>
        订阅管理
      </a-menu-item>
      <a-menu-item key="/message-tasks">
        <template #icon>
          <icon-notification />
        </template>
        消息任务
      </a-menu-item>
      <a-menu-item key="/configs">
        <template #icon>
          <icon-settings />
        </template>
        配置管理
      </a-menu-item>
      <a-menu-item key="/sys-info">
        <template #icon>
          <icon-info-circle />
        </template>
        系统信息
      </a-menu-item>
    </a-menu>
  </a-layout-header>
</template>

<script setup lang="ts">
import { ref, watchEffect } from 'vue'
import { useRouter, useRoute } from 'vue-router'

const router = useRouter()
const route = useRoute()
const selectedKeys = ref<string[]>(['/'])

watchEffect(() => {
  selectedKeys.value = [route.path]
})

const handleMenuClick = (key: string) => {
  router.push(key)
}
</script>