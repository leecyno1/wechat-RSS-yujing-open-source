<template>
  <nav class="nav" aria-label="Primary">
    <router-link class="nav-item" :class="{ active: activeKey === '/channels' }" to="/channels">频道</router-link>
    <router-link class="nav-item" :class="{ active: activeKey === '/favorites' }" to="/favorites">收藏</router-link>
    <router-link class="nav-item" :class="{ active: activeKey === '/manage' }" to="/manage/subscriptions">管理</router-link>
    <router-link class="nav-item" :class="{ active: activeKey === '/message-tasks' }" to="/message-tasks">任务</router-link>
    <router-link class="nav-item" :class="{ active: activeKey === '/export/records' }" to="/export/records">导出</router-link>
    <router-link class="nav-item" :class="{ active: activeKey === '/info' }" to="/info/system">信息</router-link>
  </nav>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'

const route = useRoute()
const activeKey = computed(() => {
  const path = route.path || '/'
  if (path.startsWith('/channels')) return '/channels'
  if (path.startsWith('/favorites')) return '/favorites'
  if (path.startsWith('/manage') || path === '/' || path.startsWith('/tags') || path.startsWith('/wechat/mp')) return '/manage'
  if (path.startsWith('/message-tasks')) return '/message-tasks'
  if (path.startsWith('/export')) return '/export/records'
  if (path.startsWith('/info') || path.startsWith('/sys-info') || path.startsWith('/configs')) return '/info'
  return '/manage'
})
</script>

<style scoped>
.nav {
  display: inline-flex;
  gap: 2px;
  padding: 4px;
  border-radius: 12px;
  border: 1px solid var(--color-border);
  background: color-mix(in srgb, var(--color-bg-2) 82%, transparent);
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.06);
}

.nav-item {
  display: inline-flex;
  align-items: center;
  height: 32px;
  padding: 0 12px;
  border-radius: 10px;
  color: var(--color-text-2);
  font-size: 13px;
  font-weight: 600;
  letter-spacing: -0.2px;
  text-decoration: none;
  user-select: none;
}

.nav-item:hover {
  background: var(--color-fill-2);
  color: var(--color-text-1);
  text-decoration: none;
}

.nav-item.active {
  background: color-mix(in srgb, var(--color-bg-1) 92%, transparent);
  color: var(--color-text-1);
  box-shadow: 0 1px 0 rgba(0, 0, 0, 0.04);
}
</style>
