<template>
  <div class="add-subscription">
    <a-page-header
      v-if="!embedded"
      title="订阅广场"
      subtitle="按平台搜索并添加博主，持续扩充你的订阅库"
      :show-back="true"
      @back="goBack"
    />

    <a-card>
      <div class="platform-manage">
        <div class="platform-switch">
          <a-tag
            v-for="p in managePlatformOptions"
            :key="p.value"
            class="platform-chip"
            :color="managePlatform === p.value ? 'arcoblue' : 'gray'"
            @click="managePlatform = p.value"
          >
            {{ p.label }}
          </a-tag>
        </div>

        <template v-if="managePlatform === 'wechat'">
          <div class="toolbar-line compact-toolbar">
            <a-select
              v-model="selectedWechatSearchValue"
              placeholder="搜索公众号并选择"
              allow-clear
              allow-search
              :filter-option="false"
              style="min-width: 260px; max-width: 360px"
              @search="handleSearch"
              @change="handleSearchSelect"
            >
              <a-option
                v-for="item of searchResults"
                :key="item.fakeid || item.nickname"
                :value="String(item.fakeid || item.nickname || '')"
                :label="item.nickname"
              >
                <div class="wechat-option">
                  <span class="wechat-option-name">{{ item.nickname }}</span>
                  <span class="wechat-option-desc">{{ item.signature || '公众号' }}</span>
                </div>
              </a-option>
            </a-select>
            <a-button size="small" type="primary" :loading="loading" @click="handleSubmit">搜索添加</a-button>
            <a-button size="small" type="outline" @click="startWechatAuth">扫码授权</a-button>
            <a-select
              v-model="selectedWechatBatchNames"
              placeholder="选择推荐博主（可多选）"
              allow-clear
              allow-search
              multiple
              :max-tag-count="2"
              style="min-width: 260px; max-width: 420px"
            >
              <a-option
                v-for="it in filteredWechatPlazaItems"
                :key="`wechat-batch-${it.name}`"
                :value="it.name"
                :label="it.name"
              >
                {{ it.name }}
              </a-option>
            </a-select>
            <a-button size="small" type="outline" :loading="platformDefaultsImporting" @click="batchAddCurrentPlatformBloggers">
              添加推荐
            </a-button>
          </div>

          <a-alert
            v-if="needWechatAuth"
            type="warning"
            show-icon
            style="margin-top: 10px"
            title="公众号平台需要先扫码授权"
          >
            <div style="display:flex; align-items:center; justify-content:space-between; gap:12px; flex-wrap:wrap;">
              <span style="color: var(--color-text-2);">
                未获取到公众号平台会话（token/cookie），请先完成「扫码授权」后再搜索/添加。
              </span>
              <a-button size="small" type="primary" @click="startWechatAuth">立即扫码授权</a-button>
            </div>
          </a-alert>

          <div class="meta-preview" v-if="form.wx_id">
            <a-avatar :size="40" :src="avatarUrl"><img :src="avatarUrl" width="40" /></a-avatar>
            <div class="meta-text">
              <div class="meta-title">{{ form.name }}</div>
              <div class="meta-sub">{{ form.description || ' ' }}</div>
            </div>
          </div>

          <div class="source-presets">
            <div class="source-presets-head compact-head nowrap-head">
              <div class="source-title">公众号推荐 / 链接识别</div>
              <a-input
                v-model="articleLink"
                placeholder="粘贴公众号文章链接，自动识别公众号"
                style="min-width: 260px; max-width: 460px"
              />
              <a-button size="small" :loading="isFetching" @click="handleGetMpInfo">识别</a-button>
            </div>
            <div v-if="wechatTagOptions.length > 1" class="tag-strip">
              <button
                v-for="tag in wechatTagOptions"
                :key="`wechat-tag-${tag}`"
                type="button"
                class="tag-chip"
                :class="{ active: activeWechatTag === tag }"
                @click="activeWechatTag = tag"
              >
                {{ tag }}
              </button>
            </div>
            <div class="preset-grid" v-if="filteredWechatPlazaItems.length">
              <div v-for="it in filteredWechatPlazaItems" :key="`wechat-${it.name}`" class="preset-card">
                <div class="preset-main">
                  <a-avatar :size="26" :image-url="wechatAvatar(it)">
                    <img :src="wechatAvatar(it)" />
                  </a-avatar>
                  <div class="preset-name-row">
                    <div class="preset-name">{{ it.name }}</div>
                    <div v-if="it.add_count" class="preset-heat">热度 {{ it.add_count }}</div>
                  </div>
                  <div class="preset-desc">{{ it.desc || '公众号推荐' }}</div>
                  <div v-if="it.tags?.length" class="preset-tags">
                    <span v-for="tag in it.tags.slice(0, 3)" :key="`${it.name}-${tag}`" class="preset-tag">{{ tag }}</span>
                  </div>
                </div>
                <a-button
                  size="small"
                  type="primary"
                  :loading="!!addingMap[it.name]"
                  :disabled="isSubscribed(it)"
                  @click="subscribeFromPlaza(it)"
                >
                  {{ isSubscribed(it) ? '已添加' : '添加推荐' }}
                </a-button>
              </div>
            </div>
            <div v-else class="muted">暂无匹配的公众号推荐。</div>
          </div>
        </template>

        <template v-else>
          <div class="toolbar-line compact-toolbar">
            <a-select
              v-model="selectedPlatformPresetKey"
              allow-clear
              allow-search
              style="min-width: 260px; max-width: 360px"
              placeholder="搜索并选择博主"
            >
              <a-option
                v-for="preset in filteredManagePlatformCandidates"
                :key="presetSelectKey(preset)"
                :value="presetSelectKey(preset)"
                :label="preset.name"
              >
                {{ preset.name }}
              </a-option>
            </a-select>
            <a-button size="small" type="primary" :loading="sourceSubmitting" @click="addSelectedPlatformBlogger">搜索添加</a-button>
            <a-button
              v-if="platformSupportsScanAuth(managePlatform)"
              size="small"
              type="outline"
              @click="startWechatAuth"
            >
              扫码授权
            </a-button>
            <a-input
              v-model="manageKeyword"
              allow-clear
              style="min-width: 180px; max-width: 260px"
              placeholder="搜索推荐与已添加"
            />
            <a-select
              v-model="selectedPlatformBatchKeys"
              placeholder="选择推荐博主（可多选）"
              allow-clear
              allow-search
              multiple
              :max-tag-count="2"
              style="min-width: 260px; max-width: 420px"
            >
              <a-option
                v-for="preset in filteredManagePlatformCandidates"
                :key="`platform-batch-${presetSelectKey(preset)}`"
                :value="presetSelectKey(preset)"
                :label="preset.name"
              >
                {{ preset.name }}
              </a-option>
            </a-select>
            <a-button size="small" type="outline" :loading="platformDefaultsImporting" @click="batchAddCurrentPlatformBloggers">
              添加推荐
            </a-button>
            <a-button size="small" type="outline" :loading="sourceListLoading" @click="loadSourceFeeds">刷新已添加</a-button>
          </div>

          <div class="source-presets">
            <div class="source-presets-head">
              <div class="source-title">{{ managePlatformLabel }}推荐博主</div>
            </div>
            <div v-if="managePlatformTagOptions.length > 1" class="tag-strip">
              <button
                v-for="tag in managePlatformTagOptions"
                :key="`${managePlatform}-tag-${tag}`"
                type="button"
                class="tag-chip"
                :class="{ active: activeManagePlatformTag === tag }"
                @click="activeManagePlatformTag = tag"
              >
                {{ tag }}
              </button>
            </div>
            <div class="preset-grid" v-if="filteredManagePlatformCandidates.length">
              <div v-for="preset in filteredManagePlatformCandidates" :key="presetSelectKey(preset)" class="preset-card">
                <div class="preset-main">
                  <a-avatar :size="26" :image-url="presetAvatar(preset)">
                    <img :src="presetAvatar(preset)" />
                  </a-avatar>
                  <div class="preset-name-row">
                    <div class="preset-name">{{ preset.name }}</div>
                    <div v-if="preset.add_count" class="preset-heat">热度 {{ preset.add_count }}</div>
                  </div>
                  <div class="preset-desc">{{ preset.description || '平台预置模板' }}</div>
                  <div v-if="preset.tags?.length" class="preset-tags">
                    <span v-for="tag in preset.tags.slice(0, 3)" :key="`${preset.name}-${tag}`" class="preset-tag">{{ tag }}</span>
                  </div>
                </div>
                <a-button
                  size="small"
                  type="primary"
                  :disabled="isPresetAdded(preset)"
                  :loading="sourceSubmitting"
                  @click="quickAddPreset(preset)"
                >
                  {{ isPresetAdded(preset) ? '已添加' : '添加推荐' }}
                </a-button>
              </div>
            </div>
            <div v-else class="muted">该平台暂无匹配的博主推荐。</div>
          </div>

          <div class="source-list-wrap">
            <div class="source-title">已添加{{ managePlatformLabel }}订阅</div>
            <a-list v-if="filteredManageSourceFeeds.length" :bordered="false">
              <a-list-item v-for="item in filteredManageSourceFeeds" :key="item.id" class="source-item">
                <div class="source-item-main">
                  <a-avatar class="source-item-avatar" :size="26">
                    <img :src="sourceFeedAvatar(item)" />
                  </a-avatar>
                  <div class="source-item-title">{{ item.name }}</div>
                  <div class="source-item-sub">{{ displaySourcePlatform(item.source_platform) }} · {{ item.source_type }}</div>
                  <div class="source-item-url">{{ item.source_url }}</div>
                </div>
                <a-space>
                  <a-button
                    size="mini"
                    type="outline"
                    :loading="sourceRefreshLoadingId === item.id"
                    @click="refreshOneSource(item.id)"
                  >
                    刷新
                  </a-button>
                  <a-button
                    size="mini"
                    status="danger"
                    :loading="sourceDeleteLoadingId === item.id"
                    @click="removeOneSource(item.id)"
                  >
                    删除
                  </a-button>
                </a-space>
              </a-list-item>
            </a-list>
            <div v-else class="muted">该平台还没有已添加订阅。</div>
          </div>
        </template>
      </div>
    </a-card>

    <WechatAuthQrcode ref="qrcodeRef" @success="onWechatAuthSuccess" />
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { notifyError, notifyInfo, notifySuccess, notifyWarning } from '@/utils/notify'
import { addSubscription, getPlaza, getSubscriptions, searchBiz, getSubscriptionInfo } from '@/api/subscription'
import { Avatar } from '@/utils/constants'
import WechatAuthQrcode from '@/components/WechatAuthQrcode.vue'
import {
  addSourceFeed,
  deleteSourceFeed,
  getRsshubStatus,
  listSourceFeeds,
  listSourcePlatformPresets,
  refreshSourceFeed,
  SourceFeedItem,
  SourcePresetItem,
} from '@/api/sources'
import { emitChannelFeedChanged } from '@/utils/subscriptionEvents'

const props = withDefaults(
  defineProps<{
    embedded?: boolean
  }>(),
  {
    embedded: false,
  }
)

const embedded = computed(() => !!props.embedded)
const router = useRouter()

const loading = ref(false)
const isFetching = ref(false)
const searchResults = ref<any[]>([])
const avatarUrl = ref('/static/default-avatar.png')
const form = ref({
  name: '',
  wx_id: '',
  avatar: '',
  description: '',
})

const qrcodeRef = ref<any>(null)
const needWechatAuth = ref(false)
const lastSearchKw = ref('')
const articleLink = ref('')
const selectedWechatSearchValue = ref('')

const sourceSubmitting = ref(false)
const sourceListLoading = ref(false)
const sourceRefreshLoadingId = ref('')
const sourceDeleteLoadingId = ref('')
const platformDefaultsImporting = ref(false)
const sourceFeeds = ref<SourceFeedItem[]>([])
const sourcePresets = ref<SourcePresetItem[]>([])
const managePlatform = ref('wechat')
const manageKeyword = ref('')
const selectedPlatformPresetKey = ref('')
const selectedWechatBatchNames = ref<string[]>([])
const selectedPlatformBatchKeys = ref<string[]>([])
const rsshubBaseUrl = ref('')

const platformAuthStateMap = ref<Record<string, 'unknown' | 'required' | 'not_required'>>({})

const PORTAL_PLATFORM_KEYS = new Set(['wsj', 'bbc', 'nytimes', 'guardian', 'cnn', 'npr', 'cnbc'])
const normalizePlatform = (raw: string) => {
  const p = String(raw || '').trim().toLowerCase()
  if (!p) return ''
  if (PORTAL_PLATFORM_KEYS.has(p)) return 'portal'
  return p
}

const SOURCE_PLATFORM_LABELS: Record<string, string> = {
  wechat: '公众号',
  zhihu: '知乎',
  xueqiu: '雪球',
  toutiao: '头条',
  baijiahao: '百家号',
  weibo: '微博',
  portal: '门户',
  wsj: '华尔街日报',
  bbc: 'BBC',
  nytimes: 'NYTimes',
  guardian: 'The Guardian',
  cnn: 'CNN',
  npr: 'NPR',
  cnbc: 'CNBC',
  tech: '科技媒体',
  rss: 'RSS',
  rsshub: 'RSSHub',
}

const AUTH_REQUIRED_RE = /(授权|扫码|cookie|token|登录|unauthorized|forbidden|403|401|login)/i

type PlazaItem = {
  name: string
  kw?: string
  desc?: string
  tags?: string[]
  mp_id?: string
  avatar?: string
  cover?: string
  add_count?: number
  platform?: string
  feed_id?: string
}
type PlazaCategory = { id: string; name: string; items: PlazaItem[] }

const plazaLoading = ref(false)
const plazaData = ref<{ categories: PlazaCategory[] }>({ categories: [] })
const subscribedNames = ref<Set<string>>(new Set())
const addingMap = ref<Record<string, boolean>>({})
const activeWechatTag = ref('全部')
const activeManagePlatformTag = ref('全部')
let reloadWechatStateTimer: ReturnType<typeof setTimeout> | null = null
let reloadSourceStateTimer: ReturnType<typeof setTimeout> | null = null

const plazaCategories = computed(() => plazaData.value.categories || [])
const sortByHeat = <T extends { name?: string; add_count?: number }>(items: T[]) =>
  [...items].sort((a, b) => {
    const diff = Number(b?.add_count || 0) - Number(a?.add_count || 0)
    if (diff !== 0) return diff
    return String(a?.name || '').localeCompare(String(b?.name || ''))
  })

const isWechatPlazaItem = (item: PlazaItem) => {
  const platform = normalizePlatform(String(item?.platform || 'wechat'))
  const feedId = String(item?.feed_id || '').trim()
  const mpId = String(item?.mp_id || '').trim()
  if (platform !== 'wechat') return false
  if (feedId.startsWith('SRC_')) return false
  return !!(mpId || !feedId || feedId.startsWith('MP_'))
}

const wechatPlazaItems = computed<PlazaItem[]>(() => {
  const dedup = new Map<string, PlazaItem>()
  for (const cat of plazaCategories.value) {
    const items = Array.isArray(cat?.items) ? cat.items : []
    for (const it of items) {
      if (!isWechatPlazaItem(it)) continue
      const name = String(it?.name || '').trim()
      if (!name || dedup.has(name)) continue
      dedup.set(name, it)
    }
  }
  return sortByHeat(Array.from(dedup.values()))
})
const wechatTagOptions = computed(() => {
  const set = new Set<string>(['全部'])
  wechatPlazaItems.value.forEach((item) => (item.tags || []).forEach((tag) => set.add(String(tag))))
  return Array.from(set)
})
const filteredWechatPlazaItems = computed(() => {
  if (activeWechatTag.value === '全部') return wechatPlazaItems.value
  return wechatPlazaItems.value.filter((item) => (item.tags || []).includes(activeWechatTag.value))
})

const managePlatformOptions = computed(() => {
  const preferred = ['wechat', 'zhihu', 'xueqiu', 'toutiao', 'baijiahao', 'weibo', 'portal']
  const keys = new Set<string>(preferred)
  for (const x of sourcePresets.value) {
    const p = normalizePlatform(String(x.platform || ''))
    if (!p || p === 'rss' || p === 'rsshub') continue
    keys.add(p)
  }
  return Array.from(keys).map((k) => ({ value: k, label: SOURCE_PLATFORM_LABELS[k] || k.toUpperCase() }))
})

const managePlatformLabel = computed(() => SOURCE_PLATFORM_LABELS[managePlatform.value] || managePlatform.value)
const SCAN_AUTH_PLATFORMS = new Set(['wechat', 'zhihu', 'xueqiu', 'toutiao', 'baijiahao', 'weibo'])
const platformSupportsScanAuth = (raw: string) => SCAN_AUTH_PLATFORMS.has(normalizePlatform(raw))

const presetSelectKey = (preset: SourcePresetItem) => {
  return [
    String(preset.platform || ''),
    String(preset.source_type || ''),
    String(preset.rsshub_route_template || ''),
    String(preset.source_url || ''),
    String(preset.name || ''),
  ].join('|')
}

const _platformQuickAddCandidates = (platform: string): SourcePresetItem[] => {
  const p = normalizePlatform(String(platform || ''))
  if (!p) return []
  return sourcePresets.value.filter((x) => {
    if (normalizePlatform(String(x.platform || '')) !== p) return false
    if (x.quick_add === false) return false
    const route = String(x.rsshub_route_template || '').trim()
    if (/:([a-zA-Z_][a-zA-Z0-9_-]*)/.test(route)) return false
    return true
  })
}

const managePlatformCandidates = computed(() => _platformQuickAddCandidates(managePlatform.value))
const managePlatformTagOptions = computed(() => {
  const set = new Set<string>(['全部'])
  managePlatformCandidates.value.forEach((item) => (item.tags || []).forEach((tag) => set.add(String(tag))))
  return Array.from(set)
})
const filteredManagePlatformCandidates = computed(() => {
  const kw = String(manageKeyword.value || '').trim().toLowerCase()
  const base = activeManagePlatformTag.value === '全部'
    ? managePlatformCandidates.value
    : managePlatformCandidates.value.filter((x) => (x.tags || []).includes(activeManagePlatformTag.value))
  if (!kw) return sortByHeat(base)
  return sortByHeat(base.filter((x) => {
    const hay = `${x.name || ''} ${x.description || ''} ${(x.tags || []).join(' ')} ${SOURCE_PLATFORM_LABELS[normalizePlatform(String(x.platform || ''))] || x.platform || ''}`.toLowerCase()
    return hay.includes(kw)
  }))
})

const selectedPlatformPresetItem = computed(() => {
  const key = String(selectedPlatformPresetKey.value || '')
  if (!key) return null
  return managePlatformCandidates.value.find((x) => presetSelectKey(x) === key) || null
})

const filteredManageSourceFeeds = computed(() =>
  sourceFeeds.value.filter((x) => {
    if (normalizePlatform(String(x.source_platform || '')) !== managePlatform.value) return false
    const kw = String(manageKeyword.value || '').trim().toLowerCase()
    if (!kw) return true
    const hay = `${x.name || ''} ${x.source_url || ''} ${x.source_type || ''} ${displaySourcePlatform(String(x.source_platform || ''))}`.toLowerCase()
    return hay.includes(kw)
  })
)

const displaySourcePlatform = (raw: string) => SOURCE_PLATFORM_LABELS[normalizePlatform(raw)] || raw

const wechatAvatar = (it: PlazaItem) => {
  const img = String((it as any)?.cover || (it as any)?.avatar || '').trim()
  return img || '/static/default-avatar.png'
}

const normalizeNameKey = (value: string) => String(value || '').trim().toLowerCase()

const markWechatSubscribedLocal = (payload: { mp_name: string }) => {
  const key = normalizeNameKey(payload.mp_name)
  if (!key) return
  subscribedNames.value = new Set([...subscribedNames.value, key])
}

const emitWechatFeedAdded = (payload: { mp_id: string; mp_name: string; avatar?: string; mp_intro?: string }) => {
  const id = String(payload.mp_id || '').trim()
  if (!id) return
  emitChannelFeedChanged({
    action: 'added',
    feed: {
      id,
      name: String(payload.mp_name || '').trim(),
      cover: String(payload.avatar || '').trim(),
      intro: String(payload.mp_intro || '').trim(),
      source_type: 'wechat',
      source_platform: 'wechat',
      unread_count: 0,
      article_count: 0,
      latest_publish_time: 0,
    },
  })
}

const upsertLocalSourceFeed = (payload: Partial<SourceFeedItem> & { id?: string; name?: string }) => {
  const id = String(payload.id || '').trim()
  if (!id) return
  const next: SourceFeedItem = {
    id,
    name: String(payload.name || '').trim() || '未命名订阅',
    source_type: (String(payload.source_type || 'rss').toLowerCase() as 'rss' | 'rsshub'),
    source_platform: normalizePlatform(String(payload.source_platform || '')),
    source_url: String(payload.source_url || '').trim(),
    updated_at: payload.updated_at || null,
  }
  const list = [...sourceFeeds.value]
  const index = list.findIndex((item) => String(item.id || '') === id)
  if (index >= 0) list[index] = { ...list[index], ...next }
  else list.unshift(next)
  sourceFeeds.value = list
}

const removeLocalSourceFeed = (feedId: string) => {
  const id = String(feedId || '').trim()
  if (!id) return
  sourceFeeds.value = sourceFeeds.value.filter((item) => String(item.id || '') !== id)
}

const emitSourceFeedAdded = (payload: Partial<SourceFeedItem> & { id?: string; name?: string }) => {
  const id = String(payload.id || '').trim()
  if (!id) return
  emitChannelFeedChanged({
    action: 'added',
    feed: {
      id,
      name: String(payload.name || '').trim() || '未命名订阅',
      cover: '',
      intro: '',
      source_type: String(payload.source_type || 'rss').toLowerCase(),
      source_platform: normalizePlatform(String(payload.source_platform || '')),
      source_url: String(payload.source_url || '').trim(),
      unread_count: 0,
      article_count: 0,
      latest_publish_time: 0,
    },
  })
}

const emitFeedRemoved = (feedId: string) => {
  const id = String(feedId || '').trim()
  if (!id) return
  emitChannelFeedChanged({
    action: 'removed',
    feed: {
      id,
      name: '',
    },
  })
}

const scheduleWechatStateReload = () => {
  if (reloadWechatStateTimer) clearTimeout(reloadWechatStateTimer)
  reloadWechatStateTimer = setTimeout(() => {
    Promise.allSettled([loadSubscribed(), loadPlaza()])
    reloadWechatStateTimer = null
  }, 300)
}

const scheduleSourceStateReload = () => {
  if (reloadSourceStateTimer) clearTimeout(reloadSourceStateTimer)
  reloadSourceStateTimer = setTimeout(() => {
    Promise.allSettled([loadSourceFeeds()])
    reloadSourceStateTimer = null
  }, 300)
}

const presetAvatar = (preset: SourcePresetItem) => {
  const explicit = String(preset?.avatar || '').trim()
  if (explicit) return explicit
  const url = String(preset?.source_url || '').trim()
  if (url) {
    try {
      const u = new URL(url)
      return `${u.origin}/favicon.ico`
    } catch {
      // ignore and fallback
    }
  }
  return '/static/default-avatar.png'
}

const startWechatAuth = () => qrcodeRef.value?.startAuth?.()

const onWechatAuthSuccess = async () => {
  needWechatAuth.value = false
  platformAuthStateMap.value.wechat = 'not_required'
  if (lastSearchKw.value) await handleSearch(lastSearchKw.value)
}

const _extractErrMsg = (e: any): string => {
  if (!e) return ''
  if (typeof e === 'string') return e
  return String(e?.detail?.message || e?.message || e?.detail || '')
}

const _markAuthStateFromError = (platform: string, errorLike: any) => {
  const msg = _extractErrMsg(errorLike)
  if (!msg) return
  if (AUTH_REQUIRED_RE.test(msg)) {
    platformAuthStateMap.value[String(platform || '').toLowerCase()] = 'required'
  }
}

watch(
  () => form.value.avatar,
  (newValue) => {
    avatarUrl.value = Avatar(newValue)
  },
  { deep: true }
)

watch(
  () => form.value.name,
  (value) => {
    if (!form.value.wx_id) {
      selectedWechatSearchValue.value = String(value || '')
    }
  }
)

watch(
  () => managePlatform.value,
  () => {
    selectedPlatformPresetKey.value = ''
    selectedPlatformBatchKeys.value = []
    activeManagePlatformTag.value = '全部'
  }
)

watch(wechatTagOptions, (options) => {
  if (!options.includes(activeWechatTag.value)) activeWechatTag.value = '全部'
})

watch(managePlatformTagOptions, (options) => {
  if (!options.includes(activeManagePlatformTag.value)) activeManagePlatformTag.value = '全部'
})

const handleSearch = async (value: string) => {
  const raw = String(value || '').trim()
  const previousName = String(form.value.name || '').trim()
  if (raw && previousName && raw !== previousName) {
    form.value.wx_id = ''
    form.value.description = ''
    form.value.avatar = ''
  }
  form.value.name = raw
  if (!raw) {
    form.value.wx_id = ''
    form.value.description = ''
    form.value.avatar = ''
    selectedWechatSearchValue.value = ''
  }
  if (!raw) {
    searchResults.value = []
    return
  }
  const safeValue = raw.slice(0, 100)
  if (safeValue.length < raw.length) notifyInfo('搜索关键词已截断为100个字符')
  lastSearchKw.value = safeValue
  try {
    const res = await searchBiz(safeValue, { page: 0, pageSize: 10 })
    searchResults.value = res.list || []
    needWechatAuth.value = false
    platformAuthStateMap.value.wechat = 'not_required'
  } catch (error) {
    const msg = _extractErrMsg(error)
    needWechatAuth.value = msg.includes('扫码授权') || msg.includes('授权')
    if (needWechatAuth.value) platformAuthStateMap.value.wechat = 'required'
    searchResults.value = []
  }
}

const handleSearchSelect = (value: string | number | boolean | Record<string, any> | undefined) => {
  const pickedValue = String(value || '').trim()
  selectedWechatSearchValue.value = pickedValue
  const picked =
    searchResults.value.find((item) => String(item?.fakeid || '') === pickedValue) ||
    searchResults.value.find((item) => String(item?.nickname || '') === pickedValue)
  if (picked) {
    handleSelect(picked)
    return
  }
  if (!pickedValue) {
    form.value.wx_id = ''
  }
}

const handleGetMpInfo = async () => {
  if (isFetching.value) return false
  if (!articleLink.value.trim()) {
    notifyWarning('请提供公众号文章链接')
    return false
  }
  isFetching.value = true
  try {
    const res = await getSubscriptionInfo(articleLink.value.trim())
    const info = res?.mp_info || false
    if (info) {
      form.value.name = info.mp_name || ''
      form.value.description = info.mp_name || ''
      form.value.wx_id = info.biz || ''
      form.value.avatar = info.logo || ''
      selectedWechatSearchValue.value = form.value.wx_id || form.value.name
      notifySuccess('公众号信息识别成功')
    } else {
      notifyWarning('未识别到公众号信息')
    }
  } catch (error) {
    notifyError('获取公众号信息失败')
    return false
  } finally {
    isFetching.value = false
  }
  return true
}

const handleSelect = (item: any) => {
  form.value.name = String(item?.nickname || '')
  form.value.wx_id = String(item?.fakeid || '')
  form.value.description = String(item?.signature || '')
  form.value.avatar = String(item?.round_head_img || '')
  selectedWechatSearchValue.value = form.value.wx_id || form.value.name
}

const tryResolveWechatSelection = async () => {
  if (form.value.wx_id) return true
  const keyword = String(form.value.name || selectedWechatSearchValue.value || '').trim()
  if (!keyword) return false
  await handleSearch(keyword)
  const exact =
    searchResults.value.find((item) => String(item?.nickname || '').trim().toLowerCase() === keyword.toLowerCase()) ||
    searchResults.value[0]
  if (!exact) return false
  handleSelect(exact)
  return true
}

const handleSubmit = async () => {
  loading.value = true
  const resolved = await tryResolveWechatSelection()
  if (!form.value.name || !form.value.wx_id || !resolved) {
    notifyWarning('请先选择一个公众号')
    loading.value = false
    return
  }

  try {
    await addSubscription({
      mp_name: form.value.name,
      mp_id: form.value.wx_id,
      avatar: form.value.avatar,
      mp_intro: form.value.description,
    })
    markWechatSubscribedLocal({ mp_name: form.value.name })
    emitWechatFeedAdded({
      mp_id: form.value.wx_id,
      mp_name: form.value.name,
      avatar: form.value.avatar,
      mp_intro: form.value.description,
    })
    notifySuccess('博主添加成功')
    scheduleWechatStateReload()
  } catch (error) {
    _markAuthStateFromError('wechat', error)
    notifyError((error as any)?.message || '添加失败，请稍后重试')
  } finally {
    loading.value = false
  }
}

const loadSubscribed = async () => {
  try {
    const pageSize = 1000
    const list: any[] = []
    let page = 0
    while (true) {
      const res: any = await getSubscriptions({ page, pageSize })
      const chunk = res?.list || res?.data?.list || []
      if (!Array.isArray(chunk) || !chunk.length) break
      list.push(...chunk)
      if (chunk.length < pageSize) break
      page += 1
      if (page > 50) break
    }
    const names = new Set<string>()
    for (const x of list) {
      if (x?.mp_name) names.add(String(x.mp_name).trim().toLowerCase())
    }
    subscribedNames.value = names
  } catch {
    subscribedNames.value = new Set()
  }
}

const loadPlaza = async () => {
  plazaLoading.value = true
  try {
    const res: any = await getPlaza({})
    plazaData.value = res || { categories: [] }
  } catch {
    plazaData.value = { categories: [] }
  } finally {
    plazaLoading.value = false
  }
}

const isSubscribed = (it: PlazaItem) => {
  const n = String(it.name || '').trim().toLowerCase()
  if (!n) return false
  return subscribedNames.value.has(n)
}

const subscribeFromPlaza = async (it: PlazaItem, opts?: { silent?: boolean; skipReload?: boolean }) => {
  const key = it.name
  if (addingMap.value[key]) return false
  addingMap.value[key] = true
  let ok = false
  try {
    const directMpId = String((it as any).mp_id || '').trim()
    if (directMpId) {
      await addSubscription({
        mp_name: it.name,
        mp_id: directMpId,
        avatar: String((it as any).cover || (it as any).avatar || ''),
        mp_intro: it.desc || '',
      })
      ok = true
      markWechatSubscribedLocal({ mp_name: it.name })
      emitWechatFeedAdded({
        mp_id: directMpId,
        mp_name: it.name,
        avatar: String((it as any).cover || (it as any).avatar || ''),
        mp_intro: it.desc || '',
      })
      if (!opts?.silent) notifySuccess(`已添加：${it.name}`)
      if (!opts?.skipReload) scheduleWechatStateReload()
      return true
    }
    const kw = String(it.kw || it.name || '').trim()
    if (!kw) throw new Error('缺少关键词')
    const r: any = await searchBiz(kw, { page: 0, pageSize: 5 })
    const list = r?.list || []
    if (!list.length) {
      if (!opts?.silent) notifyWarning(`未找到公众号：${kw}`)
      return false
    }
    const picked = list[0]
    await addSubscription({
      mp_name: picked.nickname,
      mp_id: picked.fakeid,
      avatar: picked.round_head_img,
      mp_intro: picked.signature,
    })
    ok = true
    markWechatSubscribedLocal({ mp_name: picked.nickname })
    emitWechatFeedAdded({
      mp_id: picked.fakeid,
      mp_name: picked.nickname,
      avatar: picked.round_head_img,
      mp_intro: picked.signature,
    })
    if (!opts?.silent) notifySuccess(`已添加：${picked.nickname}`)
    if (!opts?.skipReload) scheduleWechatStateReload()
    return true
  } catch (e: any) {
    const msg = _extractErrMsg(e)
    _markAuthStateFromError('wechat', msg)
    if (msg.includes('扫码授权') || msg.includes('授权')) {
      needWechatAuth.value = true
      startWechatAuth()
    }
    if (!opts?.silent) notifyError(msg || '添加失败')
    return false
  } finally {
    addingMap.value[key] = false
    if (ok) platformAuthStateMap.value.wechat = 'not_required'
  }
}

const loadSourcePresets = async () => {
  try {
    const res: any = await listSourcePlatformPresets()
    sourcePresets.value = res?.list || []
  } catch {
    sourcePresets.value = []
  }
}

const loadSourceFeeds = async () => {
  sourceListLoading.value = true
  try {
    const res: any = await listSourceFeeds({ limit: 1000, offset: 0 })
    sourceFeeds.value = res?.list || []
  } catch (e: any) {
    sourceFeeds.value = []
    notifyError(e?.message || '加载订阅失败')
  } finally {
    sourceListLoading.value = false
  }
}

const sourceFeedAvatar = (item: SourceFeedItem) => {
  const raw = String(item?.source_url || '').trim()
  if (!raw) return '/static/default-avatar.png'
  try {
    const u = new URL(raw)
    return `${u.origin}/favicon.ico`
  } catch {
    return '/static/default-avatar.png'
  }
}

const _presetTargetUrl = (preset: SourcePresetItem): string => {
  const st = String(preset?.source_type || 'rss').toLowerCase()
  if (st === 'rss') return String(preset.source_url || '').trim()
  const base = String(rsshubBaseUrl.value || '').trim().replace(/\/+$/, '')
  const route = String(preset.rsshub_route_template || '').trim().replace(/^\/+/, '')
  if (!base || !route) return ''
  return `${base}/${route}`
}

const isPresetAdded = (preset: SourcePresetItem) => {
  const url = _presetTargetUrl(preset)
  if (!url) return false
  return sourceFeeds.value.some((x) => String(x.source_url || '').trim() === url)
}

const _buildPayloadByPreset = (preset: SourcePresetItem) => {
  const st = (preset?.source_type || 'rss') as 'rss' | 'rsshub'
  return {
    source_type: st,
    source_platform: preset.platform || undefined,
    source_url: st === 'rss' ? String(preset.source_url || '').trim() : undefined,
    rsshub_base_url: st === 'rsshub' ? String(rsshubBaseUrl.value || '').trim() : undefined,
    rsshub_route: st === 'rsshub' ? String(preset.rsshub_route_template || '').trim() : undefined,
    name: String(preset.name || '').trim() || undefined,
    auto_subscribe: true,
  }
}

const quickAddPreset = async (preset: SourcePresetItem) => {
  if (sourceSubmitting.value) return
  sourceSubmitting.value = true
  try {
    const res: any = await addSourceFeed(_buildPayloadByPreset(preset))
    if (res?.warning) notifyInfo(String(res.warning))
    const feedPayload = res?.feed || {
      id: String(res?.feed?.id || ''),
      name: String(res?.feed?.name || preset.name || ''),
      source_type: String(res?.feed?.source_type || preset.source_type || 'rss'),
      source_platform: String(res?.feed?.source_platform || preset.platform || ''),
      source_url: String(res?.feed?.source_url || _presetTargetUrl(preset) || ''),
    }
    upsertLocalSourceFeed(feedPayload)
    emitSourceFeedAdded(feedPayload)
    notifySuccess(`已添加：${preset.name}`)
    platformAuthStateMap.value[String(preset.platform || '').toLowerCase()] = 'not_required'
    scheduleSourceStateReload()
  } catch (e: any) {
    _markAuthStateFromError(String(preset.platform || '').toLowerCase(), e)
    if (platformSupportsScanAuth(String(preset.platform || ''))) {
      const msg = _extractErrMsg(e)
      if (AUTH_REQUIRED_RE.test(msg)) {
        notifyInfo(`${managePlatformLabel.value}需要先扫码授权，再执行添加`)
        startWechatAuth()
      }
    }
    notifyError(_extractErrMsg(e) || '添加失败')
  } finally {
    sourceSubmitting.value = false
  }
}

const addSelectedPlatformBlogger = async () => {
  const preset = selectedPlatformPresetItem.value
  if (!preset) {
    notifyWarning('请先搜索并选择一个博主')
    return
  }
  await quickAddPreset(preset)
}

const batchAddWechatCreators = async () => {
  if (platformDefaultsImporting.value) return
  const selected = Array.from(new Set(selectedWechatBatchNames.value.map((x) => String(x || '').trim()).filter(Boolean)))
  if (!selected.length) {
    notifyWarning('请先选择要批量添加的公众号')
    return
  }
  const itemMap = new Map<string, PlazaItem>()
  for (const it of wechatPlazaItems.value) {
    const key = String(it.name || '').trim()
    if (!key || itemMap.has(key)) continue
    itemMap.set(key, it)
  }
  const candidates = selected.map((x) => itemMap.get(x)).filter((x): x is PlazaItem => !!x)
  if (!candidates.length) {
    notifyWarning('未找到可添加的公众号')
    return
  }
  platformDefaultsImporting.value = true
  let ok = 0
  let fail = 0
  let skip = 0
  try {
    const workers = Math.min(3, candidates.length)
    let cursor = 0
    const worker = async () => {
      while (cursor < candidates.length) {
        const it = candidates[cursor++]
        if (isSubscribed(it)) {
          skip += 1
          continue
        }
        const added = await subscribeFromPlaza(it, { silent: true, skipReload: true })
        if (added) ok += 1
        else fail += 1
      }
    }
    await Promise.all(Array.from({ length: workers }).map(() => worker()))
    if (ok > 0) scheduleWechatStateReload()
    selectedWechatBatchNames.value = []
    if (ok > 0) notifySuccess(`已批量添加公众号 ${ok} 个`)
    if (skip > 0) notifyInfo(`已跳过 ${skip} 个已订阅公众号`)
    if (fail > 0) notifyInfo(`部分公众号添加失败（${fail}）`)
  } finally {
    platformDefaultsImporting.value = false
  }
}

const batchAddPlatformCreators = async () => {
  if (platformDefaultsImporting.value) return
  const selected = Array.from(new Set(selectedPlatformBatchKeys.value.map((x) => String(x || '').trim()).filter(Boolean)))
  if (!selected.length) {
    notifyWarning('请先选择要批量添加的博主')
    return
  }
  const itemMap = new Map<string, SourcePresetItem>()
  for (const it of managePlatformCandidates.value) {
    const key = presetSelectKey(it)
    if (!key || itemMap.has(key)) continue
    itemMap.set(key, it)
  }
  const candidates = selected.map((x) => itemMap.get(x)).filter((x): x is SourcePresetItem => !!x)
  if (!candidates.length) {
    notifyWarning('未找到可添加的博主')
    return
  }
  platformDefaultsImporting.value = true
  let ok = 0
  let fail = 0
  let skip = 0
  try {
    const workers = Math.min(4, candidates.length)
    let cursor = 0
    const worker = async () => {
      while (cursor < candidates.length) {
        const preset = candidates[cursor++]
        if (isPresetAdded(preset)) {
          skip += 1
          continue
        }
        try {
          const res: any = await addSourceFeed(_buildPayloadByPreset(preset))
          const feedPayload = res?.feed || {
            id: String(res?.feed?.id || ''),
            name: String(res?.feed?.name || preset.name || ''),
            source_type: String(res?.feed?.source_type || preset.source_type || 'rss'),
            source_platform: String(res?.feed?.source_platform || preset.platform || ''),
            source_url: String(res?.feed?.source_url || _presetTargetUrl(preset) || ''),
          }
          upsertLocalSourceFeed(feedPayload)
          emitSourceFeedAdded(feedPayload)
          ok += 1
          platformAuthStateMap.value[String(preset.platform || '').toLowerCase()] = 'not_required'
        } catch (e) {
          fail += 1
          _markAuthStateFromError(String(preset.platform || '').toLowerCase(), e)
        }
      }
    }
    await Promise.all(Array.from({ length: workers }).map(() => worker()))
    if (ok > 0) scheduleSourceStateReload()
    selectedPlatformBatchKeys.value = []
    if (ok > 0) notifySuccess(`已批量添加博主 ${ok} 个`)
    if (skip > 0) notifyInfo(`已跳过 ${skip} 个已添加博主`)
    if (fail > 0) notifyInfo(`部分博主添加失败（${fail}）`)
  } finally {
    platformDefaultsImporting.value = false
  }
}

const batchAddCurrentPlatformBloggers = async () => {
  if (managePlatform.value === 'wechat') {
    await batchAddWechatCreators()
    return
  }
  await batchAddPlatformCreators()
}

const refreshOneSource = async (feedId: string) => {
  if (!feedId) return
  sourceRefreshLoadingId.value = feedId
  try {
    const res: any = await refreshSourceFeed(feedId)
    notifySuccess(`刷新完成：新增 ${Number(res?.changed || 0)} 篇`)
  } catch (e: any) {
    notifyError(e?.message || '刷新失败')
  } finally {
    sourceRefreshLoadingId.value = ''
  }
}

const removeOneSource = async (feedId: string) => {
  if (!feedId) return
  sourceDeleteLoadingId.value = feedId
  try {
    await deleteSourceFeed(feedId, { hard: false })
    removeLocalSourceFeed(feedId)
    emitFeedRemoved(feedId)
    notifySuccess('已删除订阅')
    scheduleSourceStateReload()
  } catch (e: any) {
    notifyError(e?.message || '删除失败')
  } finally {
    sourceDeleteLoadingId.value = ''
  }
}

const goBack = () => {
  if (embedded.value) return
  router.go(-1)
}

onMounted(async () => {
  await Promise.allSettled([
    loadSubscribed(),
    loadPlaza(),
    loadSourcePresets(),
    loadSourceFeeds(),
    getRsshubStatus().then((res: any) => {
      const base = String(res?.internal_url || res?.public_url || '').trim()
      rsshubBaseUrl.value = base.replace(/\/+$/, '')
    }),
  ])
  if (!rsshubBaseUrl.value) rsshubBaseUrl.value = 'http://rsshub:1200'
  if (!managePlatformOptions.value.find((x) => x.value === managePlatform.value)) {
    managePlatform.value = managePlatformOptions.value[0]?.value || 'zhihu'
  }
})
</script>

<style scoped>
.add-subscription {
  padding: 12px 0 0;
  max-width: 100%;
  margin: 0 auto;
}

.platform-manage {
  display: grid;
  gap: 12px;
}

.platform-switch {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  align-items: center;
}

.platform-chip {
  cursor: pointer;
}

.inline-row {
  display: flex;
  gap: 8px;
  align-items: center;
  flex-wrap: wrap;
}

.toolbar-line {
  display: flex;
  gap: 8px;
  align-items: center;
  flex-wrap: wrap;
  padding-bottom: 2px;
}

.compact-toolbar :deep(.arco-select-view),
.compact-toolbar :deep(.arco-input-wrapper) {
  height: 30px;
}

.compact-toolbar :deep(.arco-btn-size-small) {
  height: 30px;
  padding: 0 10px;
}

.nowrap-head {
  flex-wrap: wrap;
  padding-bottom: 2px;
}

.wechat-option {
  display: grid;
  gap: 2px;
  min-width: 0;
}

.wechat-option-name {
  font-weight: 700;
}

.wechat-option-desc {
  color: var(--color-text-3);
  font-size: 12px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.meta-preview {
  margin-top: 12px;
  display: flex;
  gap: 10px;
  align-items: center;
}

.meta-text {
  min-width: 0;
}

.meta-title {
  font-weight: 700;
}

.meta-sub {
  color: var(--color-text-3);
  font-size: 12px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 640px;
}

.source-title {
  font-weight: 700;
  color: var(--color-text-1);
}

.source-presets {
  border: 1px solid var(--color-neutral-3);
  border-radius: 12px;
  padding: 12px;
}

.source-presets-head {
  display: flex;
  align-items: center;
  justify-content: flex-start;
  gap: 10px;
  margin-bottom: 8px;
  flex-wrap: wrap;
}

.compact-head {
  margin-bottom: 4px;
}

.tag-strip {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  margin: 4px 0 10px;
}

.tag-chip {
  border: 1px solid var(--color-neutral-3);
  background: var(--color-bg-2);
  color: var(--color-text-2);
  border-radius: 999px;
  height: 28px;
  padding: 0 10px;
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
}

.tag-chip.active {
  color: var(--color-primary-6);
  border-color: var(--color-primary-4);
  background: color-mix(in srgb, var(--color-primary-1) 70%, transparent);
}

.preset-grid {
  margin-top: 8px;
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
  gap: 10px;
  max-height: 360px;
  overflow-y: auto;
  padding-right: 4px;
}

.preset-card {
  border: 1px solid var(--color-neutral-3);
  border-radius: 14px;
  min-height: 48px;
  padding: 8px 10px;
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  align-items: center;
  gap: 10px;
  background: var(--color-bg-2);
}

.preset-main {
  min-width: 0;
  display: grid;
  grid-template-columns: 26px minmax(0, 1fr);
  align-items: center;
  gap: 10px;
}

.preset-name-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  min-width: 0;
}

.preset-name {
  font-weight: 700;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.preset-heat {
  flex: 0 0 auto;
  color: var(--color-text-3);
  font-size: 11px;
  white-space: nowrap;
}

.preset-desc {
  color: var(--color-text-3);
  font-size: 12px;
  min-width: 0;
  grid-column: 2;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.preset-tags {
  grid-column: 2;
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.preset-tag {
  display: inline-flex;
  align-items: center;
  height: 20px;
  padding: 0 8px;
  border-radius: 999px;
  background: color-mix(in srgb, var(--color-fill-2) 70%, transparent);
  color: var(--color-text-3);
  font-size: 11px;
  white-space: nowrap;
}

.source-list-wrap {
  border: 1px solid var(--color-neutral-3);
  border-radius: 12px;
  padding: 12px;
}

.source-item {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: center;
}

.source-item-main {
  min-width: 0;
  display: grid;
  grid-template-columns: 28px 1fr;
  align-items: center;
  gap: 2px 8px;
}

.source-item-avatar {
  grid-row: 1 / span 3;
  grid-column: 1;
}

.source-item-title {
  font-weight: 700;
  grid-column: 2;
}

.source-item-sub {
  margin-top: 2px;
  color: var(--color-text-3);
  font-size: 12px;
  grid-column: 2;
}

.source-item-url {
  margin-top: 4px;
  color: var(--color-text-3);
  font-size: 12px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: min(58vw, 820px);
  grid-column: 2;
}

.muted {
  color: var(--color-text-3);
  padding: 8px 0;
}
</style>
