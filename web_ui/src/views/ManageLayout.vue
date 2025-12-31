<template>
  <div class="manage-page">
    <div class="manage-card">
      <a-tabs type="rounded" size="small" :active-key="activeTab" @change="onTabChange">
        <a-tab-pane key="subscriptions" title="订阅管理" />
        <a-tab-pane key="topics" title="专题" />
      </a-tabs>
    </div>

    <router-view />
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'

const route = useRoute()
const router = useRouter()

const activeTab = computed(() => {
  const path = route.path || ''
  if (path.includes('/topics')) return 'topics'
  return 'subscriptions'
})

const onTabChange = (key: string) => {
  router.push(key === 'topics' ? '/manage/topics' : '/manage/subscriptions')
}
</script>

<style scoped>
.manage-page {
  padding: 12px;
}

.manage-card {
  display: flex;
  align-items: center;
  padding: 10px 12px;
  border-radius: var(--app-radius-md);
  border: 1px solid var(--color-border);
  background: color-mix(in srgb, var(--color-bg-2) 84%, transparent);
  box-shadow: 0 10px 28px rgba(0, 0, 0, 0.06);
  margin-bottom: 12px;
}
</style>

