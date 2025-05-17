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
        文章列表
      </a-menu-item>
      <a-menu-item key="/wechat/mp">
        <template #icon>
          <icon-wechat />
        </template>
        公众号管理
      </a-menu-item>
    </a-menu>
  </a-layout-header>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'

const router = useRouter()
const selectedKeys = ref<string[]>(['/'])

const handleMenuClick = (key: string) => {
  router.push(key)
}
</script>