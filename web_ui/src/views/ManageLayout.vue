<template>
  <div class="manage-page">
    <div class="manage-card">
      <div class="manage-toolbar">
        <div class="manage-title">频道管理</div>
        <a-space size="small" class="manage-actions">
          <a-button size="small" type="primary" @click="goToCreateTopic">创建频道</a-button>
        </a-space>
      </div>
      <div class="manage-hint">频道用于聚合你已订阅的来源，便于首页快速筛选。</div>
    </div>

    <router-view />
  </div>
</template>

<script setup lang="ts">
import { useRouter } from 'vue-router'
const router = useRouter()

const goToCreateTopic = () => {
  router.push('/manage/topics/add')
}
</script>

<style scoped>
.manage-page {
  padding: 12px;
}

.manage-toolbar {
  width: 100%;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}

.manage-title {
  font-size: 14px;
  font-weight: 700;
  color: var(--color-text-1);
}

.manage-card {
  display: flex;
  flex-direction: column;
  align-items: stretch;
  padding: 8px 10px;
  border-radius: var(--app-radius-md);
  border: 1px solid var(--color-border);
  background: color-mix(in srgb, var(--color-bg-2) 84%, transparent);
  box-shadow: 0 10px 28px rgba(0, 0, 0, 0.06);
  margin-bottom: 12px;
}

.manage-actions {
  flex-wrap: wrap;
}

.manage-hint {
  margin-top: 8px;
  color: var(--color-text-3);
  font-size: 12px;
}
</style>
