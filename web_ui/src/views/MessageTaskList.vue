<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { listMessageTasks, deleteMessageTask } from '@/api/messageTask'
import type { MessageTask } from '@/types/messageTask'
import { useRouter } from 'vue-router'

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

const handleAdd = () => {
  router.push('/message-tasks/add')
}

const handleEdit = (id: number) => {
  router.push(`/message-tasks/edit/${id}`)
}

const handleView = (id: number) => {
  router.push(`/message-tasks/detail/${id}`)
}

const handleDelete = async (id: number) => {
  try {
    await deleteMessageTask(id)
    fetchTaskList()
  } catch (error) {
    console.error(error)
  }
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
        <a-button type="primary" @click="handleAdd">添加消息任务</a-button>
      </div>

      <a-table
        :data="taskList"
        :pagination="pagination"
        @page-change="handlePageChange"
      >
        <template #columns>
          <a-table-column title="ID" data-index="id" :width="80" />
          <a-table-column title="名称" data-index="name" ellipsis />
          <a-table-column title="类型" data-index="message_type" ellipsis />
          <a-table-column title="cron表达式" :width="120">
            <template #cell="{ record }">
              {{ parseCronExpression(record.cron_exp) }}
            </template>
          </a-table-column>
          <a-table-column title="状态" :width="100">
            <template #cell="{ record }">
              <a-tag :color="record.status === 1 ? 'green' : 'red'">
                {{ record.status === 1 ? '启用' : '禁用' }}
              </a-tag>
            </template>
          </a-table-column>
          <a-table-column title="操作" :width="200">
            <template #cell="{ record }">
              <a-space>
                <a-button size="mini" type="primary" @click="handleEdit(record.id)">编辑</a-button>
                <a-button size="mini" status="danger" @click="handleDelete(record.id)">删除</a-button>
              </a-space>
            </template>
          </a-table-column>
        </template>
      </a-table>
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

h2 {
  margin: 0;
  color: var(--color-text-1);
}
</style>