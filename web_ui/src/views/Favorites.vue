<template>
  <a-card :bordered="false" class="favorites-card">
    <template #title>
      <div class="title-row">
        <span>收藏中心</span>
        <a-tag color="blue">{{ filteredItems.length }} / {{ totalItems }}</a-tag>
      </div>
    </template>

    <div class="toolbar compact-toolbar">
      <div class="toolbar-filters">
        <a-input
          v-model="kw"
          allow-clear
          size="small"
          class="search-input"
          placeholder="搜索标题/博主"
          @press-enter="refresh"
        />
        <a-select v-model="categoryFilter" allow-clear size="small" class="filter-select compact-select" placeholder="分类">
          <a-option value="all">全部分类</a-option>
          <a-option v-for="c in categoryOptions" :key="c" :value="c">{{ c }}</a-option>
        </a-select>
        <a-select
          v-model="tagFilter"
          allow-clear
          multiple
          size="small"
          :max-tag-count="1"
          class="filter-select compact-select"
          allow-search
          placeholder="标签"
        >
          <a-option v-for="t in allTags" :key="t" :value="t">{{ t }}</a-option>
        </a-select>
      </div>

      <div class="toolbar-actions compact-row">
        <a-button size="small" :type="officialOnly ? 'primary' : 'outline'" class="tag-toggle" @click="officialOnly = !officialOnly">
          官方精选
        </a-button>
        <a-button size="small" @click="refresh" :loading="loading">
          <template #icon><icon-refresh /></template>
          刷新
        </a-button>
        <a-button size="small" type="outline" @click="exportPanelOpen = !exportPanelOpen">
          {{ exportPanelOpen ? '收起导出' : '文章导出' }}
        </a-button>
        <a-input
          v-model="newCategory"
          size="small"
          class="new-category-input"
          placeholder="新增分类"
          @press-enter="addCategory"
        />
        <a-button size="small" type="outline" @click="addCategory">添加分类</a-button>
      </div>
    </div>

    <div class="stats-row">
      <a-tag size="small">官方精选 {{ officialCount }}</a-tag>
      <a-tag size="small">自定义分类 {{ customCategories.length }}</a-tag>
      <a-tag size="small">标签 {{ allTags.length }}</a-tag>
    </div>

    <a-collapse v-model:active-key="exportActiveKeys" :bordered="false" class="export-collapse">
      <a-collapse-item key="export">
        <template #header>
          <span class="export-header">文章导出（已集成）</span>
        </template>
        <div class="export-toolbar compact-row">
          <a-switch v-model="useAllFeeds" size="small" />
          <span class="hint">{{ useAllFeeds ? '全部订阅' : `已选 ${selectedFeedIds.length} 个` }}</span>
          <a-select
            v-model="selectedFeedIds"
            :disabled="useAllFeeds"
            multiple
            allow-search
            allow-clear
            :max-tag-count="2"
            class="export-feed-select"
            placeholder="选择导出来源"
          >
            <a-option v-for="f in filteredFeeds" :key="f.id" :value="f.id">{{ f.name }}</a-option>
          </a-select>
          <a-checkbox-group v-model="formats" class="format-group">
            <a-checkbox value="pdf">PDF</a-checkbox>
            <a-checkbox value="docx">WORD</a-checkbox>
            <a-checkbox value="json">JSON</a-checkbox>
            <a-checkbox value="csv">CSV</a-checkbox>
          </a-checkbox-group>
          <a-input-number v-model="pageCount" :min="1" :max="10000" size="mini" placeholder="页数" />
          <a-input-number v-model="pageSize" :min="1" :max="10" size="mini" placeholder="每页" />
          <a-button size="small" type="primary" :loading="exporting" @click="submitExport">开始导出</a-button>
          <a-button size="small" :loading="recordsLoading" @click="loadRecords()">刷新记录</a-button>
          <a-button size="small" :loading="linkExporting" @click="openLinksModal">批量导出链接</a-button>
        </div>

        <a-table :data="records" :loading="recordsLoading" :pagination="false" row-key="filename" size="small" class="export-records-table">
          <a-table-column title="文件名" data-index="filename" />
          <a-table-column title="大小" :width="110">
            <template #cell="{ record }">{{ formatFileSize(record.size) }}</template>
          </a-table-column>
          <a-table-column title="时间" :width="170">
            <template #cell="{ record }">{{ formatDateTime(record.modified_time || record.created_time) }}</template>
          </a-table-column>
          <a-table-column title="操作" :width="150">
            <template #cell="{ record }">
              <a-space>
                <a-button size="mini" type="outline" @click="downloadRecord(record)">下载</a-button>
                <a-button size="mini" status="danger" @click="deleteRecord(record)">删除</a-button>
              </a-space>
            </template>
          </a-table-column>
        </a-table>
      </a-collapse-item>
    </a-collapse>

    <a-card class="public-card" size="small" :bordered="false">
      <template #title>
        <div class="title-row">
          <span>公共收藏榜</span>
          <a-space size="small">
            <a-select v-model="publicDays" size="mini" class="public-days" @change="loadPublicFavorites">
              <a-option :value="0">全部时间</a-option>
              <a-option :value="7">最近7天</a-option>
              <a-option :value="30">最近30天</a-option>
              <a-option :value="90">最近90天</a-option>
            </a-select>
            <a-button size="mini" type="outline" :loading="publicLoading" @click="loadPublicFavorites">刷新</a-button>
          </a-space>
        </div>
      </template>

      <a-spin :loading="publicLoading">
        <div v-if="publicItems.length" class="public-grid">
          <div v-for="item in publicItems" :key="`public-${item.id}`" class="public-item">
            <div class="public-main">
              <a-link :href="item.url" target="_blank" class="public-title">{{ item.title }}</a-link>
              <div class="public-meta">
                <span>{{ item.mp_name || '未知来源' }}</span>
                <span class="dot">·</span>
                <span>{{ item.favorite_users || 0 }} 人收藏</span>
                <span class="dot">·</span>
                <span>热度 {{ item.hot_score || 0 }}</span>
              </div>
            </div>
            <a-button
              size="mini"
              type="primary"
              :disabled="item.my_favorited"
              @click="favoriteFromPublic(item.id)"
            >
              {{ item.my_favorited ? '已在我的收藏' : '加入收藏' }}
            </a-button>
          </div>
        </div>
        <a-empty v-else description="暂无公共收藏数据" />
      </a-spin>
    </a-card>

    <a-table
      :data="pagedItems"
      :loading="loading"
      :pagination="pagination"
      row-key="id"
      @page-change="handlePageChange"
      @page-size-change="handlePageSizeChange"
    >
      <a-table-column title="文章" data-index="title" :ellipsis="true">
        <template #cell="{ record }">
          <div class="title-cell">
            <a-link :href="record.url" target="_blank" @click="trackOpen(record.id)">
              {{ record.title }}
            </a-link>
            <div class="title-meta">
              <span>{{ record.mp_name || '未知来源' }}</span>
              <span class="dot">·</span>
              <span>{{ formatTimestamp(record.publish_time) }}</span>
              <span class="dot">·</span>
              <span>热度 {{ record._score }}</span>
            </div>
            <div class="tag-row">
              <a-tag v-for="tag in record._allTags.slice(0, 6)" :key="`${record.id}-${tag}`" size="mini">{{ tag }}</a-tag>
            </div>
          </div>
        </template>
      </a-table-column>

      <a-table-column title="分类" :width="150">
        <template #cell="{ record }">
          <a-select
            :model-value="record._category"
            size="mini"
            allow-clear
            class="table-select"
            placeholder="未分类"
            @change="(val) => updateCategory(record.id, String(val || ''))"
          >
            <a-option v-for="c in categoryOptions" :key="c" :value="c">{{ c }}</a-option>
          </a-select>
        </template>
      </a-table-column>

      <a-table-column title="自定义标签" :width="220">
        <template #cell="{ record }">
          <a-input-tag
            :model-value="getUserTags(record.id)"
            :max-tag-count="2"
            allow-clear
            size="mini"
            class="table-tag-input"
            placeholder="回车添加"
            @change="(val) => updateUserTags(record.id, val as string[])"
          />
        </template>
      </a-table-column>

      <a-table-column title="收藏时间" data-index="favorited_at" :width="168" />
      <a-table-column title="操作" :width="90">
        <template #cell="{ record }">
          <a-button type="text" status="danger" @click="remove(record.id)">
            <template #icon><icon-delete /></template>
          </a-button>
        </template>
      </a-table-column>
    </a-table>

    <a-modal
      v-model:visible="linksVisible"
      title="批量链接导出"
      :footer="false"
      width="860px"
      unmount-on-close
    >
      <a-space direction="vertical" fill>
        <div class="toolbar compact-row">
          <a-input-number v-model="linkLimit" :min="10" :max="2000" size="small" placeholder="链接数量" />
          <a-input v-model="linkSearch" size="small" allow-clear placeholder="按关键词筛选文章（可选）" />
          <a-button size="small" :loading="linkExporting" @click="generateLinks">重新生成</a-button>
          <a-button size="small" type="primary" @click="copyLinks">复制全部链接</a-button>
        </div>
        <a-textarea v-model="linksText" :auto-size="{ minRows: 12, maxRows: 20 }" />
      </a-space>
    </a-modal>
  </a-card>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { Message, Modal } from '@arco-design/web-vue'
import { formatTimestamp } from '@/utils/date'
import { getChannelArticles, getChannelFeeds } from '@/api/channels'
import { DeleteExportRecords, exportArticles, getExportRecords } from '@/api/tools'
import {
  createFavoriteCategory,
  favoriteArticle,
  listFavoriteCategories,
  listFavoriteMeta,
  listFavorites,
  listPublicFavorites,
  unfavoriteArticle,
  updateFavoriteMeta
} from '@/api/favorites'

type FavoriteMeta = {
  category?: string
  user_tags?: string[]
  open_count?: number
}

type FeedItem = { id: string; name: string }

const DEFAULT_CATEGORIES = ['未分类', '官方精选', '商业财经', '科技AI', '科教文卫', '门户资讯']

const loading = ref(false)
const items = ref<any[]>([])
const publicLoading = ref(false)
const publicItems = ref<any[]>([])
const publicDays = ref<number>(30)
const metas = ref<Record<string, FavoriteMeta>>({})
const customCategories = ref<string[]>([])

const kw = ref('')
const categoryFilter = ref('all')
const tagFilter = ref<string[]>([])
const officialOnly = ref(false)
const newCategory = ref('')
const exportPanelOpen = ref(false)
const exportActiveKeys = ref<string[]>([])

const feeds = ref<FeedItem[]>([])
const useAllFeeds = ref(true)
const selectedFeedIds = ref<string[]>([])
const formats = ref<string[]>(['pdf', 'docx', 'json', 'csv'])
const pageCount = ref(10)
const pageSize = ref(10)
const exporting = ref(false)
const records = ref<any[]>([])
const recordsLoading = ref(false)
const activeExportKey = ref('all_subscriptions')
const linksVisible = ref(false)
const linkExporting = ref(false)
const linkLimit = ref(200)
const linkSearch = ref('')
const linksText = ref('')

const pagination = ref({
  current: 1,
  pageSize: 20,
  total: 0,
  showTotal: true,
  showJumper: true,
  showPageSize: true,
  pageSizeOptions: [10, 20, 50, 100]
})

const categoryOptions = computed(() => {
  const set = new Set(DEFAULT_CATEGORIES)
  customCategories.value.forEach((x) => set.add(x))
  return Array.from(set)
})

const normalizeTag = (x: string) => String(x || '').trim().replace(/\s+/g, '')
const errText = (e: any) => String(e?.detail?.message || e?.message || e?.detail || e || '操作失败')

const loadFavoriteMetaData = async () => {
  try {
    const [metaRes, catRes] = await Promise.allSettled([listFavoriteMeta({ only_favorited: true }), listFavoriteCategories()])
    const next: Record<string, FavoriteMeta> = {}
    if (metaRes.status === 'fulfilled') {
      const list = (metaRes.value as any)?.list || []
      for (const item of list) {
        const aid = String(item?.article_id || '').trim()
        if (!aid) continue
        next[aid] = {
          category: String(item?.category || '').trim(),
          user_tags: Array.isArray(item?.tags) ? item.tags.map(normalizeTag).filter(Boolean) : [],
          open_count: Number(item?.open_count || 0)
        }
      }
      if (Array.isArray((metaRes.value as any)?.categories)) {
        customCategories.value = ((metaRes.value as any).categories || []).map((x: any) => String(x || '').trim()).filter(Boolean)
      }
    }
    if (catRes.status === 'fulfilled' && Array.isArray((catRes.value as any)?.list)) {
      const fromCatApi = ((catRes.value as any).list || []).map((x: any) => String(x || '').trim()).filter(Boolean)
      if (fromCatApi.length) customCategories.value = fromCatApi
    }
    metas.value = next
  } catch {
    metas.value = {}
  }
}

const inferAutoTags = (item: any): string[] => {
  const text = `${item.title || ''} ${item.description || ''} ${item.mp_name || ''} ${item.source_platform || ''}`.toLowerCase()
  const tags: string[] = []
  const rules: Array<[RegExp, string]> = [
    [/ai|大模型|人工智能|agent|gpt|deepseek/, 'AI'],
    [/财经|金融|投资|股市|基金|宏观|雪球/, '财经'],
    [/创业|产品|增长|商业|运营/, '商业'],
    [/教育|科研|高校|医学|卫生/, '科教文卫'],
    [/知乎|微博|头条|百家|公众号/, '平台'],
    [/bbc|wsj|guardian|nytimes|cnn/, '海外资讯'],
    [/科技|编程|开发|芯片|开源/, '科技']
  ]
  rules.forEach(([re, tag]) => {
    if (re.test(text)) tags.push(tag)
  })
  if ((item.mp_name || '').trim()) tags.push(String(item.mp_name).trim())
  return Array.from(new Set(tags))
}

const scoreItem = (item: any, meta: FavoriteMeta) => {
  const open = Number(meta.open_count || 0)
  const read = Number(item.read_count || 0)
  const like = Number(item.like_count || 0)
  const share = Number(item.share_count || 0)
  const recommend = Number(item.recommend_count || 0)
  return Math.round(open * 8 + like * 2 + share * 3 + recommend * 2 + read / 1000)
}

const decoratedItems = computed(() => {
  return items.value.map((item) => {
    const id = String(item.id)
    const meta = metas.value[id] || {}
    const userTags = (meta.user_tags || []).map(normalizeTag).filter(Boolean)
    const autoTags = inferAutoTags(item)
    const allTags = Array.from(new Set([...userTags, ...autoTags]))
    const score = scoreItem(item, meta)
    const official = score >= 12 || Number(meta.open_count || 0) >= 3 || Number(item.like_count || 0) >= 20
    const category = String(meta.category || '').trim() || (official ? '官方精选' : '未分类')
    return {
      ...item,
      _category: category,
      _score: score,
      _official: official,
      _allTags: allTags
    }
  })
})

const allTags = computed(() => {
  const set = new Set<string>()
  decoratedItems.value.forEach((x) => x._allTags.forEach((t: string) => set.add(t)))
  return Array.from(set)
})

const filteredFeeds = computed(() => {
  if (!kw.value.trim()) return feeds.value
  const q = kw.value.trim().toLowerCase()
  return feeds.value.filter((x) => `${x.name || ''} ${x.id || ''}`.toLowerCase().includes(q))
})

const exportFeedIds = computed(() => {
  if (useAllFeeds.value) return feeds.value.map((x) => x.id).filter(Boolean)
  return selectedFeedIds.value.filter(Boolean)
})

const filteredItems = computed(() => {
  const q = kw.value.trim().toLowerCase()
  return decoratedItems.value.filter((item) => {
    if (officialOnly.value && !item._official) return false
    if (categoryFilter.value !== 'all' && item._category !== categoryFilter.value) return false
    if (tagFilter.value.length && !tagFilter.value.some((t) => item._allTags.includes(t))) return false
    if (!q) return true
    const hay = `${item.title || ''} ${item.description || ''} ${item.mp_name || ''}`.toLowerCase()
    return hay.includes(q)
  })
})

const pagedItems = computed(() => {
  const start = (pagination.value.current - 1) * pagination.value.pageSize
  return filteredItems.value.slice(start, start + pagination.value.pageSize)
})

const totalItems = computed(() => decoratedItems.value.length)
const officialCount = computed(() => decoratedItems.value.filter((x) => x._official).length)

const refresh = async () => {
  loading.value = true
  try {
    const all: any[] = []
    let offset = 0
    const limit = 100
    while (true) {
      const res: any = await listFavorites({ offset, limit })
      const list = res.list || []
      all.push(...list)
      if (list.length < limit) break
      offset += limit
    }
    items.value = all
    pagination.value.total = filteredItems.value.length
    if ((pagination.value.current - 1) * pagination.value.pageSize >= pagination.value.total) {
      pagination.value.current = 1
    }
    await Promise.allSettled([loadFavoriteMetaData(), loadPublicFavorites()])
  } catch (e) {
    Message.error(errText(e))
  } finally {
    loading.value = false
  }
}

const hashText = (text: string) => {
  let h = 0
  for (let i = 0; i < text.length; i++) h = (h * 31 + text.charCodeAt(i)) | 0
  return String(Math.abs(h))
}

const computeExportKey = () => {
  if (useAllFeeds.value) return 'all_subscriptions'
  if (selectedFeedIds.value.length <= 1) return selectedFeedIds.value[0] || 'selected_subscriptions'
  return `batch_${hashText(selectedFeedIds.value.join(','))}`
}

const formatFileSize = (size: number | string) => {
  const n = Number(size || 0)
  if (!n || Number.isNaN(n)) return '0 MB'
  return `${(n / (1024 * 1024)).toFixed(2)} MB`
}

const formatDateTime = (v: string) => {
  if (!v) return '-'
  const d = new Date(v)
  if (Number.isNaN(d.getTime())) return '-'
  return d.toLocaleString('zh-CN')
}

const loadFeeds = async () => {
  try {
    const res: any = await getChannelFeeds({ limit: 1000, offset: 0 })
    const list = (res?.list || []).map((x: any) => ({ id: String(x.id || ''), name: String(x.name || x.mp_name || x.id || '') }))
    feeds.value = list.filter((x: FeedItem) => !!x.id)
    if (!selectedFeedIds.value.length && feeds.value.length) selectedFeedIds.value = [feeds.value[0].id]
  } catch (e) {
    Message.error(errText(e))
  }
}

const loadRecords = async (key?: string) => {
  const targetKey = String(key || activeExportKey.value || '').trim() || 'all_subscriptions'
  activeExportKey.value = targetKey
  recordsLoading.value = true
  try {
    const res: any = await getExportRecords({ export_key: targetKey })
    const list = Array.isArray(res) ? res : res?.data || []
    records.value = list
  } catch (e) {
    records.value = []
    Message.error(errText(e))
  } finally {
    recordsLoading.value = false
  }
}

const submitExport = async () => {
  if (!formats.value.length) {
    Message.info('请至少选择一种导出格式')
    return
  }
  if (!useAllFeeds.value && !exportFeedIds.value.length) {
    Message.info('请先选择要导出的订阅源')
    return
  }

  exporting.value = true
  const key = computeExportKey()
  try {
    const mpId = useAllFeeds.value ? '' : exportFeedIds.value.join(',')
    await exportArticles({
      mp_id: mpId,
      export_scope: useAllFeeds.value ? 'all_subscriptions' : 'selected',
      export_key: key,
      scope: 'all',
      ids: [],
      page_count: Number(pageCount.value || 1),
      limit: Number(pageSize.value || 10),
      add_title: true,
      remove_images: false,
      remove_links: false,
      format: formats.value,
      zip_filename: ''
    })
    Message.success('导出任务已启动')
    await loadRecords(key)
  } catch (e) {
    Message.error(errText(e))
  } finally {
    exporting.value = false
  }
}

const downloadRecord = (record: any) => {
  if (!record?.download_url) {
    Message.info('下载链接不可用')
    return
  }
  window.open(record.download_url, '_blank')
}

const deleteRecord = (record: any) => {
  Modal.confirm({
    title: '确认删除',
    content: `确定删除 ${record?.filename || '该文件'} 吗？`,
    onOk: async () => {
      try {
        await DeleteExportRecords({ export_key: activeExportKey.value, filename: record.path })
        await loadRecords()
        Message.success('删除成功')
      } catch (e) {
        Message.error(errText(e))
      }
    }
  })
}

const buildArticleLinkList = async () => {
  const out = new Set<string>()
  const perPage = 100
  let offset = 0

  while (out.size < Number(linkLimit.value || 200)) {
    const params: any = {
      limit: perPage,
      offset,
      search: String(linkSearch.value || '').trim() || undefined
    }
    if (!useAllFeeds.value) params.mp_ids = exportFeedIds.value
    const res: any = await getChannelArticles(params)
    const list = (res?.list || []).slice(0, perPage)
    for (const item of list) {
      const url = String(item?.url || item?.link || '').trim()
      if (url) out.add(url)
      if (out.size >= Number(linkLimit.value || 200)) break
    }
    if (!list.length || list.length < perPage) break
    offset += perPage
  }
  return Array.from(out)
}

const generateLinks = async () => {
  if (!useAllFeeds.value && !exportFeedIds.value.length) {
    Message.info('请先选择订阅源')
    return
  }
  linkExporting.value = true
  try {
    const urls = await buildArticleLinkList()
    linksText.value = urls.join('\n')
    Message.success(`已生成 ${urls.length} 条链接`)
  } catch (e) {
    Message.error(errText(e))
  } finally {
    linkExporting.value = false
  }
}

const openLinksModal = async () => {
  linksVisible.value = true
  if (!linksText.value.trim()) await generateLinks()
}

const copyLinks = async () => {
  const text = String(linksText.value || '').trim()
  if (!text) {
    Message.info('当前没有可复制的链接')
    return
  }
  try {
    await navigator.clipboard.writeText(text)
    Message.success('链接已复制到剪贴板')
  } catch {
    Message.error('复制失败，请手动复制')
  }
}

const loadPublicFavorites = async () => {
  publicLoading.value = true
  try {
    const res: any = await listPublicFavorites({ offset: 0, limit: 12, days: Number(publicDays.value || 0) })
    publicItems.value = res.list || []
  } catch (e) {
    Message.error(errText(e))
  } finally {
    publicLoading.value = false
  }
}

const handlePageChange = (page: number) => {
  pagination.value.current = page
}

const handlePageSizeChange = (pageSize: number) => {
  pagination.value.pageSize = pageSize
  pagination.value.current = 1
}

const remove = async (articleId: string) => {
  try {
    await unfavoriteArticle(articleId)
    delete metas.value[String(articleId)]
    Message.success('已取消收藏')
    await refresh()
  } catch (e) {
    Message.error(errText(e))
  }
}

const favoriteFromPublic = async (articleId: string) => {
  try {
    await favoriteArticle(String(articleId))
    Message.success('已加入我的收藏')
    await refresh()
  } catch (e) {
    Message.error(errText(e))
  }
}

const getUserTags = (articleId: string) => (metas.value[String(articleId)]?.user_tags || []).slice(0, 20)

const updateCategory = (articleId: string, category: string) => {
  const id = String(articleId)
  metas.value[id] = {
    ...(metas.value[id] || {}),
    category: String(category || '').trim()
  }
  updateFavoriteMeta(id, { category: String(category || '').trim() }).catch(() => {})
}

const updateUserTags = (articleId: string, tags: string[]) => {
  const id = String(articleId)
  const clean = (tags || []).map(normalizeTag).filter(Boolean)
  metas.value[id] = {
    ...(metas.value[id] || {}),
    user_tags: clean
  }
  updateFavoriteMeta(id, { tags: clean }).catch(() => {})
}

const trackOpen = (articleId: string) => {
  const id = String(articleId)
  const old = metas.value[id] || {}
  metas.value[id] = {
    ...old,
    open_count: Number(old.open_count || 0) + 1
  }
  updateFavoriteMeta(id, { open_count_inc: 1 }).catch(() => {})
}

const addCategory = async () => {
  const name = String(newCategory.value || '').trim()
  if (!name) return
  if (categoryOptions.value.includes(name)) {
    newCategory.value = ''
    return
  }
  try {
    await createFavoriteCategory(name)
    newCategory.value = ''
    await loadFavoriteMetaData()
    Message.success('分类已添加')
  } catch (e) {
    Message.error(errText(e))
  }
}

watch([kw, categoryFilter, tagFilter, officialOnly], () => {
  pagination.value.current = 1
  pagination.value.total = filteredItems.value.length
})

watch(
  exportPanelOpen,
  (v) => {
    exportActiveKeys.value = v ? ['export'] : []
  },
  { immediate: true }
)

watch(exportActiveKeys, (v: any) => {
  if (Array.isArray(v)) {
    exportPanelOpen.value = v.includes('export')
    return
  }
  exportPanelOpen.value = String(v || '') === 'export'
})

onMounted(async () => {
  await Promise.allSettled([refresh(), loadFeeds(), loadRecords('all_subscriptions')])
})
</script>

<style scoped>
.favorites-card {
  margin: 10px 12px;
  border: 1px solid var(--app-border-soft);
  border-radius: var(--app-radius-lg);
  background: var(--app-surface-1);
  box-shadow: var(--app-shadow-soft);
}

.title-row {
  display: flex;
  align-items: center;
  gap: 7px;
}

.toolbar {
  display: grid;
  gap: 6px;
  margin-bottom: 8px;
  padding: 8px;
  border-radius: 12px;
  border: 1px solid var(--app-border-soft);
  background: var(--app-surface-2);
  box-shadow: var(--app-shadow-card);
}

.compact-toolbar {
  gap: 5px;
}

.compact-row {
  gap: 6px;
}

.toolbar-primary {
  display: none;
}

.toolbar-filters {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 6px;
}

.toolbar-actions {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: nowrap;
  overflow-x: auto;
  padding-bottom: 2px;
}

.search-input {
  width: 100%;
}

.filter-select {
  width: 100%;
}

.compact-select {
  width: 100%;
}

.new-category-input {
  width: 120px;
  flex: 0 0 auto;
}

.official-check {
  display: inline-flex;
  align-items: center;
  padding: 0 8px;
  border-radius: 8px;
  border: 1px solid var(--color-border);
  background: color-mix(in srgb, var(--color-bg-2) 88%, transparent);
}

.tag-toggle {
  min-width: 78px;
  flex: 0 0 auto;
}

.toolbar-actions :deep(.arco-btn) {
  flex: 0 0 auto;
}

.stats-row {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-bottom: 8px;
  justify-content: flex-end;
}

.export-collapse {
  margin-bottom: 10px;
  border: 1px solid var(--app-border-soft);
  border-radius: 12px;
  background: var(--app-surface-1);
  box-shadow: var(--app-shadow-card);
}

.export-header {
  font-size: 12px;
  font-weight: 600;
}

.export-toolbar {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  margin-bottom: 8px;
}

.export-feed-select {
  width: min(300px, 56vw);
}

.format-group {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.export-records-table {
  border: 1px solid var(--app-border-soft);
  border-radius: 10px;
  overflow: hidden;
}

.hint {
  font-size: 12px;
  color: var(--color-text-3);
}

.public-card {
  margin-bottom: 12px;
  border: 1px solid var(--app-border-soft);
  border-radius: 12px;
  background: var(--app-surface-1);
  box-shadow: var(--app-shadow-card);
}

.public-days {
  width: 120px;
}

.public-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 7px;
}

.public-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 8px;
  padding: 8px 9px;
  border-radius: 11px;
  border: 1px solid var(--app-border-soft);
  background: var(--app-surface-2);
  box-shadow: var(--app-shadow-card);
}

.public-main {
  min-width: 0;
}

.public-title {
  display: block;
  max-width: 100%;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.public-meta {
  margin-top: 4px;
  font-size: 12px;
  color: var(--color-text-3);
}

.title-cell {
  display: flex;
  flex-direction: column;
  gap: 3px;
}

.title-meta {
  font-size: 12px;
  color: var(--color-text-3);
}

.tag-row {
  display: flex;
  gap: 5px;
  flex-wrap: wrap;
}

.dot {
  margin: 0 4px;
}

.table-select {
  width: 106px;
}

.table-tag-input {
  width: 170px;
}

.favorites-card :deep(.arco-card-header),
.public-card :deep(.arco-card-header) {
  min-height: 42px;
  padding-top: 10px;
  padding-bottom: 8px;
}

.favorites-card :deep(.arco-card-body) {
  padding-top: 10px;
}

.favorites-card :deep(.arco-table),
.favorites-card :deep(.arco-table-container) {
  border-radius: 12px;
}

.favorites-card :deep(.arco-table-th),
.favorites-card :deep(.arco-table-td) {
  padding-top: 8px;
  padding-bottom: 8px;
}

.favorites-card :deep(.arco-table-tr:hover .arco-table-td) {
  background: color-mix(in srgb, var(--brand-blue-1) 36%, transparent);
}

body[arco-theme='dark'] .favorites-card :deep(.arco-table-tr:hover .arco-table-td) {
  background: color-mix(in srgb, var(--brand-blue-9) 42%, transparent);
}

@media (max-width: 980px) {
  .toolbar-filters {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }
  .export-feed-select {
    width: min(240px, 72vw);
  }
  .public-grid {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 720px) {
  .favorites-card {
    margin: 8px;
  }
  .toolbar {
    padding: 7px;
  }
  .toolbar-filters {
    grid-template-columns: 1fr;
  }
  .toolbar-actions {
    flex-wrap: wrap;
    overflow-x: visible;
  }
}
</style>
