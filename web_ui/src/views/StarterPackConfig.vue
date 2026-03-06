<template>
  <div class="starter-pack-page">
    <a-card title="新用户默认订阅包" :bordered="false">
      <a-space direction="vertical" fill>
        <a-alert type="info" show-icon>
          新用户注册后自动订阅你设定的平台频道。保存后即时生效。
        </a-alert>

        <a-form :model="form" layout="vertical">
          <a-form-item label="开启默认订阅包">
            <a-switch v-model="form.enable" />
          </a-form-item>

          <a-form-item label="平台列表（逗号分隔）">
            <a-input
              v-model="form.platforms"
              placeholder="wechat,zhihu,xueqiu,toutiao,baijiahao,wsj,bbc"
            />
          </a-form-item>

          <a-form-item label="每个平台默认订阅数量">
            <a-input-number v-model="form.perPlatform" :min="1" :max="30" />
          </a-form-item>

          <a-form-item label="固定频道ID（可选，逗号分隔）">
            <a-textarea
              v-model="form.feedIds"
              :auto-size="{ minRows: 2, maxRows: 5 }"
              placeholder="MP_WXS_xxx,SRC_xxx"
            />
          </a-form-item>
        </a-form>

        <a-space>
          <a-button type="primary" :loading="saving" @click="save">保存</a-button>
          <a-button :loading="loading" @click="load">刷新</a-button>
        </a-space>
      </a-space>
    </a-card>

    <a-card title="多平台自动刷新并发（可选）" :bordered="false" class="mt12">
      <a-space direction="vertical" fill>
        <a-form :model="sourceForm" layout="vertical">
          <a-form-item label="默认来源并发 workers">
            <a-input-number v-model="sourceForm.defaultWorkers" :min="1" :max="32" />
          </a-form-item>
          <a-form-item label="按平台覆盖（逗号分隔）">
            <a-input
              v-model="sourceForm.byPlatform"
              placeholder="zhihu:4,xueqiu:3,toutiao:3,baijiahao:2,wsj:1,bbc:1,rsshub:3,rss:2"
            />
          </a-form-item>
        </a-form>

        <a-space>
          <a-button type="primary" :loading="savingSource" @click="saveSourceWorkers">保存并发配置</a-button>
        </a-space>
      </a-space>
    </a-card>
  </div>
</template>

<script setup lang="ts">
import { reactive, ref, onMounted } from 'vue'
import { Message } from '@arco-design/web-vue'
import { getConfig, updateConfig } from '@/api/configManagement'

const loading = ref(false)
const saving = ref(false)
const savingSource = ref(false)

const form = reactive({
  enable: false,
  platforms: 'wechat,zhihu,xueqiu,toutiao,baijiahao,wsj,bbc',
  perPlatform: 2,
  feedIds: ''
})

const sourceForm = reactive({
  defaultWorkers: 4,
  byPlatform: 'zhihu:4,xueqiu:3,toutiao:3,baijiahao:2,wsj:1,bbc:1,rsshub:3,rss:2'
})

const asBool = (v: any) => String(v ?? '').trim().toLowerCase() === 'true'
const asInt = (v: any, d: number) => {
  const n = Number(v)
  return Number.isFinite(n) ? Math.trunc(n) : d
}

const fetchValue = async (key: string, fallback: string) => {
  try {
    const r: any = await getConfig(key)
    const val = String(r?.config_value ?? '').trim()
    return val || fallback
  } catch {
    return fallback
  }
}

const load = async () => {
  loading.value = true
  try {
    const [enable, platforms, perPlatform, feedIds, srcWorkers, srcByPlatform] = await Promise.all([
      fetchValue('auth.default_subscribe_enable', 'False'),
      fetchValue('auth.default_subscribe_platforms', form.platforms),
      fetchValue('auth.default_subscribe_per_platform', String(form.perPlatform)),
      fetchValue('auth.default_subscribe_feed_ids', ''),
      fetchValue('auto_update.source_workers', String(sourceForm.defaultWorkers)),
      fetchValue('auto_update.source_workers_by_platform', sourceForm.byPlatform)
    ])

    form.enable = asBool(enable)
    form.platforms = platforms
    form.perPlatform = Math.max(1, Math.min(30, asInt(perPlatform, 2)))
    form.feedIds = feedIds

    sourceForm.defaultWorkers = Math.max(1, Math.min(32, asInt(srcWorkers, 4)))
    sourceForm.byPlatform = srcByPlatform
  } finally {
    loading.value = false
  }
}

const save = async () => {
  if (saving.value) return
  saving.value = true
  try {
    await Promise.all([
      updateConfig('auth.default_subscribe_enable', {
        config_key: 'auth.default_subscribe_enable',
        config_value: form.enable ? 'True' : 'False',
        description: '新用户注册后自动订阅默认平台包'
      }),
      updateConfig('auth.default_subscribe_platforms', {
        config_key: 'auth.default_subscribe_platforms',
        config_value: form.platforms.trim(),
        description: '默认订阅平台列表'
      }),
      updateConfig('auth.default_subscribe_per_platform', {
        config_key: 'auth.default_subscribe_per_platform',
        config_value: String(Math.max(1, Math.min(30, Number(form.perPlatform || 2)))),
        description: '每个平台默认订阅数量'
      }),
      updateConfig('auth.default_subscribe_feed_ids', {
        config_key: 'auth.default_subscribe_feed_ids',
        config_value: form.feedIds.trim(),
        description: '固定订阅的频道ID列表'
      })
    ])
    Message.success('默认订阅包配置已保存')
  } catch (e: any) {
    Message.error(e?.message || '保存失败')
  } finally {
    saving.value = false
  }
}

const saveSourceWorkers = async () => {
  if (savingSource.value) return
  savingSource.value = true
  try {
    await Promise.all([
      updateConfig('auto_update.source_workers', {
        config_key: 'auto_update.source_workers',
        config_value: String(Math.max(1, Math.min(32, Number(sourceForm.defaultWorkers || 4)))),
        description: '多平台来源默认并发'
      }),
      updateConfig('auto_update.source_workers_by_platform', {
        config_key: 'auto_update.source_workers_by_platform',
        config_value: sourceForm.byPlatform.trim(),
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

onMounted(load)
</script>

<style scoped>
.starter-pack-page {
  padding: 12px;
}

.mt12 {
  margin-top: 12px;
}
</style>
