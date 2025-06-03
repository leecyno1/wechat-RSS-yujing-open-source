<template>
  <a-page-header
    title="系统信息"
    :sub-title="`版本: ${sysInfo.version}`"
  >
   
      <a-card :bordered="false" class="sys-info-card">
        <a-descriptions bordered :column="{ xs: 1, sm: 1, md: 1, lg: 2 }">
        <a-descriptions-item label="操作系统">
          <template #label>
            <desktop-outlined /> 操作系统
          </template>
          {{ sysInfo.os.name }}
        </a-descriptions-item>
        <a-descriptions-item label="系统版本">
          <template #label>
            <code-outlined /> 系统版本
          </template>
          {{ sysInfo.os.version }} ({{ sysInfo.os.release }})
        </a-descriptions-item>
        <a-descriptions-item label="Python版本">
          <template #label>
            <code-outlined /> Python版本
          </template>
          {{ sysInfo.python_version }}
        </a-descriptions-item>
        <a-descriptions-item label="运行时间">
          <template #label>
            <clock-circle-outlined /> 运行时间
          </template>
          {{ formatUptime(sysInfo.uptime) }}
        </a-descriptions-item>
        <a-descriptions-item label="系统架构">
          <template #label>
            <deployment-unit-outlined /> 系统架构
          </template>
          {{ sysInfo.system.node }} / {{ sysInfo.system.machine }} ({{ sysInfo.system.processor }})
        </a-descriptions-item>
        <a-descriptions-item label="API版本">
          <template #label>
            <api-outlined /> API版本
          </template>
          {{ sysInfo.api_version }}
        </a-descriptions-item>
        <a-descriptions-item label="核心版本">
          <template #label>
            <appstore-outlined /> 核心版本
          </template>
          {{ sysInfo.core_version }}
        </a-descriptions-item>
        <a-descriptions-item label="最新版本" v-if="sysInfo.need_update">
          <template #label>
            <cloud-download-outlined /> 最新版本
          </template>
           {{ sysInfo.latest_version }}
          <!-- 添加点击事件 -->
          <a-button 
            type="text" 
            size="small" 
            style="margin-left: 8px"
            @click="openUpdateLink"
          >立即更新</a-button>
        </a-descriptions-item>
      </a-descriptions>
    </a-card>
  </a-page-header>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { getSysInfo } from '@/api/sysInfo'
import type { SysInfo } from '@/api/sysInfo'

const sysInfo = ref<SysInfo>({
        "os": {
            "name": "",
            "version": "",
            "release": ""
        },
        "python_version": "",
        "uptime": 0,
        "system": {
            "node": "",
            "machine": "",
            "processor": ""
        },
        "api_version": "/api/v1/wx",
        "core_version": "",
        "latest_version": "",
        "need_update": true
    })

const formatUptime = (seconds: number): string => {
  const days = Math.floor(seconds / 86400)
  const hours = Math.floor((seconds % 86400) / 3600)
  const minutes = Math.floor((seconds % 3600) / 60)
  return `${days}天 ${hours}小时 ${minutes}分钟`
}

// 定义打开链接的函数
const openUpdateLink = () => {
  window.open('https://github.com/rachelos/we-mp-rss', '_blank')
}

onMounted(async () => {
  sysInfo.value = await getSysInfo()
})
</script>

<style scoped>
.sys-info-container {
  margin-top: 16px;
}

.sys-info-card {
  margin-bottom: 16px;
  border-radius: 8px;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.12);
  transition: all 0.3s ease;
  background: var(--color-bg-2);
  height: 100%;
}

.sys-info-card:hover {
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.16);
  transform: translateY(-2px);
}

.sys-info-card :deep(.ant-card-head) {
  border-bottom: none;
}

.sys-info-card :deep(.ant-descriptions-item-label) {
  display: flex;
  align-items: center;
  gap: 8px;
  font-weight: 500;
}

.sys-info-card :deep(.ant-descriptions-item-content) {
  color: var(--color-text-1);
}

.sys-info-card :deep(.anticon) {
  font-size: 16px;
}

.sys-info-card :deep(.ant-descriptions-row) {
  padding: 12px 0;
}

.sys-info-card :deep(.ant-descriptions-item) {
  padding-bottom: 0;
}
</style>