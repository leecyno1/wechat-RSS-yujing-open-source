<template>
  <div class="config-page">
    <div class="config-grid">
      <div class="config-left">
        <a-card title="订阅包（新用户默认）" :bordered="false">
          <a-space direction="vertical" fill>
            <a-alert type="info" show-icon>
              新用户注册后自动订阅你设定的平台。保存后即时生效。
            </a-alert>

            <a-form :model="starterForm" layout="vertical">
              <a-form-item label="开启默认订阅包">
                <a-switch v-model="starterForm.enable" />
              </a-form-item>
              <a-form-item label="平台列表（逗号分隔）">
                <a-input v-model="starterForm.platforms" placeholder="wechat,zhihu,xueqiu,toutiao,baijiahao,wsj,bbc" />
              </a-form-item>
              <a-form-item label="每个平台默认订阅数量">
                <a-input-number v-model="starterForm.perPlatform" :min="1" :max="30" />
              </a-form-item>
              <a-form-item label="固定频道ID（可选，逗号分隔）">
                <a-textarea
                  v-model="starterForm.feedIds"
                  :auto-size="{ minRows: 2, maxRows: 5 }"
                  placeholder="MP_WXS_xxx,SRC_xxx"
                />
              </a-form-item>
            </a-form>

            <a-space>
              <a-button type="primary" :loading="savingStarter" @click="saveStarter">保存订阅包</a-button>
              <a-button :loading="loading" @click="loadAll">刷新</a-button>
            </a-space>
          </a-space>
        </a-card>

        <a-card title="多平台自动刷新并发" :bordered="false" class="mt12">
          <a-form :model="sourceForm" layout="vertical">
            <a-form-item label="默认来源并发 workers">
              <a-input-number v-model="sourceForm.defaultWorkers" :min="1" :max="64" />
            </a-form-item>
            <a-form-item label="按平台覆盖（逗号分隔）">
              <a-input
                v-model="sourceForm.byPlatform"
                placeholder="zhihu:4,xueqiu:3,toutiao:3,baijiahao:2,wsj:1,bbc:1,rsshub:3,rss:2"
              />
            </a-form-item>
          </a-form>
          <a-button type="primary" :loading="savingSource" @click="saveSourceWorkers">保存并发配置</a-button>
        </a-card>
      </div>

      <div class="config-right">
        <a-card title="模型路由（已合并）" :bordered="false" class="model-card">
          <a-space direction="vertical" fill>
        <a-alert type="info" show-icon>
          摘要走大模型，关键信息走小模型。此页已合并“模型路由 + 订阅包”，避免重复配置。
        </a-alert>

        <div class="switch-row">
          <a-space>
            <span class="label">启用模型路由</span>
            <a-switch v-model="modelForm.routerEnable" />
          </a-space>
          <a-space>
            <span class="label">自动 AI 摘要</span>
            <a-switch v-model="modelForm.autoAiSummary" />
          </a-space>
          <a-space>
            <span class="label">自动关键信息</span>
            <a-switch v-model="modelForm.autoKeyPoints" />
          </a-space>
          <a-space>
            <span class="label">自动全文拆解</span>
            <a-switch v-model="modelForm.autoBreakdown" />
          </a-space>
          <a-space>
            <span class="label">刷新后预热洞察</span>
            <a-switch v-model="modelForm.prewarmOnUpdate" />
          </a-space>
        </div>

        <div class="switch-row">
          <a-space>
            <span class="label">摘要路由</span>
            <a-select v-model="modelForm.summaryMode" size="small" style="width: 180px">
              <a-option value="fallback">fallback</a-option>
              <a-option value="shard">shard</a-option>
            </a-select>
          </a-space>
          <a-space>
            <span class="label">关键信息路由</span>
            <a-select v-model="modelForm.keyPointsMode" size="small" style="width: 180px">
              <a-option value="fallback">fallback</a-option>
              <a-option value="shard">shard</a-option>
            </a-select>
          </a-space>
          <a-space>
            <span class="label">拆解路由</span>
            <a-select v-model="modelForm.breakdownMode" size="small" style="width: 180px">
              <a-option value="fallback">fallback</a-option>
              <a-option value="shard">shard</a-option>
            </a-select>
          </a-space>
          <a-space>
            <span class="label">Shard失败回退</span>
            <a-switch v-model="modelForm.shardIncludeFallback" />
          </a-space>
          <a-space>
            <span class="label">LLM 最大字符</span>
            <a-input-number v-model="modelForm.maxChars" :min="2000" :max="120000" />
          </a-space>
        </div>

        <a-space>
          <a-button size="small" @click="applyPresetModels">导入预置模型清单</a-button>
          <a-button size="small" @click="clearModelSelections">清空模型选择</a-button>
          <a-button type="primary" size="small" :loading="savingModel" @click="saveModelRouter">保存模型路由</a-button>
        </a-space>

        <div class="providers-grid">
          <a-card v-for="provider in providers" :key="provider.id" size="small" :title="provider.label">
            <a-form layout="vertical">
              <a-form-item label="API Base URL">
                <a-input v-model="provider.apiUrl" placeholder="https://api.example.com/v1" />
              </a-form-item>
              <a-form-item label="API Key">
                <a-input-password v-model="provider.apiKey" placeholder="sk-..." :visibility="true" allow-clear />
              </a-form-item>
              <a-form-item label="大模型（摘要）">
                <a-select
                  v-model="provider.bigSelected"
                  multiple
                  allow-clear
                  allow-create
                  placeholder="选择或输入模型"
                >
                  <a-option v-for="m in provider.bigModels" :key="m" :value="m">{{ m }}</a-option>
                </a-select>
              </a-form-item>
              <a-form-item label="小模型（关键信息）">
                <a-select
                  v-model="provider.smallSelected"
                  multiple
                  allow-clear
                  allow-create
                  placeholder="选择或输入模型"
                >
                  <a-option v-for="m in provider.smallModels" :key="m" :value="m">{{ m }}</a-option>
                </a-select>
              </a-form-item>
            </a-form>
          </a-card>
        </div>

        <a-divider orientation="left">路由预览（只读）</a-divider>
        <div class="preview-grid">
          <a-card size="small" title="摘要路由（大模型）JSON">
            <a-textarea :model-value="summaryProfilesJsonPreview" :auto-size="{ minRows: 6, maxRows: 12 }" readonly />
          </a-card>
          <a-card size="small" title="关键信息路由（小模型）JSON">
            <a-textarea :model-value="keyPointsProfilesJsonPreview" :auto-size="{ minRows: 6, maxRows: 12 }" readonly />
          </a-card>
          <a-card size="small" title="兼容Fallback JSON">
            <a-textarea :model-value="fallbackProfilesJsonPreview" :auto-size="{ minRows: 6, maxRows: 12 }" readonly />
          </a-card>
        </div>
          </a-space>
        </a-card>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { Message } from '@arco-design/web-vue'
import { getConfig, updateConfig } from '@/api/configManagement'

interface ProviderPreset {
  id: string
  label: string
  apiUrl: string
  bigModels: string[]
  smallModels: string[]
}

interface ProviderState {
  id: string
  label: string
  apiUrl: string
  apiKey: string
  bigModels: string[]
  smallModels: string[]
  bigSelected: string[]
  smallSelected: string[]
}

const PROVIDER_PRESETS: ProviderPreset[] = [
  {
    id: 'openrouter',
    label: '首选：OpenRouter',
    apiUrl: 'https://openrouter.ai/api/v1',
    bigModels: ['arcee-ai/trinity-large-preview:free', 'stepfun/step-3.5-flash:free'],
    smallModels: ['liquid/lfm-2.5-1.2b-thinking:free', 'liquid/lfm-2.5-1.2b-instruct:free']
  },
  {
    id: 'magicark',
    label: '二选：魔力方舟',
    apiUrl: 'https://ai.gitee.com/v1',
    bigModels: ['GLM-4.7-Flash'],
    smallModels: ['Qwen3-8B', 'DeepSeek-R1-Distill-Qwen-14B', 'Qwen3-4B', 'DeepSeek-R1-Distill-Qwen-7B', 'internlm3-8b-instruct']
  },
  {
    id: 'siliconflow',
    label: '三选：硅基流动',
    apiUrl: 'https://api.siliconflow.cn/v1',
    bigModels: ['stepfun-ai/Step-3.5-Flash', 'deepseek-ai/DeepSeek-R1-Distill-Qwen-7B', 'THUDM/GLM-Z1-9B-0414'],
    smallModels: ['Qwen/Qwen3-8B', 'THUDM/GLM-4-9B-0414', 'inclusionAI/Ling-mini-2.0']
  }
]

const makeProviders = (): ProviderState[] =>
  PROVIDER_PRESETS.map((p) => ({
    id: p.id,
    label: p.label,
    apiUrl: p.apiUrl,
    apiKey: '',
    bigModels: [...p.bigModels],
    smallModels: [...p.smallModels],
    bigSelected: [],
    smallSelected: []
  }))

const loading = ref(false)
const savingStarter = ref(false)
const savingSource = ref(false)
const savingModel = ref(false)
const providers = ref<ProviderState[]>(makeProviders())

const starterForm = reactive({
  enable: false,
  platforms: 'wechat,zhihu,xueqiu,toutiao,baijiahao,wsj,bbc',
  perPlatform: 2,
  feedIds: ''
})

const sourceForm = reactive({
  defaultWorkers: 4,
  byPlatform: 'zhihu:4,xueqiu:3,toutiao:3,baijiahao:2,wsj:1,bbc:1,rsshub:3,rss:2'
})

const modelForm = reactive({
  routerEnable: true,
  autoAiSummary: true,
  autoKeyPoints: true,
  autoBreakdown: false,
  prewarmOnUpdate: true,
  summaryMode: 'fallback',
  keyPointsMode: 'fallback',
  breakdownMode: 'fallback',
  shardIncludeFallback: true,
  maxChars: 24000
})

const asBool = (v: any, fallback = false) => {
  const s = String(v ?? '').trim().toLowerCase()
  if (!s) return fallback
  return ['1', 'true', 'yes', 'on'].includes(s)
}

const asInt = (v: any, fallback: number) => {
  const n = Number(v)
  return Number.isFinite(n) ? Math.trunc(n) : fallback
}

const fetchValue = async (key: string, fallback = ''): Promise<string> => {
  try {
    const res: any = await getConfig(key)
    const v = String(res?.config_value ?? res?.data?.config_value ?? '').trim()
    return v || fallback
  } catch {
    return fallback
  }
}

const findProvider = (provider: string, apiUrl: string) => {
  const p = String(provider || '').trim().toLowerCase()
  const u = String(apiUrl || '').trim().toLowerCase()
  if (p) {
    const byId = providers.value.find((x) => x.id === p)
    if (byId) return byId
  }
  if (u.includes('openrouter.ai')) return providers.value.find((x) => x.id === 'openrouter')
  if (u.includes('ai.gitee.com')) return providers.value.find((x) => x.id === 'magicark')
  if (u.includes('siliconflow.cn')) return providers.value.find((x) => x.id === 'siliconflow')
  if (u) {
    const byUrl = providers.value.find((x) => String(x.apiUrl || '').trim().toLowerCase() === u)
    if (byUrl) return byUrl
  }
  return null
}

const ensureOption = (arr: string[], value: string) => {
  const v = String(value || '').trim()
  if (!v) return
  if (!arr.includes(v)) arr.push(v)
}

const ensureSelected = (arr: string[], value: string) => {
  const v = String(value || '').trim()
  if (!v) return
  if (!arr.includes(v)) arr.push(v)
}

const parseProfiles = (raw: string): any[] => {
  try {
    const parsed = JSON.parse(String(raw || '[]'))
    return Array.isArray(parsed) ? parsed : []
  } catch {
    return []
  }
}

const hydrateProvidersFromProfiles = (profiles: any[], kind: 'big' | 'small') => {
  for (const it of profiles) {
    const provider = String(it?.provider || '').trim()
    const apiUrl = String(it?.api_url || '').trim()
    const apiKey = String(it?.api_key || '').trim()
    const model = String(it?.model || '').trim()
    if (!model) continue
    const target = findProvider(provider, apiUrl)
    if (!target) continue
    if (apiUrl) target.apiUrl = apiUrl
    if (apiKey) target.apiKey = apiKey
    if (kind === 'big') {
      ensureOption(target.bigModels, model)
      ensureSelected(target.bigSelected, model)
    } else {
      ensureOption(target.smallModels, model)
      ensureSelected(target.smallSelected, model)
    }
  }
}

const buildProfiles = (kind: 'big' | 'small') => {
  const out: Array<Record<string, any>> = []
  let priority = 1
  for (const p of providers.value) {
    const chosen = kind === 'big' ? p.bigSelected : p.smallSelected
    for (const model of chosen) {
      const apiUrl = String(p.apiUrl || '').trim()
      const apiKey = String(p.apiKey || '').trim()
      const m = String(model || '').trim()
      if (!apiUrl || !apiKey || !m) continue
      out.push({
        name: `${p.id}-${kind}-${priority}`,
        provider: p.id,
        api_url: apiUrl,
        api_key: apiKey,
        model: m,
        priority
      })
      priority += 1
    }
  }
  return out
}

const summaryProfiles = computed(() => buildProfiles('big'))
const keyPointsProfiles = computed(() => buildProfiles('small'))
const breakdownProfiles = computed(() => {
  const summary = summaryProfiles.value
  if (summary.length) return summary
  return keyPointsProfiles.value
})
const fallbackProfiles = computed(() => {
  const merged = [...summaryProfiles.value, ...keyPointsProfiles.value]
  const seen = new Set<string>()
  const out: Array<Record<string, any>> = []
  let priority = 1
  for (const p of merged) {
    const key = `${p.provider}|${p.api_url}|${p.model}`
    if (seen.has(key)) continue
    seen.add(key)
    out.push({
      ...p,
      name: `fallback-${priority}`,
      priority
    })
    priority += 1
  }
  return out
})

const summaryProfilesJsonPreview = computed(() => JSON.stringify(summaryProfiles.value, null, 2))
const keyPointsProfilesJsonPreview = computed(() => JSON.stringify(keyPointsProfiles.value, null, 2))
const fallbackProfilesJsonPreview = computed(() => JSON.stringify(fallbackProfiles.value, null, 2))

const applyPresetModels = () => {
  for (const p of providers.value) {
    const preset = PROVIDER_PRESETS.find((x) => x.id === p.id)
    if (!preset) continue
    p.apiUrl = preset.apiUrl
    p.bigModels = [...new Set([...p.bigModels, ...preset.bigModels])]
    p.smallModels = [...new Set([...p.smallModels, ...preset.smallModels])]
    if (!p.bigSelected.length) p.bigSelected = [...preset.bigModels]
    if (!p.smallSelected.length) p.smallSelected = [...preset.smallModels]
  }
  Message.success('已导入预置模型清单（保留已有 API Key）')
}

const clearModelSelections = () => {
  for (const p of providers.value) {
    p.bigSelected = []
    p.smallSelected = []
  }
}

const validateProviderInputs = () => {
  for (const p of providers.value) {
    const needBig = p.bigSelected.length > 0
    const needSmall = p.smallSelected.length > 0
    if (!needBig && !needSmall) continue
    if (!String(p.apiUrl || '').trim()) {
      Message.error(`${p.label} 缺少 API Base URL`)
      return false
    }
    if (!String(p.apiKey || '').trim()) {
      Message.error(`${p.label} 缺少 API Key`)
      return false
    }
  }
  if (!summaryProfiles.value.length) {
    Message.error('请至少选择 1 个大模型（用于摘要）')
    return false
  }
  if (!keyPointsProfiles.value.length) {
    Message.error('请至少选择 1 个小模型（用于关键信息）')
    return false
  }
  return true
}

const saveStarter = async () => {
  if (savingStarter.value) return
  savingStarter.value = true
  try {
    await Promise.all([
      updateConfig('auth.default_subscribe_enable', {
        config_key: 'auth.default_subscribe_enable',
        config_value: starterForm.enable ? 'True' : 'False',
        description: '新用户注册后自动订阅默认平台包'
      }),
      updateConfig('auth.default_subscribe_platforms', {
        config_key: 'auth.default_subscribe_platforms',
        config_value: String(starterForm.platforms || '').trim(),
        description: '默认订阅平台列表'
      }),
      updateConfig('auth.default_subscribe_per_platform', {
        config_key: 'auth.default_subscribe_per_platform',
        config_value: String(Math.max(1, Math.min(30, Number(starterForm.perPlatform || 2)))),
        description: '每个平台默认订阅数量'
      }),
      updateConfig('auth.default_subscribe_feed_ids', {
        config_key: 'auth.default_subscribe_feed_ids',
        config_value: String(starterForm.feedIds || '').trim(),
        description: '固定订阅频道ID列表'
      })
    ])
    Message.success('订阅包配置已保存')
  } catch (e: any) {
    Message.error(e?.message || '保存失败')
  } finally {
    savingStarter.value = false
  }
}

const saveSourceWorkers = async () => {
  if (savingSource.value) return
  savingSource.value = true
  try {
    await Promise.all([
      updateConfig('auto_update.source_workers', {
        config_key: 'auto_update.source_workers',
        config_value: String(Math.max(1, Math.min(64, Number(sourceForm.defaultWorkers || 4)))),
        description: '多平台来源默认并发'
      }),
      updateConfig('auto_update.source_workers_by_platform', {
        config_key: 'auto_update.source_workers_by_platform',
        config_value: String(sourceForm.byPlatform || '').trim(),
        description: '多平台来源按平台并发覆盖'
      })
    ])
    Message.success('并发配置已保存')
  } catch (e: any) {
    Message.error(e?.message || '保存失败')
  } finally {
    savingSource.value = false
  }
}

const saveModelRouter = async () => {
  if (savingModel.value) return
  if (!validateProviderInputs()) return

  savingModel.value = true
  try {
    const summaryJson = JSON.stringify(summaryProfiles.value)
    const keyJson = JSON.stringify(keyPointsProfiles.value)
    const breakdownJson = JSON.stringify(breakdownProfiles.value)
    const fallbackJson = JSON.stringify(fallbackProfiles.value)
    const primary = summaryProfiles.value[0] || keyPointsProfiles.value[0] || null

    const updates: Promise<any>[] = [
      updateConfig('llm.router.enable', {
        config_key: 'llm.router.enable',
        config_value: modelForm.routerEnable ? 'true' : 'false',
        description: '任务级模型路由开关'
      }),
      updateConfig('insights.auto_ai_summary', {
        config_key: 'insights.auto_ai_summary',
        config_value: modelForm.autoAiSummary ? 'True' : 'False',
        description: '自动生成 AI 摘要'
      }),
      updateConfig('insights.auto_key_points', {
        config_key: 'insights.auto_key_points',
        config_value: modelForm.autoKeyPoints ? 'True' : 'False',
        description: '自动生成关键信息'
      }),
      updateConfig('insights.auto_llm_breakdown', {
        config_key: 'insights.auto_llm_breakdown',
        config_value: modelForm.autoBreakdown ? 'True' : 'False',
        description: '自动生成全文拆解'
      }),
      updateConfig('insights.prewarm_on_update', {
        config_key: 'insights.prewarm_on_update',
        config_value: modelForm.prewarmOnUpdate ? 'True' : 'False',
        description: '刷新后自动预热洞察'
      }),
      updateConfig('llm.max_chars', {
        config_key: 'llm.max_chars',
        config_value: String(Math.max(2000, Math.min(120000, Number(modelForm.maxChars || 24000)))),
        description: 'LLM 输入最大字符'
      }),
      updateConfig('llm.router.summary.mode', {
        config_key: 'llm.router.summary.mode',
        config_value: modelForm.summaryMode,
        description: '摘要路由模式'
      }),
      updateConfig('llm.router.key_points.mode', {
        config_key: 'llm.router.key_points.mode',
        config_value: modelForm.keyPointsMode,
        description: '关键信息路由模式'
      }),
      updateConfig('llm.router.breakdown.mode', {
        config_key: 'llm.router.breakdown.mode',
        config_value: modelForm.breakdownMode,
        description: '拆解路由模式'
      }),
      updateConfig('llm.router.shard.include_fallback', {
        config_key: 'llm.router.shard.include_fallback',
        config_value: modelForm.shardIncludeFallback ? 'True' : 'False',
        description: 'Shard 模式失败后回退其它通道'
      }),
      updateConfig('llm.router.summary.profiles_json', {
        config_key: 'llm.router.summary.profiles_json',
        config_value: summaryJson,
        description: '摘要路由配置'
      }),
      updateConfig('llm.router.key_points.profiles_json', {
        config_key: 'llm.router.key_points.profiles_json',
        config_value: keyJson,
        description: '关键信息路由配置'
      }),
      updateConfig('llm.router.breakdown.profiles_json', {
        config_key: 'llm.router.breakdown.profiles_json',
        config_value: breakdownJson,
        description: '全文拆解路由配置'
      }),
      updateConfig('llm.router.big_profiles_json', {
        config_key: 'llm.router.big_profiles_json',
        config_value: summaryJson,
        description: '兼容别名：大模型路由'
      }),
      updateConfig('llm.router.small_profiles_json', {
        config_key: 'llm.router.small_profiles_json',
        config_value: keyJson,
        description: '兼容别名：小模型路由'
      }),
      updateConfig('llm.fallback.enable', {
        config_key: 'llm.fallback.enable',
        config_value: modelForm.routerEnable ? 'True' : 'False',
        description: '兼容旧版 fallback'
      }),
      updateConfig('llm.fallback.profiles_json', {
        config_key: 'llm.fallback.profiles_json',
        config_value: fallbackJson,
        description: '兼容旧版 fallback 通道'
      })
    ]

    if (primary) {
      updates.push(
        updateConfig('llm.provider', {
          config_key: 'llm.provider',
          config_value: String(primary.provider || 'siliconflow'),
          description: '默认 LLM Provider（兼容单通道）'
        }),
        updateConfig('llm.siliconflow.api_url', {
          config_key: 'llm.siliconflow.api_url',
          config_value: String(primary.api_url || ''),
          description: '默认 API URL（兼容单通道）'
        }),
        updateConfig('llm.siliconflow.api_key', {
          config_key: 'llm.siliconflow.api_key',
          config_value: String(primary.api_key || ''),
          description: '默认 API Key（兼容单通道）'
        }),
        updateConfig('llm.siliconflow.model', {
          config_key: 'llm.siliconflow.model',
          config_value: String(primary.model || ''),
          description: '默认模型（兼容单通道）'
        })
      )
    }

    await Promise.all(updates)
    Message.success('模型路由配置已保存')
  } catch (e: any) {
    Message.error(e?.message || '保存失败')
  } finally {
    savingModel.value = false
  }
}

const loadAll = async () => {
  loading.value = true
  try {
    providers.value = makeProviders()

    const [
      starterEnable,
      starterPlatforms,
      starterPerPlatform,
      starterFeedIds,
      sourceWorkers,
      sourceByPlatform,
      routerEnable,
      autoAiSummary,
      autoKeyPoints,
      autoBreakdown,
      prewarmOnUpdate,
      summaryMode,
      keyPointsMode,
      breakdownMode,
      shardIncludeFallback,
      maxChars,
      summaryProfilesRaw,
      keyPointsProfilesRaw,
      fallbackProfilesRaw
    ] = await Promise.all([
      fetchValue('auth.default_subscribe_enable', 'False'),
      fetchValue('auth.default_subscribe_platforms', starterForm.platforms),
      fetchValue('auth.default_subscribe_per_platform', String(starterForm.perPlatform)),
      fetchValue('auth.default_subscribe_feed_ids', ''),
      fetchValue('auto_update.source_workers', String(sourceForm.defaultWorkers)),
      fetchValue('auto_update.source_workers_by_platform', sourceForm.byPlatform),
      fetchValue('llm.router.enable', 'false'),
      fetchValue('insights.auto_ai_summary', 'True'),
      fetchValue('insights.auto_key_points', 'True'),
      fetchValue('insights.auto_llm_breakdown', 'False'),
      fetchValue('insights.prewarm_on_update', 'True'),
      fetchValue('llm.router.summary.mode', 'fallback'),
      fetchValue('llm.router.key_points.mode', 'fallback'),
      fetchValue('llm.router.breakdown.mode', 'fallback'),
      fetchValue('llm.router.shard.include_fallback', 'True'),
      fetchValue('llm.max_chars', '24000'),
      fetchValue('llm.router.summary.profiles_json', ''),
      fetchValue('llm.router.key_points.profiles_json', ''),
      fetchValue('llm.fallback.profiles_json', '')
    ])

    starterForm.enable = asBool(starterEnable, false)
    starterForm.platforms = starterPlatforms
    starterForm.perPlatform = Math.max(1, Math.min(30, asInt(starterPerPlatform, 2)))
    starterForm.feedIds = starterFeedIds

    sourceForm.defaultWorkers = Math.max(1, Math.min(64, asInt(sourceWorkers, 4)))
    sourceForm.byPlatform = sourceByPlatform

    modelForm.routerEnable = asBool(routerEnable, true)
    modelForm.autoAiSummary = asBool(autoAiSummary, true)
    modelForm.autoKeyPoints = asBool(autoKeyPoints, true)
    modelForm.autoBreakdown = asBool(autoBreakdown, false)
    modelForm.prewarmOnUpdate = asBool(prewarmOnUpdate, true)
    modelForm.summaryMode = summaryMode || 'fallback'
    modelForm.keyPointsMode = keyPointsMode || 'fallback'
    modelForm.breakdownMode = breakdownMode || 'fallback'
    modelForm.shardIncludeFallback = asBool(shardIncludeFallback, true)
    modelForm.maxChars = Math.max(2000, Math.min(120000, asInt(maxChars, 24000)))

    const summaryProfiles = parseProfiles(summaryProfilesRaw)
    const keyProfiles = parseProfiles(keyPointsProfilesRaw)
    const fallbackProfiles = parseProfiles(fallbackProfilesRaw)

    hydrateProvidersFromProfiles(summaryProfiles, 'big')
    hydrateProvidersFromProfiles(keyProfiles, 'small')
    if (!summaryProfiles.length) hydrateProvidersFromProfiles(fallbackProfiles, 'big')
    if (!keyProfiles.length) hydrateProvidersFromProfiles(fallbackProfiles, 'small')
  } finally {
    loading.value = false
  }
}

onMounted(loadAll)
</script>

<style scoped>
.config-page {
  padding: 12px;
}

.config-grid {
  display: grid;
  grid-template-columns: minmax(360px, 36%) minmax(0, 64%);
  gap: 12px;
  align-items: start;
}

.config-left,
.config-right {
  min-width: 0;
}

.model-card {
  min-height: 100%;
}

.mt12 {
  margin-top: 12px;
}

.switch-row {
  display: flex;
  gap: 18px;
  flex-wrap: wrap;
  align-items: center;
}

.label {
  color: var(--color-text-2);
  font-size: 13px;
}

.providers-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
  gap: 10px;
}

.preview-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
  gap: 10px;
}

@media (max-width: 1200px) {
  .config-grid {
    grid-template-columns: 1fr;
  }
}
</style>
