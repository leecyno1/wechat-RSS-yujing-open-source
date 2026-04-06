<template>
  <nav class="nav" aria-label="Primary">
    <router-link class="nav-item" :class="{ active: activeKey === '/channels' }" to="/channels">首页</router-link>
    <router-link class="nav-item" :class="{ active: activeKey === '/favorites' }" to="/favorites">收藏</router-link>
    <router-link
      v-if="isAdmin"
      class="nav-item"
      :class="{ active: activeKey === '/info' }"
      to="/info/system"
    >
      信息
    </router-link>
  </nav>
</template>

<script setup lang="ts">
import { computed, onMounted, onBeforeUnmount, ref, watch } from 'vue'
import { useRoute } from 'vue-router'

const route = useRoute()
const role = ref('')

const syncRole = () => {
  role.value = String(localStorage.getItem('current_user_role') || '').trim().toLowerCase()
}

onMounted(() => {
  syncRole()
  window.addEventListener('storage', syncRole)
  window.addEventListener('user-role-updated', syncRole as EventListener)
})

onBeforeUnmount(() => {
  window.removeEventListener('storage', syncRole)
  window.removeEventListener('user-role-updated', syncRole as EventListener)
})

watch(
  () => route.fullPath,
  () => syncRole()
)

const isAdmin = computed(() => role.value === 'admin')

const activeKey = computed(() => {
  const path = route.path || '/'
  if (path.startsWith('/channels') || path === '/') return '/channels'
  if (path.startsWith('/favorites')) return '/favorites'
  if (path.startsWith('/info') || path.startsWith('/sys-info') || path.startsWith('/configs')) return '/info'
  return '/channels'
})
</script>

<style scoped>
.nav {
  display: inline-flex;
  gap: 4px;
  padding: 4px;
  border-radius: 13px;
  border: 1px solid var(--app-border-soft);
  background: var(--app-surface-1);
  backdrop-filter: blur(12px) saturate(130%);
  box-shadow: var(--app-shadow-card);
}

.nav-item {
  display: inline-flex;
  align-items: center;
  height: 32px;
  padding: 0 11px;
  border-radius: 10px;
  color: var(--color-text-2);
  font-size: 13px;
  font-weight: 600;
  letter-spacing: -0.2px;
  text-decoration: none;
  user-select: none;
}

.nav-item:hover {
  background: color-mix(in srgb, var(--color-fill-2) 90%, transparent);
  color: var(--color-text-1);
  text-decoration: none;
}

.nav-item.active {
  background: color-mix(in srgb, var(--brand-blue-1) 84%, transparent);
  color: var(--brand-blue-7);
  box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--brand-blue-5) 42%, transparent);
}

body[arco-theme='dark'] .nav-item.active {
  background: color-mix(in srgb, var(--brand-blue-9) 54%, transparent);
  color: var(--brand-blue-3);
  box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--brand-blue-5) 35%, transparent);
}
</style>
