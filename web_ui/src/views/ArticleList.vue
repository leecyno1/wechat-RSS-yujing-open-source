<template>
  <a-layout class="article-list">
    <a-layout-sider 
      width="280" 
      :style="{background: '#fff', padding: '0', borderRight: '1px solid #eee', display: 'flex', flexDirection: 'column'}"
    >
      <a-card 
        :bordered="false" 
        title="公众号列表"
        :headStyle="{padding: '12px 16px', borderBottom: '1px solid #eee', position: 'sticky', top: 0, background: '#fff', zIndex: 1}"
      >
        <div style="display: flex; flex-direction: column; height: calc(100vh - 150px); background: #fff">
          <div style="flex: 1; overflow: auto">
            <a-list
              :data="mpList"
              :loading="mpLoading"
              bordered
            >
              <template #item="{item, index}">
                <a-list-item 
                  @click="handleMpClick(item.id)"
                  :class="{'active-mp': activeMpId === item.id}"
                  style="padding: 12px 16px; cursor: pointer;"
                >
                  <a-typography-text :ellipsis="{rows:1}" strong>
                    {{index + 1}}. {{item.name || item.mp_name}}
                  </a-typography-text>
                </a-list-item>
              </template>
            </a-list>
          </div>
          
          <div style="padding: 12px 16px; border-top: 1px solid #eee; background: #fff">
            <a-pagination
              v-model:current="mpPagination.current"
              v-model:page-size="mpPagination.pageSize"
              :total="mpPagination.total"
              :page-size-options="mpPagination.pageSizeOptions"
              show-total
              show-jumper
              @change="handleMpPageChange"
            />
          </div>
        </div>
      </a-card>
    </a-layout-sider>
    
    <a-layout-content :style="{padding: '20px'}">
    <a-page-header
      title="文章列表"
      subtitle="管理您的公众号订阅内容"
      :show-back="false"
    >
      <template #extra>
        <a-space>
          <a-button type="primary" @click="showAddModal">
            <template #icon><icon-plus /></template>
            添加订阅
          </a-button>
          <a-button @click="refresh">
            <template #icon><icon-refresh /></template>
            刷新
          </a-button>
        </a-space>
      </template>
    </a-page-header>

    <a-card>
      <div class="search-bar">
        <a-input-search
          v-model="searchText"
          placeholder="搜索文章标题"
          @search="handleSearch"
          allow-clear
        />
      </div>

      <a-table
        :columns="columns"
        :data="articles"
        :loading="loading"
        :pagination="pagination"
        @page-change="handlePageChange"
        row-key="id"
      >
        <template #status="{ record }">
          <a-tag :color="statusColorMap[record.status]">
            {{ statusTextMap[record.status] }}
          </a-tag>
        </template>
        <template #actions="{ record }">
          <a-button type="text" @click="editArticle(record.id)">
            编辑
          </a-button>
          <a-button type="text" status="danger" @click="deleteArticle(record.id)">
            删除
          </a-button>
        </template>
      </a-table>
    </a-card>
    </a-layout-content>
  </a-layout>
</template>

<script setup lang="ts">
import { ref, onMounted, h } from 'vue'
import { getArticles } from '@/api/article'
import { getSubscriptions ,UpdateMps} from '@/api/subscription'
import { Message } from '@arco-design/web-vue'
import { formatDateTime } from '@/utils/date'
import router from '@/router'

const articles = ref([])
const loading = ref(false)
const mpList = ref([])
const mpLoading = ref(false)
const activeMpId = ref('')
const mpPagination = ref({
  current: 1,
  pageSize: 10,
  total: 0,
  showPageSize: true,
  pageSizeOptions: [10, 20, 50]
})
const searchText = ref('')
const filterStatus = ref('')

const pagination = ref({
  current: 1,
  pageSize: 10,
  total: 0,
  showTotal: true,
  showJumper: true,
  showPageSize: true,
  pageSizeOptions: [10, 20, 50]
})

const statusTextMap = {
  published: '已发布',
  draft: '草稿',
  deleted: '已删除'
}

const statusColorMap = {
  published: 'green',
  draft: 'orange',
  deleted: 'red'
}

const columns = [
  {
    title: '文章标题',
    dataIndex: 'title',
    width: '70%',
    ellipsis: true,
    render: ({ record }) => h('a', { 
      href: record.url || '#',
      target: '_blank',
      style: { color: 'var(--color-text-1)' }
    }, record.title)
  },
  {
    title: '发布时间',
    dataIndex: 'created_at',
    width: '30%',
    render: ({ record }) => h('span', 
      { style: { color: 'var(--color-text-3)', fontSize: '12px' } },
      formatDateTime(record.created_at)
    )
  }
]

const handleMpPageChange = (page: number) => {
  mpPagination.value.current = page
  fetchMpList()
}

const handleMpClick = (mpId: string) => {
  activeMpId.value = mpId
  pagination.value.current = 1
  fetchArticles()
}

const fetchArticles = async () => {
  loading.value = true
  try {
    console.log('请求参数:', {
      page: pagination.value.current - 1,
      pageSize: pagination.value.pageSize,
      search: searchText.value,
      status: filterStatus.value,
      mp_id: activeMpId.value
    })
    
    const res = await getArticles({
      page: pagination.value.current - 1,
      pageSize: pagination.value.pageSize,
      search: searchText.value,
      status: filterStatus.value,
      mp_id: activeMpId.value
    })
    
    // 确保数据包含必要字段
    articles.value = (res.list || []).map(item => ({
      ...item,
      mp_name: item.mp_name || item.account_name || '未知公众号',
      publish_time: item.publish_time || item.create_time || '-',
      url: "https://mp.weixin.qq.com/s/"+item.id 
    }))
    pagination.value.total = res.total || 0
  } catch (error) {
    console.error('获取文章列表错误:', error)
    Message.error(error.message)
  } finally {
    loading.value = false
  }
}

const handlePageChange = (page: number) => {
  pagination.value.current = page
  fetchArticles()
}

const handleSearch = () => {
  pagination.value.current = 1
  fetchArticles()
}

const refresh = () => {
  UpdateMps(activeMpId.value).then(() => {
    Message.success('刷新成功')
  })
  fetchArticles()
}

const showAddModal = () => {
  router.push('/add-subscription')
}

const handleAddSuccess = () => {
  fetchArticles()
}

const editArticle = (id: number) => {
  // 编辑逻辑
}

const deleteArticle = (id: number) => {
  // 删除逻辑
}

onMounted(() => {
  console.log('组件挂载，开始获取数据')
  fetchMpList().then(() => {
    console.log('公众号列表获取完成')
    fetchArticles()
  }).catch(err => {
    console.error('初始化失败:', err)
  })
})

const fetchMpList = async () => {
  mpLoading.value = true
  try {
    const res = await getSubscriptions({
      page: mpPagination.value.current - 1,
      pageSize: mpPagination.value.pageSize
    })
    
      mpList.value = res.list.map(item => ({
        id: item.id || item.mp_id,
        name: item.name || item.mp_name,
        article_count: item.article_count || 0
      }))
      mpPagination.value.total = res.total || 0
  } catch (error) {
    console.error('获取公众号列表错误:', error)
    Message.error(error.message)
  } finally {
    mpLoading.value = false
  }
}
</script>

<style scoped>
.article-list {
  height: 100vh;
}

.a-layout-sider {
  overflow: auto;
}

.a-list-item {
  cursor: pointer;
  padding: 12px 16px;
  transition: all 0.2s;
}

.a-list-item:hover {
  background-color: var(--color-fill-2);
}

.active-mp {
  background-color: var(--color-primary-light-1);
}

.search-bar {
  display: flex;
  margin-bottom: 20px;
}

@media (max-width: 768px) {
  .a-layout-sider {
    width: 100% !important;
    max-width: 100%;
  }
  
  .a-layout {
    flex-direction: column;
  }
}
</style>