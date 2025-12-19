<script setup lang="ts">
import { ref, onMounted, onBeforeUnmount } from 'vue'
import { listMessageTasks, deleteMessageTask,FreshJobApi,FreshJobByIdApi,RunMessageTask } from '@/api/messageTask'
import type { MessageTask } from '@/types/messageTask'
import { useRouter } from 'vue-router'
import { Message, Modal } from '@arco-design/web-vue'
import ResponsiveTable from '@/components/ResponsiveTable.vue'
import TaskList from '@/components/TaskList.vue'
import { 
  getNotificationEnabled, 
  enableBrowserNotification, 
  disableBrowserNotification,
  initBrowserNotification 
} from '@/utils/browserNotification'

const isMobile = ref(window.innerWidth < 768)
const handleResize = () => {
  isMobile.value = window.innerWidth < 768
}

// 浏览器通知状态
const browserNotificationEnabled = ref(false)

onMounted(() => {
  window.addEventListener('resize', handleResize)
  // 初始化浏览器通知状态
  browserNotificationEnabled.value = getNotificationEnabled()
  initBrowserNotification()
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', handleResize)
})
const parseCronExpression = (exp: string) => {
  const parts = exp.split(' ')
  if (parts.length !== 5) return exp
  
  const [minute, hour, day, month, week] = parts
  
  let result = ''
  
  // 解析分钟
  if (minute === '*') {
    result += '每分钟'
  } else if (minute.includes('/')) {
    const [_, interval] = minute.split('/')
    result += `每${interval}分钟`
  } else {
    result += `在${minute}分`
  }
  
  // 解析小时
  if (hour === '*') {
    result += '每小时'
  } else if (hour.includes('/')) {
    const [_, interval] = hour.split('/')
    result += `每${interval}小时`
  } else {
    result += ` ${hour}时`
  }
  
  // 解析日期
  if (day === '*') {
    result += ' 每天'
  } else if (day.includes('/')) {
    const [_, interval] = day.split('/')
    result += ` 每${interval}天`
  } else {
    result += ` ${day}日`
  }
  
  // 解析月份
  if (month === '*') {
    result += ' 每月'
  } else if (month.includes('/')) {
    const [_, interval] = month.split('/')
    result += ` 每${interval}个月`
  } else {
    result += ` ${month}月`
  }
  
  // 解析星期
  if (week !== '*') {
    result += ` 星期${week}`
  }
  
  return result || exp
}

const router = useRouter()
const loading = ref(false)
const taskList = ref<MessageTask[]>([])
const pagination = ref({
  current: 1,
  pageSize: 10,
  total: 0
})

const fetchTaskList = async () => {
  loading.value = true
  try {
    const res = await listMessageTasks({
      offset: (pagination.value.current - 1) * pagination.value.pageSize,
      limit: pagination.value.pageSize
    })
    taskList.value = res.list
    pagination.value.total = res.total
  } finally {
    loading.value = false
  }
}

const handlePageChange = (page: number) => {
  pagination.value.current = page
  fetchTaskList()
}

const handleLoadMore = async () => {
    loading.value = true
    try {
      pagination.value.current += 1
      const res = await listMessageTasks({
        offset: (pagination.value.current - 1) * pagination.value.pageSize,
        limit: pagination.value.pageSize
      })
      taskList.value = [...taskList.value, ...res.list]
      pagination.value.total = res.total
    } finally {
      loading.value = false
    }
}

const handleAdd = () => {
  router.push('/message-tasks/add')
}
const FreshJob = () => {
  FreshJobApi().then((data) => {
    console.log("刷新任务")
    Message.success(data.message||"刷新任务成功")
  })
}

// 切换浏览器通知
const toggleNotification = async () => {
  if (browserNotificationEnabled.value) {
    disableBrowserNotification()
    browserNotificationEnabled.value = false
    Message.success('浏览器通知已关闭')
  } else {
    const success = await enableBrowserNotification()
    if (success) {
      browserNotificationEnabled.value = true
      Message.success('浏览器通知已开启，将每分钟检查新文章')
    } else {
      Message.error('开启浏览器通知失败')
    }
  }
}

const handleEdit = (id: number) => {
  router.push(`/message-tasks/edit/${id}`)
}

const handleView = (id: number) => {
  router.push(`/message-tasks/detail/${id}`)
}

const handleDelete = async (id: number) => {
  Modal.confirm({
    title: '确认删除',
    content: '确定要删除这条消息任务吗？删除后无法恢复',
    okText: '确认',
    cancelText: '取消',
    onOk: async () => {
      try {
        await deleteMessageTask(id)
        Message.success('删除成功')
        fetchTaskList()
      } catch (error) {
        console.error(error)
        Message.error('删除失败')
      }
    }
  })
}
const runTask = async (id: number,isTest:boolean=false) => {
  Modal.confirm({
    title: '确认执行',
    content: '确定要执行这条消息任务吗？',
    okText: '确认',
    cancelText: '取消',
    onOk: async () => {
      try {
        let res = await RunMessageTask(id,isTest)
        Message.success(res?.message||'执行成功')
      } catch (error) {
        console.error(error)
        Message.error('执行失败')
        console.log(error)
      }
    }
  })
}

onMounted(() => {
  fetchTaskList()
})
</script>

<template>
  <a-spin :loading="loading">
    <div class="message-task-list">
      <div class="header">
        <h2>消息任务列表</h2>
        <a-tooltip :content="browserNotificationEnabled ? '点击关闭浏览器通知' : '开启后有新文章时浏览器标题会闪烁并播放提示音'" class="desktop-only">
          <a-button class="desktop-only"
            :type="browserNotificationEnabled ? 'primary' : 'outline'" 
            :status="browserNotificationEnabled ? 'success' : 'normal'"
            @click="toggleNotification"
          >
            <template #icon>
              <icon-notification />
            </template>
            {{ browserNotificationEnabled ? '通知已开启' : '开启浏览器通知' }}
          </a-button>
        </a-tooltip>
        <a-tooltip content="点击应用按钮后任务才会生效">
          <a-button type="primary" @click="FreshJob">应用</a-button>
        </a-tooltip>
        <a-button type="primary" @click="handleAdd">添加消息任务</a-button>
      </div>
      <a-alert type="info" closable>
        注意：只有添加了任务消息才会定时执行更新任务，点击应用按钮后任务才会生效
      </a-alert>

      <TaskList
      :task-list="taskList"
      :loading="loading"
      :pagination="pagination"
      :is-mobile="isMobile"
      @page-change="handlePageChange"
      @load-more="handleLoadMore"
    >
      <template #table-columns>
        <a-table-column title="名称" data-index="name" ellipsis :width="200"/>
        <a-table-column title="cron表达式">
          <template #cell="{ record }">
            {{ parseCronExpression(record.cron_exp) }}
          </template>
        </a-table-column>
        <a-table-column title="类型" :width="100">
          <template #cell="{ record }">
            <a-tag :color="record.message_type === 1 ? 'green' : 'red'">
              {{ record.message_type === 1 ? 'WeekHook' : 'Message' }}
            </a-tag>
          </template>
        </a-table-column>
        <a-table-column title="状态" :width="100">
          <template #cell="{ record }">
            <a-tag :color="record.status === 1 ? 'green' : 'red'">
              {{ record.status === 1 ? '启用' : '禁用' }}
            </a-tag>
          </template>
        </a-table-column>
      </template>

      <template #list-item-meta="{ item }">
        <a-list-item-meta>
          <template #title>
            {{ item.name }}
          </template>
          <template #description>
            <div>{{ parseCronExpression(item.cron_exp) }}</div>
            <div>
              <a-tag :color="item.message_type === 1 ? 'green' : 'red'">
                {{ item.message_type === 1 ? 'WeekHook' : 'Message' }}
              </a-tag>
              <a-tag :color="item.status === 1 ? 'green' : 'red'">
                {{ item.status === 1 ? '启用' : '禁用' }}
              </a-tag>
            </div>
          </template>
        </a-list-item-meta>
      </template>

      <template #actions="{ record }">
        <a-space>
          <a-button size="mini" type="primary" @click="handleEdit(record.id)">编辑</a-button>
          <a-tooltip content="点击测试消息任务">
            <a-button size="mini" type="dashed" @click="runTask(record.id, true)">测试</a-button>
          </a-tooltip>
          <a-tooltip content="执行更新任务">
            <a-button size="mini" type="dashed" @click="runTask(record.id)">执行</a-button>
          </a-tooltip>
          <a-button size="mini" status="danger" @click="handleDelete(record.id)">删除</a-button>
        </a-space>
      </template>

      <template #mobile-actions="{ record }">
        <a-space>
          <a-button size="mini" type="primary" @click="handleEdit(record.id)">编辑</a-button>
          <a-button size="mini" type="dashed" @click="runTask(record.id, true)">测试</a-button>
          <a-button size="mini" type="dashed" @click="runTask(record.id)">执行</a-button>
          <a-button size="mini" status="danger" @click="handleDelete(record.id)">删除</a-button>
        </a-space>
      </template>
    </TaskList>
    </div>
  </a-spin>
</template>

<style scoped>
.message-task-list {
  padding: 20px;
}

.header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
}

.header h2 {
  flex: 1;
}

.header .arco-btn {
  margin-left: 10px;
}

h2 {
  margin: 0;
  color: var(--color-text-1);
}


/* 移动端列表样式 */
.a-list {
  margin-top: 16px;
}

.a-list-item {
  padding: 12px 16px;
  margin-bottom: 8px;
  background-color: var(--color-bg-2);
  border-radius: 4px;
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.1);
  transition: all 0.2s;
}

.a-list-item:hover {
  background-color: var(--color-bg-3);
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
}

.a-list-item-meta-title {
  font-weight: 500;
  margin-bottom: 4px;
}

.a-list-item-meta-description {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.a-list-item-meta-description .arco-tag {
  margin-right: 8px;
}

.a-list-item-extra {
  display: flex;
  gap: 8px;
}

/* 移动端隐藏桌面端元素 */
.desktop-only {
  display: block;
}

@media (max-width: 768px) {
  .desktop-only {
    display: none !important;
  }
}
</style>