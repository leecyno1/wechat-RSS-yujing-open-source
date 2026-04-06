<template>
  <div class="workbench">
    <a-card :bordered="false" class="summary-card">
      <div class="summary-row">
        <div class="summary-item">
          <div class="summary-label">总订阅</div>
          <div class="summary-value">{{ allRows.length }}</div>
        </div>
        <div class="summary-item">
          <div class="summary-label">公众号</div>
          <div class="summary-value">{{ wechatRows.length }}</div>
        </div>
        <div class="summary-item">
          <div class="summary-label">多平台</div>
          <div class="summary-value">{{ sourceRows.length }}</div>
        </div>
        <div class="summary-actions">
          <a-button size="small" type="outline" :loading="loading" @click="loadAll">刷新列表</a-button>
          <a-button
            size="small"
            type="outline"
            :loading="batchRefreshing"
            :disabled="!selectedRows.length"
            @click="batchRefresh"
          >
            批量刷新
          </a-button>
          <a-button
            size="small"
            status="danger"
            :loading="batchRemoving"
            :disabled="!selectedRows.length"
            @click="batchRemove"
          >
            批量取消订阅
          </a-button>
        </div>
      </div>
    </a-card>

    <a-card :bordered="false">
      <div class="filter-row">
        <a-input
          v-model="keyword"
          size="small"
          allow-clear
          class="filter-input"
          placeholder="搜索订阅源/博主名称"
          @press-enter="noop"
        />
        <a-select v-model="platform" size="small" class="filter-select">
          <a-option value="all">全部平台</a-option>
          <a-option v-for="p in platformOptions" :key="p" :value="p">{{ platformLabel(p) }}</a-option>
        </a-select>
        <a-tag color="arcoblue">已选 {{ selectedRows.length }} 项</a-tag>
      </div>

      <a-table
        row-key="key"
        :columns="columns"
        :data="filteredRows"
        :loading="loading"
        :pagination="{ pageSize: 12, showPageSize: true, pageSizeOptions: [12, 20, 40] }"
        :row-selection="{
          type: 'checkbox',
          showCheckedAll: true,
          onlyCurrent: false,
          checkStrictly: true
        }"
        v-model:selectedKeys="selectedKeys"
      >
        <template #name="{ record }">
          <div class="name-cell">
            <span class="name-main">{{ record.name }}</span>
            <a-tag size="small" :color="record.kind === 'wechat' ? 'green' : 'blue'">
              {{ record.kind === 'wechat' ? '公众号' : 'RSS' }}
            </a-tag>
          </div>
        </template>
        <template #platform="{ record }">
          <span>{{ platformLabel(record.platform) }}</span>
        </template>
        <template #source="{ record }">
          <span class="source-cell" :title="record.source">{{ record.source }}</span>
        </template>
        <template #actions="{ record }">
          <a-space>
            <a-button
              size="mini"
              type="outline"
              :loading="refreshingMap[record.key] === true"
              @click="refreshOne(record)"
            >
              刷新
            </a-button>
            <a-button
              size="mini"
              status="danger"
              :loading="removingMap[record.key] === true"
              @click="removeOne(record)"
            >
              取消订阅
            </a-button>
          </a-space>
        </template>
      </a-table>
    </a-card>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { Modal } from '@arco-design/web-vue'
import { getSubscriptions, UpdateMps, deleteMpApi } from '@/api/subscription'
import { deleteSourceFeed, listSourceFeeds, refreshSourceFeed } from '@/api/sources'
import { notifyError, notifyInfo, notifySuccess } from '@/utils/notify'

type ManageRowKind = 'wechat' | 'source'

interface ManageRow {
  key: string
  id: string
  name: string
  platform: string
  kind: ManageRowKind
  source: string
}

const loading = ref(false)
const batchRefreshing = ref(false)
const batchRemoving = ref(false)

const keyword = ref('')
const platform = ref('all')
const selectedKeys = ref<string[]>([])

const wechatRows = ref<ManageRow[]>([])
const sourceRows = ref<ManageRow[]>([])

const refreshingMap = ref<Record<string, boolean>>({})
const removingMap = ref<Record<string, boolean>>({})

const allRows = computed(() => [...wechatRows.value, ...sourceRows.value])

const rowsByKey = computed(() => {
  const map = new Map<string, ManageRow>()
  for (const row of allRows.value) map.set(row.key, row)
  return map
})

const selectedRows = computed(() => selectedKeys.value.map((x) => rowsByKey.value.get(String(x))).filter(Boolean) as ManageRow[])

const platformOptions = computed(() => {
  const set = new Set<string>()
  for (const row of allRows.value) set.add(String(row.platform || 'other'))
  return Array.from(set.values()).sort()
})

const filteredRows = computed(() => {
  const kw = String(keyword.value || '').trim().toLowerCase()
  const pf = String(platform.value || 'all').trim().toLowerCase()
  return allRows.value.filter((row) => {
    if (pf && pf !== 'all' && String(row.platform || '').toLowerCase() !== pf) return false
    if (!kw) return true
    const hay = `${row.name} ${row.source} ${row.platform}`.toLowerCase()
    return hay.includes(kw)
  })
})

const platformLabel = (platformKey: string) => {
  const key = String(platformKey || '').toLowerCase()
  const labels: Record<string, string> = {
    wechat: '公众号',
    zhihu: '知乎',
    xueqiu: '雪球',
    toutiao: '头条',
    baijiahao: '百家号',
    weibo: '微博',
    wsj: '华尔街日报',
    bbc: 'BBC',
    rss: 'RSS',
    rsshub: 'RSSHub',
    other: '其他',
  }
  return labels[key] || key || '其他'
}

const columns = [
  { title: '订阅源/博主', slotName: 'name', width: 260 },
  { title: '平台', slotName: 'platform', width: 120 },
  { title: '来源标识', slotName: 'source' },
  { title: '操作', slotName: 'actions', width: 180 },
]

const noop = () => {}

const loadAll = async () => {
  loading.value = true
  try {
    const [wxRes, srcRes] = await Promise.allSettled([
      getSubscriptions({ page: 0, pageSize: 1000 }),
      listSourceFeeds({ limit: 1000, offset: 0 }),
    ])

    if (wxRes.status === 'fulfilled') {
      const list = (wxRes.value as any)?.list || (wxRes.value as any)?.data?.list || []
      wechatRows.value = list.map((x: any) => ({
        key: `wechat:${x.id}`,
        id: String(x.id),
        name: String(x.mp_name || x.name || '未命名公众号'),
        platform: 'wechat',
        kind: 'wechat' as const,
        source: String(x.id || ''),
      }))
    } else {
      wechatRows.value = []
    }

    if (srcRes.status === 'fulfilled') {
      const list = (srcRes.value as any)?.list || []
      sourceRows.value = list.map((x: any) => ({
        key: `source:${x.id}`,
        id: String(x.id),
        name: String(x.name || '未命名来源'),
        platform: String(x.source_platform || x.source_type || 'other'),
        kind: 'source' as const,
        source: String(x.source_url || ''),
      }))
    } else {
      sourceRows.value = []
    }
    selectedKeys.value = []
  } catch (e: any) {
    notifyError(e?.message || '加载订阅管理列表失败')
  } finally {
    loading.value = false
  }
}

const refreshOne = async (row: ManageRow) => {
  if (!row?.id) return
  refreshingMap.value[row.key] = true
  try {
    if (row.kind === 'wechat') {
      await UpdateMps(row.id, { start_page: 0, end_page: 1 })
      notifySuccess(`已触发刷新：${row.name}`)
    } else {
      const res: any = await refreshSourceFeed(row.id)
      notifySuccess(`刷新完成：${row.name}（新增 ${Number(res?.changed || 0)} 篇）`)
    }
  } catch (e: any) {
    notifyError(e?.message || `刷新失败：${row.name}`)
  } finally {
    refreshingMap.value[row.key] = false
  }
}

const removeOne = async (row: ManageRow) => {
  Modal.confirm({
    title: '确认取消订阅',
    content: `确定取消订阅「${row.name}」吗？`,
    onOk: async () => {
      removingMap.value[row.key] = true
      try {
        if (row.kind === 'wechat') {
          await deleteMpApi(row.id, { hard: false })
        } else {
          await deleteSourceFeed(row.id, { hard: false })
        }
        notifySuccess(`已取消订阅：${row.name}`)
        await loadAll()
      } catch (e: any) {
        notifyError(e?.message || `取消失败：${row.name}`)
      } finally {
        removingMap.value[row.key] = false
      }
    },
  })
}

const runWithConcurrency = async <T>(list: T[], limit: number, worker: (item: T) => Promise<void>) => {
  let cursor = 0
  const cap = Math.max(1, Math.min(8, limit || 4))
  const jobs = Array.from({ length: Math.min(cap, list.length) }).map(async () => {
    while (cursor < list.length) {
      const idx = cursor++
      await worker(list[idx])
    }
  })
  await Promise.all(jobs)
}

const batchRefresh = async () => {
  const list = selectedRows.value
  if (!list.length) {
    notifyInfo('请先勾选需要刷新的订阅项')
    return
  }
  batchRefreshing.value = true
  let ok = 0
  let fail = 0
  try {
    await runWithConcurrency(list, 4, async (row) => {
      try {
        if (row.kind === 'wechat') {
          await UpdateMps(row.id, { start_page: 0, end_page: 1 })
        } else {
          await refreshSourceFeed(row.id)
        }
        ok += 1
      } catch {
        fail += 1
      }
    })
    notifySuccess(`批量刷新已完成：成功 ${ok}，失败 ${fail}`)
  } finally {
    batchRefreshing.value = false
  }
}

const batchRemove = async () => {
  const list = selectedRows.value
  if (!list.length) {
    notifyInfo('请先勾选需要取消订阅的项目')
    return
  }
  Modal.confirm({
    title: '批量取消订阅',
    content: `确认取消所选 ${list.length} 项订阅吗？`,
    onOk: async () => {
      batchRemoving.value = true
      let ok = 0
      let fail = 0
      try {
        await runWithConcurrency(list, 4, async (row) => {
          try {
            if (row.kind === 'wechat') {
              await deleteMpApi(row.id, { hard: false })
            } else {
              await deleteSourceFeed(row.id, { hard: false })
            }
            ok += 1
          } catch {
            fail += 1
          }
        })
        notifySuccess(`批量取消完成：成功 ${ok}，失败 ${fail}`)
        await loadAll()
      } finally {
        batchRemoving.value = false
      }
    },
  })
}

onMounted(async () => {
  await loadAll()
})
</script>

<style scoped>
.workbench {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.summary-card {
  background: color-mix(in srgb, var(--color-bg-2) 90%, transparent);
}

.summary-row {
  display: grid;
  grid-template-columns: repeat(3, minmax(100px, 140px)) 1fr;
  gap: 10px;
  align-items: center;
}

.summary-item {
  border: 1px solid var(--color-border);
  border-radius: 12px;
  padding: 8px 10px;
  background: var(--color-bg-1);
}

.summary-label {
  font-size: 12px;
  color: var(--color-text-3);
}

.summary-value {
  font-size: 20px;
  line-height: 1.2;
  font-weight: 700;
  color: var(--color-text-1);
}

.summary-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  justify-content: flex-end;
}

.filter-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}

.filter-input {
  width: 260px;
}

.filter-select {
  width: 140px;
}

.name-cell {
  display: flex;
  align-items: center;
  gap: 8px;
}

.name-main {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.source-cell {
  display: inline-block;
  max-width: 620px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--color-text-2);
}

@media (max-width: 1200px) {
  .summary-row {
    grid-template-columns: repeat(2, minmax(100px, 1fr));
  }

  .summary-actions {
    grid-column: 1 / -1;
    justify-content: flex-start;
  }
}
</style>
