<template>
  <div class="article-export-page">
    <a-card :bordered="false">
      <template #title>文章导出</template>
      <a-space direction="vertical" fill size="large">
        <div class="toolbar">
          <a-input
            v-model="feedKw"
            allow-clear
            size="small"
            class="feed-search"
            placeholder="搜索订阅源"
          />
          <a-button size="small" :loading="feedsLoading" @click="loadFeeds">刷新订阅源</a-button>
        </div>

        <a-space direction="vertical" fill>
          <div class="row">
            <span class="label">导出范围</span>
            <a-switch v-model="useAllFeeds" />
            <span class="hint">{{ useAllFeeds ? '全部订阅' : `已选 ${selectedFeedIds.length} 个` }}</span>
          </div>
          <a-select
            v-model="selectedFeedIds"
            :disabled="useAllFeeds"
            multiple
            allow-search
            allow-clear
            :max-tag-count="4"
            placeholder="选择要导出的订阅源"
          >
            <a-option v-for="f in filteredFeeds" :key="f.id" :value="f.id">{{ f.name }}</a-option>
          </a-select>
        </a-space>

        <a-space direction="vertical" fill>
          <div class="row">
            <span class="label">导出格式</span>
            <a-checkbox-group v-model="formats">
              <a-checkbox value="pdf">PDF</a-checkbox>
              <a-checkbox value="docx">WORD</a-checkbox>
              <a-checkbox value="md">Markdown</a-checkbox>
              <a-checkbox value="json">JSON</a-checkbox>
              <a-checkbox value="csv">CSV</a-checkbox>
            </a-checkbox-group>
          </div>

          <div class="grid">
            <a-input-number v-model="pageCount" :min="1" :max="10000" size="small" placeholder="导出页数" />
            <a-input-number v-model="pageSize" :min="1" :max="10" size="small" placeholder="每页数量" />
            <a-input v-model="zipFilename" size="small" placeholder="导出文件名（可选）" />
          </div>

          <div class="row">
            <a-checkbox v-model="addTitle">添加标题</a-checkbox>
            <a-checkbox v-model="removeImages">移除图片</a-checkbox>
            <a-checkbox v-model="removeLinks">移除链接</a-checkbox>
          </div>
        </a-space>

        <div class="toolbar">
          <a-button type="primary" :loading="exporting" @click="submitExport">开始导出文件</a-button>
          <a-button :loading="linkExporting" @click="openLinksModal">批量导出链接</a-button>
        </div>
      </a-space>
    </a-card>

    <a-card :bordered="false" class="records-card">
      <template #title>导出记录</template>
      <template #extra>
        <a-space>
          <a-tag color="arcoblue">{{ activeExportKey }}</a-tag>
          <a-button size="small" :loading="recordsLoading" @click="loadRecords()">刷新</a-button>
        </a-space>
      </template>
      <a-table :data="records" :loading="recordsLoading" :pagination="false" row-key="filename">
        <a-table-column title="文件名" data-index="filename" />
        <a-table-column title="大小" :width="120">
          <template #cell="{ record }">{{ formatFileSize(record.size) }}</template>
        </a-table-column>
        <a-table-column title="时间" :width="180">
          <template #cell="{ record }">{{ formatDateTime(record.modified_time || record.created_time) }}</template>
        </a-table-column>
        <a-table-column title="操作" :width="160">
          <template #cell="{ record }">
            <a-space>
              <a-button size="mini" type="outline" @click="downloadRecord(record)">下载</a-button>
              <a-button size="mini" status="danger" @click="deleteRecord(record)">删除</a-button>
            </a-space>
          </template>
        </a-table-column>
      </a-table>
    </a-card>

    <a-modal
      v-model:visible="linksVisible"
      title="批量链接导出"
      :footer="false"
      width="860px"
      unmount-on-close
    >
      <a-space direction="vertical" fill>
        <div class="toolbar">
          <a-input-number v-model="linkLimit" :min="10" :max="2000" size="small" placeholder="导出链接数量" />
          <a-input
            v-model="linkSearch"
            size="small"
            allow-clear
            placeholder="按关键词筛选文章（可选）"
          />
          <a-button size="small" :loading="linkExporting" @click="generateLinks">重新生成</a-button>
          <a-button size="small" type="primary" @click="copyLinks">复制全部链接</a-button>
        </div>
        <a-textarea v-model="linksText" :auto-size="{ minRows: 14, maxRows: 24 }" />
      </a-space>
    </a-modal>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { Modal } from '@arco-design/web-vue'
import { getChannelArticles, getChannelFeeds } from '@/api/channels'
import { DeleteExportRecords, exportArticles, getExportRecords } from '@/api/tools'
import { notifyError, notifyInfo, notifySuccess } from '@/utils/notify'

type FeedItem = { id: string; name: string }

const feeds = ref<FeedItem[]>([])
const feedsLoading = ref(false)
const feedKw = ref('')
const useAllFeeds = ref(true)
const selectedFeedIds = ref<string[]>([])

const formats = ref<string[]>(['pdf', 'docx', 'json', 'csv'])
const pageCount = ref(10)
const pageSize = ref(10)
const zipFilename = ref('')
const addTitle = ref(true)
const removeImages = ref(false)
const removeLinks = ref(false)
const exporting = ref(false)

const records = ref<any[]>([])
const recordsLoading = ref(false)
const activeExportKey = ref('all_subscriptions')

const linksVisible = ref(false)
const linkExporting = ref(false)
const linkLimit = ref(200)
const linkSearch = ref('')
const linksText = ref('')

const filteredFeeds = computed(() => {
  const kw = String(feedKw.value || '').trim().toLowerCase()
  if (!kw) return feeds.value
  return feeds.value.filter((x) => `${x.name || ''} ${x.id || ''}`.toLowerCase().includes(kw))
})

const exportFeedIds = computed(() => {
  if (useAllFeeds.value) return feeds.value.map((x) => x.id).filter(Boolean)
  return selectedFeedIds.value.filter(Boolean)
})

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

const loadFeeds = async () => {
  feedsLoading.value = true
  try {
    const res: any = await getChannelFeeds({ limit: 1000, offset: 0 })
    const list = (res?.list || []).map((x: any) => ({ id: String(x.id || ''), name: String(x.name || x.mp_name || x.id || '') }))
    feeds.value = list.filter((x: FeedItem) => !!x.id)
    if (!selectedFeedIds.value.length && feeds.value.length) {
      selectedFeedIds.value = [feeds.value[0].id]
    }
  } catch (e: any) {
    notifyError(e?.message || '获取订阅源失败')
  } finally {
    feedsLoading.value = false
  }
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

const loadRecords = async (key?: string) => {
  const targetKey = String(key || activeExportKey.value || '').trim() || 'all_subscriptions'
  activeExportKey.value = targetKey
  recordsLoading.value = true
  try {
    const res: any = await getExportRecords({ export_key: targetKey })
    const list = Array.isArray(res) ? res : res?.data || []
    records.value = list
  } catch (e: any) {
    records.value = []
    notifyError(e?.message || '读取导出记录失败')
  } finally {
    recordsLoading.value = false
  }
}

const submitExport = async () => {
  if (!formats.value.length) {
    notifyInfo('请至少选择一种导出格式')
    return
  }
  if (!useAllFeeds.value && !exportFeedIds.value.length) {
    notifyInfo('请先选择要导出的订阅源')
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
      add_title: !!addTitle.value,
      remove_images: !!removeImages.value,
      remove_links: !!removeLinks.value,
      format: formats.value,
      zip_filename: String(zipFilename.value || '').trim()
    })
    notifySuccess('导出任务已启动')
    await loadRecords(key)
  } catch (e: any) {
    notifyError(e?.message || '导出失败')
  } finally {
    exporting.value = false
  }
}

const downloadRecord = (record: any) => {
  if (!record?.download_url) {
    notifyInfo('下载链接不可用')
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
        notifySuccess('删除成功')
      } catch (e: any) {
        notifyError(e?.message || '删除失败')
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
    if (!useAllFeeds.value) {
      params.mp_ids = exportFeedIds.value
    }
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
    notifyInfo('请先选择订阅源')
    return
  }
  linkExporting.value = true
  try {
    const urls = await buildArticleLinkList()
    linksText.value = urls.join('\n')
    notifySuccess(`已生成 ${urls.length} 条链接`)
  } catch (e: any) {
    notifyError(e?.message || '生成链接失败')
  } finally {
    linkExporting.value = false
  }
}

const openLinksModal = async () => {
  linksVisible.value = true
  if (!linksText.value.trim()) {
    await generateLinks()
  }
}

const copyLinks = async () => {
  const text = String(linksText.value || '').trim()
  if (!text) {
    notifyInfo('当前没有可复制的链接')
    return
  }
  try {
    await navigator.clipboard.writeText(text)
    notifySuccess('链接已复制到剪贴板')
  } catch {
    notifyError('复制失败，请手动复制')
  }
}

onMounted(async () => {
  await loadFeeds()
  await loadRecords('all_subscriptions')
})
</script>

<style scoped>
.article-export-page {
  padding: 12px;
}

.records-card {
  margin-top: 12px;
}

.toolbar {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.feed-search {
  width: 220px;
}

.row {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}

.label {
  font-size: 13px;
  color: var(--color-text-2);
}

.hint {
  color: var(--color-text-3);
  font-size: 12px;
}

.grid {
  display: grid;
  grid-template-columns: 140px 140px minmax(220px, 1fr);
  gap: 8px;
}

@media (max-width: 980px) {
  .grid {
    grid-template-columns: 1fr;
  }
}
</style>
