<template>
  <div class="info-page">
    <div class="info-card">
      <a-tabs
        type="rounded"
        size="small"
        :active-key="activeTab"
        @change="onTabChange"
      >
        <a-tab-pane key="system" title="系统" />
        <a-tab-pane key="configs" title="配置" />
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
  if (path.includes('/configs')) return 'configs'
  return 'system'
})

const onTabChange = (key: string) => {
  router.push(key === 'configs' ? '/info/configs' : '/info/system')
}
</script>

<style scoped>
.info-page {
  padding: 12px;
}

.info-card {
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

