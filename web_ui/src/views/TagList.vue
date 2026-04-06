<script setup lang="ts">
import { ref, onMounted, onBeforeUnmount } from 'vue'
import { listTags, deleteTag, listTagPlaza, useTagFromPlaza } from '@/api/tagManagement'
import type { Tag } from '@/types/tagManagement'
import type { TagPlazaItem } from '@/api/tagManagement'
import { notifyError, notifySuccess } from '@/utils/notify'
import { pickDefaultChannelLogo } from '@/constants/channelLogos'

const loading = ref(false)
const loadingMore = ref(false)
const tags = ref<Tag[]>([])
const pagination = ref({
  current: 1,
  pageSize: 10,
  total: 0
})
const isMobile = ref(window.innerWidth < 768)
const plazaVisible = ref(false)
const plazaLoading = ref(false)
const plazaUsingId = ref('')
const plazaKeyword = ref('')
const plazaTags = ref<TagPlazaItem[]>([])
const plazaPagination = ref({
  current: 1,
  pageSize: 10,
  total: 0
})

const handleResize = () => {
  isMobile.value = window.innerWidth < 768
}

onMounted(() => {
  window.addEventListener('resize', handleResize)
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', handleResize)
})

const fetchTags = async (isLoadMore = false) => {
  try {
    if (isLoadMore) {
      loadingMore.value = true
    } else {
      loading.value = true
    }
    const res = await listTags({
      offset: (pagination.value.current - 1) * pagination.value.pageSize,
      limit: pagination.value.pageSize
    })
    console.log(res)
    if (isLoadMore) {
      tags.value = [...tags.value, ...(res.list || [])]
    } else {
      tags.value = res.list || []
    }
    pagination.value.total = res.total || 0
  } catch (error) {
    notifyError('获取频道列表失败')
  } finally {
    if (isLoadMore) {
      loadingMore.value = false
    } else {
      loading.value = false
    }
  }
}

const handleDelete = async (id: string) => {
  try {
    await deleteTag(id)
    notifySuccess('删除成功')
    fetchTags()
  } catch (error) {
    notifyError('删除失败')
  }
}


const handlePageChange = (page: number) => {
  pagination.value.current = page
  fetchTags()
}

const fetchTagPlaza = async () => {
  plazaLoading.value = true
  try {
    const res: any = await listTagPlaza({
      offset: (plazaPagination.value.current - 1) * plazaPagination.value.pageSize,
      limit: plazaPagination.value.pageSize,
      keyword: String(plazaKeyword.value || '').trim().slice(0, 100),
    })
    plazaTags.value = res?.list || []
    plazaPagination.value.total = Number(res?.total || 0)
  } catch {
    notifyError('获取频道广场失败')
  } finally {
    plazaLoading.value = false
  }
}

const openTagPlaza = async () => {
  plazaVisible.value = true
  plazaPagination.value.current = 1
  await fetchTagPlaza()
}

const searchTagPlaza = async () => {
  plazaPagination.value.current = 1
  await fetchTagPlaza()
}

const resetTagPlazaSearch = async () => {
  plazaKeyword.value = ''
  plazaPagination.value.current = 1
  await fetchTagPlaza()
}

const handlePlazaPageChange = (page: number) => {
  plazaPagination.value.current = page
  fetchTagPlaza()
}

const useTag = async (tag: TagPlazaItem) => {
  if (!tag?.id || plazaUsingId.value) return
  plazaUsingId.value = tag.id
  try {
    const res: any = await useTagFromPlaza(tag.id)
    notifySuccess(res?.message || '已添加到我的频道')
    await fetchTags()
    await fetchTagPlaza()
  } catch {
    notifyError('使用频道失败')
  } finally {
    plazaUsingId.value = ''
  }
}

const tagCover = (tag: Tag) => {
  const cover = String(tag?.cover || '').trim()
  if (cover) return cover
  return pickDefaultChannelLogo(String(tag?.name || ''))
}

onMounted(() => {
  fetchTags()
})
</script>

<template>
  <div class="tag-list">
    <a-page-header title="频道管理" subtitle="管理频道（用于分组筛选公众号）">
      <template #extra>
        <a-button type="outline" size="small" @click="openTagPlaza">频道广场</a-button>
      </template>
    </a-page-header>

    <a-card>
      <a-table
        v-if="!isMobile"
        :loading="loading"
        :data="tags"
        :pagination="pagination"
        @page-change="handlePageChange"
      >
        <template #columns>
          <a-table-column title="封面" :width="80">
            <template #cell="{ record }">
              <a-avatar :size="36" :image-url="tagCover(record)">
                <img :src="tagCover(record)" />
              </a-avatar>
            </template>
          </a-table-column>
          <a-table-column title="频道名称" data-index="name" />
          <a-table-column title="状态" data-index="status">
            <template #cell="{ record }">
              <a-tag v-if="record.status === 1" color="green">启用</a-tag>
              <a-tag v-else color="red">禁用</a-tag>
            </template>
          </a-table-column>
          <a-table-column title="创建时间" data-index="created_at" />
          <a-table-column title="操作">
            <template #cell="{ record }">
              <a-space>
                <a-link type="primary" target="_blank" :href="`/feed/tag/${record.id}.rss`">
                  订阅
                </a-link>
                <a-button type="text" @click="$router.push(`/tags/edit/${record.id}`)">
                  编辑
                </a-button>
                <a-popconfirm content="确认删除该频道？" @ok="handleDelete(record.id)">
                  <a-button type="text" status="danger">删除</a-button>
                </a-popconfirm>
              </a-space>
            </template>
          </a-table-column>
        </template>
      </a-table>

      <a-list
        v-else
        :loading="loading"
        :loading-more="loadingMore"
        :data="tags"
        :pagination="pagination"
        @page-change="handlePageChange"
      >
        <template #item="{ item }">
          <a-list-item>
            <a-list-item-meta>
              <template #title>
                <a-avatar :size="24" :image-url="tagCover(item)" style="margin-right: 8px">
                  <img :src="tagCover(item)" />
                </a-avatar>
                {{ item.name }}
                <a-tag v-if="item.status === 1" color="green" size="small">启用</a-tag>
                <a-tag v-else color="red" size="small">禁用</a-tag>
              </template>
              <template #description>
                创建时间: {{ item.created_at }}
              </template>
            </a-list-item-meta>
            <a-space>
              <a-button type="text" size="small" @click="$router.push(`/tags/edit/${item.id}`)">
                编辑
              </a-button>
              <a-popconfirm content="确认删除该频道？" @ok="handleDelete(item.id)">
                <a-button type="text" status="danger" size="small">删除</a-button>
              </a-popconfirm>
            </a-space>
          </a-list-item>
        </template>
      <template #footer>
          <div v-if="pagination.current * pagination.pageSize < pagination.total" class="load-more">
            <a-button 
              type="primary"
              :loading="loadingMore"
              @click="() => {
                pagination.current++
                fetchTags(true)
              }"
            >
              加载更多
            </a-button>
              <div class="total-count">
                共 {{ pagination.total }} 条
              </div>
            </div>
        </template>
      </a-list>
    </a-card>

    <a-modal
      v-model:visible="plazaVisible"
      title="频道广场"
      width="980px"
      :footer="false"
      unmount-on-close
    >
      <div class="plaza-toolbar">
        <a-input
          v-model="plazaKeyword"
          allow-clear
          :max-length="100"
          placeholder="搜索频道名称/简介"
          style="max-width: 320px"
          @press-enter="searchTagPlaza"
        />
        <a-space size="small">
          <a-button size="small" type="primary" @click="searchTagPlaza">
            搜索
          </a-button>
          <a-button size="small" @click="resetTagPlazaSearch">
            重置
          </a-button>
        </a-space>
      </div>

      <a-table
        :loading="plazaLoading"
        :data="plazaTags"
        :pagination="plazaPagination"
        @page-change="handlePlazaPageChange"
      >
        <template #columns>
          <a-table-column title="封面" :width="80">
            <template #cell="{ record }">
              <a-avatar :size="36" :image-url="tagCover(record)">
                <img :src="tagCover(record)" />
              </a-avatar>
            </template>
          </a-table-column>
          <a-table-column title="频道" data-index="name" />
          <a-table-column title="创建者" :width="150">
            <template #cell="{ record }">
              {{ record.creator_display || '未知用户' }}
            </template>
          </a-table-column>
          <a-table-column title="订阅数" :width="90">
            <template #cell="{ record }">
              {{ Number(record.mp_count || 0) }}
            </template>
          </a-table-column>
          <a-table-column title="简介" data-index="intro" />
          <a-table-column title="操作" :width="120">
            <template #cell="{ record }">
              <a-button
                size="small"
                type="primary"
                :loading="plazaUsingId === record.id"
                @click="useTag(record)"
              >
                使用频道
              </a-button>
            </template>
          </a-table-column>
        </template>
      </a-table>
    </a-modal>
  </div>
</template>

<style scoped>
.tag-list {
  padding: 16px;
}

.plaza-toolbar {
  margin-bottom: 10px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  flex-wrap: wrap;
}

.load-more{
    width: 120px;
    margin: 0px auto;
    text-align: center;
}
</style>
