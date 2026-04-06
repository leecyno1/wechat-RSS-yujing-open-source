<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { Message } from '@arco-design/web-vue'
import { getChannelFeeds, type ChannelFeedItem } from '@/api/channels'

interface SelectedFeedItem {
  id: string
  mp_name: string
  mp_cover?: string
  source_platform?: string
  source_type?: string
}

const props = defineProps<{
  modelValue: SelectedFeedItem[]
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', value: SelectedFeedItem[]): void
}>()

const loading = ref(false)
const kw = ref('')
const platformFilter = ref('all')
const allFeeds = ref<ChannelFeedItem[]>([])
const selected = ref<SelectedFeedItem[]>([])

const PLATFORM_LABELS: Record<string, string> = {
  all: '全部平台',
  wechat: '公众号',
  zhihu: '知乎',
  xueqiu: '雪球',
  toutiao: '头条',
  baijiahao: '百家号',
  weibo: '微博',
  portal: '门户',
  rss: '订阅源'
}

const normalizePlatform = (value: string | undefined | null) => {
  const raw = String(value || '').trim().toLowerCase()
  if (!raw) return 'rss'
  if (raw === 'wx') return 'wechat'
  if ([
    'wsj', 'bbc', 'nytimes', 'guardian', 'cnn', 'npr', 'cnbc', 'tech',
    'global_news', 'global_tech', 'global_finance', 'global_programming', 'global_startups',
    'china_news', 'china_tech', 'china_finance', 'china_product'
  ].includes(raw)) return 'portal'
  if (raw === 'rsshub') return 'rss'
  return raw
}

const feedPlatform = (feed: ChannelFeedItem) => {
  return normalizePlatform(feed.source_platform || feed.source_type || 'rss')
}

const isSelected = (id: string) => selected.value.some((x) => String(x.id) === String(id))

const platformOptions = computed(() => {
  const set = new Set<string>(['all'])
  for (const f of allFeeds.value) set.add(feedPlatform(f))
  return Array.from(set).map((key) => ({ value: key, label: PLATFORM_LABELS[key] || key.toUpperCase() }))
})

const filteredFeeds = computed(() => {
  const q = kw.value.trim().toLowerCase()
  return allFeeds.value.filter((f) => {
    if (platformFilter.value !== 'all' && feedPlatform(f) !== platformFilter.value) return false
    if (!q) return true
    return String(f.name || '').toLowerCase().includes(q) || String(f.intro || '').toLowerCase().includes(q)
  })
})

const selectedIdsText = computed(() => selected.value.map((x) => String(x.id)).join(','))

const emitSelected = () => emit('update:modelValue', selected.value)

const toSelected = (feed: ChannelFeedItem): SelectedFeedItem => ({
  id: String(feed.id),
  mp_name: String(feed.name || ''),
  mp_cover: String(feed.cover || ''),
  source_platform: String(feed.source_platform || ''),
  source_type: String(feed.source_type || '')
})

const toggle = (feed: ChannelFeedItem) => {
  const id = String(feed.id)
  const idx = selected.value.findIndex((x) => String(x.id) === id)
  if (idx >= 0) {
    selected.value.splice(idx, 1)
  } else {
    selected.value.push(toSelected(feed))
  }
  emitSelected()
}

const clearAll = () => {
  selected.value = []
  emitSelected()
}

const selectVisible = () => {
  const map = new Map(selected.value.map((x) => [String(x.id), x]))
  for (const feed of filteredFeeds.value) map.set(String(feed.id), toSelected(feed))
  selected.value = Array.from(map.values())
  emitSelected()
}

const selectAllSubscribed = () => {
  selected.value = allFeeds.value.map((f) => toSelected(f))
  emitSelected()
}

const parseSelected = (raw: any[]) => {
  if (!Array.isArray(raw)) {
    selected.value = []
    return
  }
  selected.value = raw
    .map((x) => ({
      id: String((x && (x.id ?? x.mp_id)) || '').trim(),
      mp_name: String((x && (x.mp_name ?? x.name)) || '').trim(),
      mp_cover: String((x && (x.mp_cover ?? x.cover)) || '').trim(),
      source_platform: String((x && x.source_platform) || '').trim(),
      source_type: String((x && x.source_type) || '').trim()
    }))
    .filter((x) => x.id)
}

const loadFeeds = async () => {
  loading.value = true
  try {
    const res: any = await getChannelFeeds({ limit: 500, offset: 0, sort: 'name' })
    allFeeds.value = (res?.list || []) as ChannelFeedItem[]
  } catch (e: any) {
    Message.error(e?.message || '加载订阅项失败')
    allFeeds.value = []
  } finally {
    loading.value = false
  }
}

defineExpose({ parseSelected, selectAllSubscribed })

onMounted(async () => {
  await loadFeeds()
  parseSelected(props.modelValue || [])
})
</script>

<template>
  <a-card :bordered="false" class="feed-multi-select">
    <a-space direction="vertical" fill>
      <a-space wrap>
        <a-input v-model="kw" allow-clear placeholder="搜索已添加订阅" style="min-width: 220px" />
        <a-select v-model="platformFilter" style="width: 140px">
          <a-option v-for="it in platformOptions" :key="it.value" :value="it.value">{{ it.label }}</a-option>
        </a-select>
        <a-button size="small" @click="selectVisible">全选可见</a-button>
        <a-button size="small" @click="selectAllSubscribed">全选已添加订阅</a-button>
        <a-button size="small" status="warning" @click="clearAll">清空</a-button>
      </a-space>

      <div class="selected-line">
        <span class="muted">已选 {{ selected.length }} 项</span>
        <a-input :model-value="selectedIdsText" readonly size="small" />
      </div>

      <a-spin :loading="loading">
        <div class="feed-grid">
          <div
            v-for="f in filteredFeeds"
            :key="f.id"
            class="feed-item"
            :class="{ active: isSelected(String(f.id)) }"
            @click="toggle(f)"
          >
            <a-avatar :size="26" :image-url="f.cover || '/static/default-avatar.png'">
              <img :src="f.cover || '/static/default-avatar.png'" />
            </a-avatar>
            <div class="feed-meta">
              <div class="feed-name">{{ f.name }}</div>
              <div class="feed-sub">{{ PLATFORM_LABELS[feedPlatform(f)] || feedPlatform(f) }}</div>
            </div>
          </div>
          <div v-if="!filteredFeeds.length" class="empty">暂无可选订阅项</div>
        </div>
      </a-spin>
    </a-space>
  </a-card>
</template>

<style scoped>
.feed-multi-select {
  padding: 12px;
}
.selected-line {
  display: grid;
  grid-template-columns: auto 1fr;
  align-items: center;
  gap: 8px;
}
.feed-grid {
  max-height: 420px;
  overflow: auto;
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px;
}
.feed-item {
  display: flex;
  align-items: center;
  gap: 8px;
  border: 1px solid var(--color-border-2);
  border-radius: 10px;
  padding: 8px 10px;
  cursor: pointer;
  background: var(--color-bg-2);
}
.feed-item:hover {
  border-color: rgb(var(--warning-6));
}
.feed-item.active {
  border-color: rgb(var(--warning-6));
  background: var(--color-fill-2);
}
.feed-meta {
  min-width: 0;
}
.feed-name {
  font-size: 12px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.feed-sub {
  font-size: 11px;
  color: var(--color-text-3);
}
.empty {
  grid-column: 1 / -1;
  text-align: center;
  color: var(--color-text-3);
  padding: 24px 0;
}
</style>
