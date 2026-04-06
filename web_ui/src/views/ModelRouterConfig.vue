<template>
  <div class="model-router-config">
    <a-card :bordered="false">
      <template #title>模型路由</template>
      <template #extra>
        <a-space>
          <a-button size="small" @click="loadAll" :loading="loading">刷新</a-button>
          <a-button size="small" type="primary" @click="saveAll" :loading="saving">保存</a-button>
        </a-space>
      </template>

      <a-space direction="vertical" fill size="large">
        <a-alert type="info" show-icon>
          摘要默认走大模型路由，关键信息默认走小模型路由。所有通道均按 OpenAI 兼容接口配置。
        </a-alert>

        <div class="switch-row">
          <a-space>
            <span class="label">启用模型路由</span>
            <a-switch v-model="form.routerEnable" />
          </a-space>
          <a-space>
            <span class="label">自动 AI 摘要</span>
            <a-switch v-model="form.autoAiSummary" />
          </a-space>
        </div>

        <a-divider orientation="left">摘要（大模型）</a-divider>
        <a-space direction="vertical" fill>
          <a-select v-model="form.summaryMode" size="small" style="width: 220px">
            <a-option value="fallback">fallback（按优先级）</a-option>
            <a-option value="shard">shard（按文章分片）</a-option>
          </a-select>
          <a-textarea
            v-model="form.summaryProfilesJson"
            :auto-size="{ minRows: 6, maxRows: 12 }"
            placeholder='JSON 数组：[{"name":"big-1","provider":"openrouter","api_url":"https://openrouter.ai/api/v1","api_key":"sk-***","model":"anthropic/claude-3.5-sonnet","priority":1}]'
          />
        </a-space>

        <a-divider orientation="left">关键信息（小模型）</a-divider>
        <a-space direction="vertical" fill>
          <a-select v-model="form.keyPointsMode" size="small" style="width: 220px">
            <a-option value="fallback">fallback（按优先级）</a-option>
            <a-option value="shard">shard（按文章分片）</a-option>
          </a-select>
          <a-textarea
            v-model="form.keyPointsProfilesJson"
            :auto-size="{ minRows: 6, maxRows: 12 }"
            placeholder='JSON 数组：[{"name":"small-1","provider":"openrouter","api_url":"https://openrouter.ai/api/v1","api_key":"sk-***","model":"qwen/qwen2.5-7b-instruct","priority":1}]'
          />
        </a-space>

        <a-divider orientation="left">全文拆解（可选）</a-divider>
        <a-space direction="vertical" fill>
          <a-select v-model="form.breakdownMode" size="small" style="width: 220px">
            <a-option value="fallback">fallback（按优先级）</a-option>
            <a-option value="shard">shard（按文章分片）</a-option>
          </a-select>
          <a-textarea
            v-model="form.breakdownProfilesJson"
            :auto-size="{ minRows: 4, maxRows: 10 }"
            placeholder="可留空（为空时默认复用摘要路由）"
          />
        </a-space>
      </a-space>
    </a-card>
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { getConfig, updateConfig } from '@/api/configManagement'
import { notifyError, notifySuccess } from '@/utils/notify'

const loading = ref(false)
const saving = ref(false)

const form = reactive({
  routerEnable: false,
  autoAiSummary: true,
  summaryMode: 'fallback',
  keyPointsMode: 'fallback',
  breakdownMode: 'fallback',
  summaryProfilesJson: '',
  keyPointsProfilesJson: '',
  breakdownProfilesJson: ''
})

const KEY_MAP = {
  routerEnable: 'llm.router.enable',
  autoAiSummary: 'insights.auto_ai_summary',
  summaryMode: 'llm.router.summary.mode',
  keyPointsMode: 'llm.router.key_points.mode',
  breakdownMode: 'llm.router.breakdown.mode',
  summaryProfilesJson: 'llm.router.summary.profiles_json',
  keyPointsProfilesJson: 'llm.router.key_points.profiles_json',
  breakdownProfilesJson: 'llm.router.breakdown.profiles_json'
} as const

const readConfig = async (key: string) => {
  const res: any = await getConfig(key)
  return String(res?.config_value ?? res?.data?.config_value ?? '')
}

const saveConfig = async (key: string, value: any) => {
  await updateConfig(key, {
    config_key: key,
    config_value: typeof value === 'string' ? value : String(value),
    description: ''
  } as any)
}

const loadAll = async () => {
  loading.value = true
  try {
    const [routerEnable, autoAiSummary, summaryMode, keyPointsMode, breakdownMode, summaryProfilesJson, keyPointsProfilesJson, breakdownProfilesJson] =
      await Promise.all([
        readConfig(KEY_MAP.routerEnable),
        readConfig(KEY_MAP.autoAiSummary),
        readConfig(KEY_MAP.summaryMode),
        readConfig(KEY_MAP.keyPointsMode),
        readConfig(KEY_MAP.breakdownMode),
        readConfig(KEY_MAP.summaryProfilesJson),
        readConfig(KEY_MAP.keyPointsProfilesJson),
        readConfig(KEY_MAP.breakdownProfilesJson)
      ])
    form.routerEnable = String(routerEnable).toLowerCase() === 'true'
    form.autoAiSummary = String(autoAiSummary || 'true').toLowerCase() !== 'false'
    form.summaryMode = summaryMode || 'fallback'
    form.keyPointsMode = keyPointsMode || 'fallback'
    form.breakdownMode = breakdownMode || 'fallback'
    form.summaryProfilesJson = summaryProfilesJson || ''
    form.keyPointsProfilesJson = keyPointsProfilesJson || ''
    form.breakdownProfilesJson = breakdownProfilesJson || ''
  } catch (e: any) {
    notifyError(e?.message || '读取模型路由配置失败')
  } finally {
    loading.value = false
  }
}

const ensureJson = (v: string, field: string) => {
  const text = String(v || '').trim()
  if (!text) return true
  try {
    const parsed = JSON.parse(text)
    if (!Array.isArray(parsed)) throw new Error('必须是 JSON 数组')
    return true
  } catch (e: any) {
    notifyError(`${field} 不是有效 JSON：${e?.message || e}`)
    return false
  }
}

const saveAll = async () => {
  if (!ensureJson(form.summaryProfilesJson, '摘要路由')) return
  if (!ensureJson(form.keyPointsProfilesJson, '关键信息路由')) return
  if (!ensureJson(form.breakdownProfilesJson, '拆解路由')) return

  saving.value = true
  try {
    await Promise.all([
      saveConfig(KEY_MAP.routerEnable, form.routerEnable ? 'true' : 'false'),
      saveConfig(KEY_MAP.autoAiSummary, form.autoAiSummary ? 'true' : 'false'),
      saveConfig(KEY_MAP.summaryMode, form.summaryMode),
      saveConfig(KEY_MAP.keyPointsMode, form.keyPointsMode),
      saveConfig(KEY_MAP.breakdownMode, form.breakdownMode),
      saveConfig(KEY_MAP.summaryProfilesJson, form.summaryProfilesJson || '[]'),
      saveConfig(KEY_MAP.keyPointsProfilesJson, form.keyPointsProfilesJson || '[]'),
      saveConfig(KEY_MAP.breakdownProfilesJson, form.breakdownProfilesJson || '')
    ])
    notifySuccess('模型路由配置已保存')
  } catch (e: any) {
    notifyError(e?.message || '保存模型路由配置失败')
  } finally {
    saving.value = false
  }
}

onMounted(loadAll)
</script>

<style scoped>
.model-router-config {
  padding: 12px;
}

.switch-row {
  display: flex;
  align-items: center;
  gap: 20px;
  flex-wrap: wrap;
}

.label {
  color: var(--color-text-2);
  font-size: 13px;
}
</style>
