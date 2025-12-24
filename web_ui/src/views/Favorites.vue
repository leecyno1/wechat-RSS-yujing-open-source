<template>
  <a-card :bordered="false" title="我的收藏">
    <a-space style="margin-bottom: 12px;">
      <a-button @click="refresh" :loading="loading">
        <template #icon><icon-refresh /></template>
        刷新
      </a-button>
    </a-space>

    <a-table :data="items" :loading="loading" :pagination="pagination" row-key="id"
      @page-change="handlePageChange" @page-size-change="handlePageSizeChange">
      <a-table-column title="标题" data-index="title" :ellipsis="true">
        <template #cell="{ record }">
          <a-link :href="record.url" target="_blank">{{ record.title }}</a-link>
        </template>
      </a-table-column>
      <a-table-column title="公众号" data-index="mp_name" :width="140" :ellipsis="true" />
      <a-table-column title="发布时间" data-index="publish_time" :width="160">
        <template #cell="{ record }">
          {{ formatTimestamp(record.publish_time) }}
        </template>
      </a-table-column>
      <a-table-column title="收藏时间" data-index="favorited_at" :width="180" />
      <a-table-column title="操作" :width="120">
        <template #cell="{ record }">
          <a-button type="text" status="danger" @click="remove(record.id)">
            <template #icon><icon-delete /></template>
          </a-button>
        </template>
      </a-table-column>
    </a-table>
  </a-card>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { Message } from '@arco-design/web-vue'
import { formatTimestamp } from '@/utils/date'
import { listFavorites, unfavoriteArticle } from '@/api/favorites'

const loading = ref(false)
const items = ref<any[]>([])
const pagination = ref({
  current: 1,
  pageSize: 20,
  total: 0,
  showTotal: true,
  showJumper: true,
  showPageSize: true,
  pageSizeOptions: [10, 20, 50, 100]
})

const refresh = async () => {
  loading.value = true
  try {
    const offset = (pagination.value.current - 1) * pagination.value.pageSize
    const res = await listFavorites({ offset, limit: pagination.value.pageSize })
    items.value = res.list || []
    pagination.value.total = res.total || 0
  } catch (e) {
    Message.error(String(e))
  } finally {
    loading.value = false
  }
}

const handlePageChange = (page: number) => {
  pagination.value.current = page
  refresh()
}
const handlePageSizeChange = (pageSize: number) => {
  pagination.value.pageSize = pageSize
  pagination.value.current = 1
  refresh()
}

const remove = async (articleId: string) => {
  try {
    await unfavoriteArticle(articleId)
    Message.success('已取消收藏')
    refresh()
  } catch (e) {
    Message.error(String(e))
  }
}

onMounted(() => {
  refresh()
})
</script>

