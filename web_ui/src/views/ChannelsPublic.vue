<template>
  <div class="channels-page">
    <a-layout class="channels-layout">
      <a-layout-sider class="sider" :width="leftSiderWidth" :style="{ '--sider-width': `${leftSiderWidth}px` }">
        <div class="sider-top">
          <div class="sider-search">
            <a-input v-model="channelKw" size="small" allow-clear placeholder="搜索订阅" @press-enter="loadFeeds" />
          </div>
          <div class="topic-tabs" role="tablist" aria-label="频道标签">
            <button
              class="topic-chip"
              :class="{ active: !activeTopic }"
              type="button"
              @click="showAllFeeds"
            >
              全部订阅
            </button>
            <button
              v-for="t in topics"
              :key="t.id"
              class="topic-chip"
              :class="{ active: activeTopic && String(activeTopic.id) === String(t.id) }"
              type="button"
              @click="selectTopic(t)"
            >
              {{ t.name }}
            </button>
          </div>
        </div>

        <a-spin :loading="channelsLoading">
          <div class="sider-list">
            <a-list :bordered="false" class="channel-list">
              <a-list-item
                v-for="c in filteredChannels"
                :key="c.id"
                class="channel-item"
                :class="{ active: c.id === activeChannelId }"
                @click="selectChannel(c.id)"
              >
                <div class="channel-item-row" :class="{ editing: canShowDeleteAction }" :title="c.intro || c.name">
                  <a-avatar :size="40" :image-url="channelAvatar(c)">
                    <img :src="channelAvatar(c)" />
                  </a-avatar>
                  <div class="channel-main">
                    <div class="channel-name">{{ c.name }}</div>
                    <div
                      class="channel-platform"
                      :class="{ 'channel-platform-compact': feedPlatform(c) !== 'wechat' }"
                    >
                      {{ channelSubline(c) }}
                    </div>
                  </div>
                  <a-button
                    v-if="canShowDeleteAction"
                    size="mini"
                    type="outline"
                    status="danger"
                    class="feed-delete-btn"
                    :loading="String(deletingFeedId) === String(c.id)"
                    @mousedown.stop.prevent
                    @click.stop.prevent="handleDeleteFeed(c)"
                  >
                    删除
                  </a-button>
                </div>
              </a-list-item>
            </a-list>
          </div>
        </a-spin>
      </a-layout-sider>

      <a-layout-content class="content">
        <div class="content-head">
          <div class="content-search-row">
            <a-input
              v-model="articleKw"
              size="small"
              class="search-input"
              allow-clear
              placeholder="搜索文章关键词"
              @press-enter="loadArticles"
            />
            <a-button size="small" class="search-btn" @click="loadArticles" :loading="articlesLoading">搜索</a-button>
            <a-button
              v-if="hasToken"
              size="small"
              type="primary"
              class="refresh-all-btn"
              :loading="refreshAllLoading"
              @click="refreshAllSubscriptions"
            >
              一键刷新
            </a-button>
            <a-tag class="status-inline-tag" color="arcoblue">{{ activeChannelName || allFeedsLabel }}</a-tag>
          </div>
          <div class="content-head-top">
            <div class="platform-tabs" role="tablist" aria-label="平台标签">
              <button
                v-for="tab in platformTabs"
                :key="tab.key"
                class="platform-tab"
                :class="{ active: activePlatform === tab.key }"
                type="button"
                @click="setPlatform(tab.key)"
              >
                <span class="platform-tab-name" :class="{ 'platform-tab-name-compact': tab.key !== 'all' && tab.key !== 'wechat' }">
                  {{ tab.label }}
                </span>
                <span class="platform-tab-count" :class="{ 'platform-tab-count-compact': tab.key !== 'all' && tab.key !== 'wechat' }">
                  {{ platformStats[tab.key]?.feed_total || 0 }}
                </span>
              </button>
            </div>
          </div>
        </div>

        <a-spin :loading="articlesLoading" class="articles-spin">
          <div class="articles-area">
            <div v-if="!activeChannelId" class="empty">请选择一个频道（左侧）</div>
            <div v-else class="articles">
              <template v-for="group in groupedArticles" :key="group.date">
                <div class="date-sep">{{ group.date }}</div>
                <div class="article-cards">
                  <a-card
                    v-for="a in group.items"
                    :key="articleKey(a)"
                    class="article-card"
                    :class="{ active: articleIdentity(a) === activeArticleId, read: (a as any).is_read }"
                    :hoverable="true"
                    @click="selectArticle(a)"
                    @dblclick.stop="onArticleDblClick(a)"
                  >
                    <div class="article-row">
                      <div class="thumb">
                        <img
                          v-if="articleThumb(a)"
                          :src="articleThumb(a)"
                          loading="lazy"
                          referrerpolicy="no-referrer"
                          @error="(e:any) => { try { (e.target as HTMLImageElement).src = '/static/default-avatar.png' } catch {} }"
                        />
                        <div v-else class="thumb-placeholder" />
                      </div>
                      <div class="body">
                        <div class="article-title-row">
                          <div class="article-title">{{ a.title }}</div>
                          <div class="article-head-meta">
                            <div class="article-source" :title="a.mp_name || activeChannelName">{{ a.mp_name || activeChannelName }}</div>
                            <span class="dot">·</span>
                            <span class="article-publish-time">{{ formatRelative(a.publish_time) }}</span>
                          </div>
                        </div>
                        <div class="article-subtitle">{{ excerpt(a.description) }}</div>
                      </div>
                    </div>
                  </a-card>
                </div>
              </template>
            </div>
          </div>
        </a-spin>
      </a-layout-content>

      <a-layout-sider class="reader" :width="700">
        <div class="reader-inner">
          <div v-if="!activeArticleId" class="empty">选择一篇文章查看全文速览</div>
          <a-spin v-else :loading="articleDetailLoading">
            <div class="reader-title">{{ activeArticleTitle }}</div>
            <div class="reader-meta-row">
              <span>{{ activeArticleSource || activeChannelName }}</span>
              <span class="dot">·</span>
              <span>{{ activeArticlePublished ? formatRelative(activeArticlePublished) : '' }}</span>
            </div>

            <div class="reader-tabs single-line" role="tablist" aria-label="文章详情标签">
              <button class="reader-tab" :class="{ active: readerTab === 'preview' }" type="button" @click="readerTab = 'preview'">
                正文预览
              </button>
              <button class="reader-tab" :class="{ active: readerTab === 'insight' }" type="button" @click="readerTab = 'insight'">
                关键信息
              </button>
              <button class="reader-tab" :class="{ active: readerTab === 'summary' }" type="button" @click="readerTab = 'summary'">
                摘要
              </button>
            </div>

            <template v-if="readerTab === 'preview'">
              <div class="full-content" v-if="previewHtml" v-html="previewHtml"></div>
              <div class="section-body text" v-else>
                暂无可用正文。若该站点限制抓取，请点击下方“新窗口打开”查看原文。
              </div>
              <div class="reader-actions preview-actions">
                <a-button
                  v-if="activeArticleUrl"
                  size="mini"
                  type="text"
                  class="open-origin-btn"
                  @click="openActiveArticleUrl"
                >
                  新窗口打开
                </a-button>
              </div>
            </template>

            <template v-else-if="readerTab === 'insight'">
              <div class="reader-section-title">关键信息</div>
              <div class="reader-actions">
                <a-button
                  v-if="hasToken"
                  size="mini"
                  type="outline"
                  :loading="keyPointsGenerating"
                  @click="generateKeyPointsNow"
                >
                  重新生成
                </a-button>
              </div>
              <a-spin :loading="insightLoading || keyPointsGenerating">
                <div class="highlight" v-if="insightHighlightText">{{ insightHighlightText }}</div>
                <a-list class="kp-list" :bordered="false" v-if="insightPoints.length">
                  <a-list-item v-for="(item, idx) in insightPoints" :key="`kp-${idx}`" class="kp-item">
                    <span class="kp-bullet">{{ idx + 1 }}</span>
                    <span class="kp-text">{{ item }}</span>
                  </a-list-item>
                </a-list>
                <div v-else class="section-body text">{{ keyInfoFallbackText }}</div>
              </a-spin>
            </template>

            <template v-else>
              <div class="reader-section-title">摘要</div>
              <div class="reader-actions">
                <a-button
                  v-if="hasToken"
                  size="mini"
                  type="primary"
                  :loading="summaryGenerating"
                  @click="generateSummaryNow"
                >
                  快速生成
                </a-button>
              </div>
              <a-spin :loading="insightLoading || summaryGenerating">
                <div class="summary-box">{{ summaryText }}</div>
              </a-spin>
            </template>
          </a-spin>
        </div>
      </a-layout-sider>
    </a-layout>

  </div>
</template>

<script setup lang="ts">
import { computed, inject, onMounted, onUnmounted, ref, unref, watch, type Ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Modal } from '@arco-design/web-vue'
import { notifyError, notifyInfo, notifySuccess } from '@/utils/notify'
import { onChannelFeedChanged, type SubscriptionFeedChangedDetail } from '@/utils/subscriptionEvents'
import {
  getArticleDetailPublic,
  getPublicChannelArticles,
  getPublicChannels,
  getPublicInsights,
  PublicInsights
} from '@/api/public'
import {
  backfillArticle,
  fetchArticleContent,
  getAuthedInsights,
  getChannelFeeds,
  getChannelArticles,
  setArticleRead,
  ChannelFeedItem
} from '@/api/channels'
import { UpdateMps, deleteMpApi } from '@/api/subscription'
import { listTags } from '@/api/tagManagement'
import { deleteSourceFeed, refreshAllSourceFeeds, refreshSourceFeed } from '@/api/sources'
import { batchCacheInsights, generateAiSummary, generateKeyPoints as generateAuthedKeyPoints, warmupInsights } from '@/api/insights'

const route = useRoute()
	const router = useRouter()
	
	const channelsLoading = ref(false)
	const channelsRefreshing = ref(false)
	const channels = ref<ChannelFeedItem[]>([])
	const channelKw = ref('')
	const activeChannelId = ref<string>('')
	const activeChannelName = ref<string>('')
	
	const articlesLoading = ref(false)
	const articlesRefreshing = ref(false)
	const articles = ref<any[]>([])
		const articleKw = ref('')
		const activeArticleId = ref<string>('')
		const activeArticleTitle = ref<string>('')
		const activeArticleDesc = ref<string>('')
const activeArticleSource = ref<string>('')
const activeArticlePublished = ref<number>(0)
const activeArticleUrl = ref<string>('')
const activeArticlePlatform = ref<string>('wechat')
const activeArticleContentHtml = ref<string>('')
const activeArticleContentText = ref<string>('')
const articleDetailLoading = ref(false)
const readerTab = ref<'preview' | 'insight' | 'summary'>('preview')
const keyPointsGenerating = ref(false)
const summaryGenerating = ref(false)

const insightLoading = ref(false)
const insight = ref<PublicInsights | null>(null)
const insightRetry = ref(0)
const INSIGHT_RETRY_MAX = 10
const INSIGHT_RETRY_DELAYS_MS = [900, 1600, 2600, 3800, 5200, 7000]
const FAST_REFRESH_DELAYS_MS = [700, 1600, 3000, 5000]
const ARTICLE_WARMUP_DELAYS_MS = [800, 1800, 3200, 5000]
const DETAIL_REFRESH_MIN_INTERVAL_MS = 1400
let insightRetryTimer: any = null
const autoFetchedContent = new Set<string>()
const insightWarmupTriggered = new Set<string>()
const articleDetailFetchedAt = new Map<string, number>()

const autoUpdateLoading = ref(false)
const autoUpdatedAt = new Map<string, number>()
const AUTO_UPDATE_MIN_INTERVAL_MS = 2 * 60 * 1000
const SOURCE_AUTO_UPDATE_MIN_INTERVAL_MS = 10 * 60 * 1000
const refreshAllLoading = ref(false)
const deletingFeedId = ref('')
const editMode = inject<Ref<boolean> | boolean>('channelsEditMode', ref(false))
const refreshAllLastAt = ref(0)
const REFRESH_ALL_MIN_INTERVAL_MS = 20 * 1000
const INSIGHTS_BATCH_LIMIT = 160
const AUTO_POLL_MS = 60 * 1000
const ARTICLE_DETAIL_CACHE_KEY = 'dasheng.article.detail.cache.v1'
const ARTICLE_DETAIL_CACHE_MAX = 400
const ARTICLE_LIST_CACHE_KEY = 'dasheng.article.list.cache.v1'
const ARTICLE_LIST_CACHE_MAX = 90
const ARTICLE_LIST_CACHE_TTL_MS = 20 * 60 * 1000
let pollTimer: any = null
let articlesRequestSeq = 0
let articleDetailRequestSeq = 0
let optimisticFeedSyncTimer: ReturnType<typeof setTimeout> | null = null
let stopFeedChangedListener: (() => void) | null = null

const hasToken = computed(() => !!localStorage.getItem('token'))
const isEditModeActive = computed(() => Boolean(unref(editMode as any)))
const canShowDeleteAction = computed(() => hasToken.value && isEditModeActive.value)
const baseUrl = computed(() => (import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, ''))
const activePlatform = ref<string>('all')
const activeTopic = ref<any | null>(null)
const activeTopicFeedIds = ref<string[]>([])
const viewportWidth = ref<number>(typeof window === 'undefined' ? 1440 : window.innerWidth)
const leftSiderWidth = computed(() => {
  const width = Number(viewportWidth.value || 1440)
  if (width <= 1280) return 204
  if (width <= 1440) return 216
  if (width <= 1680) return 228
  return 236
})

const handleViewportResize = () => {
  viewportWidth.value = typeof window === 'undefined' ? 1440 : window.innerWidth
}

const PLATFORM_LABELS: Record<string, string> = {
  all: '全部平台',
  wechat: '公众号',
  zhihu: '知乎',
  xueqiu: '雪球',
  toutiao: '头条',
  baijiahao: '百家号',
  weibo: '微博',
  portal: '门户',
  rss: '订阅源'
}
const PLATFORM_ORDER = ['wechat', 'zhihu', 'xueqiu', 'toutiao', 'baijiahao', 'weibo', 'portal', 'rss']
const PLATFORM_LOGOS: Record<string, string> = {
  wechat: '/static/default-avatar.png',
  zhihu: '/static/channel-logos/culture.svg',
  xueqiu: '/static/channel-logos/finance.svg',
  toutiao: '/static/channel-logos/portal.svg',
  baijiahao: '/static/channel-logos/portal.svg',
  weibo: '/static/channel-logos/culture.svg',
  portal: '/static/channel-logos/global.svg',
  rss: '/static/channel-logos/tech.svg',
  all: '/static/channel-logos/portal.svg'
}

const normalizePlatform = (value: string | undefined | null) => {
  const raw = String(value || '').trim().toLowerCase()
  if (!raw) return ''
  if (raw === 'wx') return 'wechat'
  if (raw === 'rsshub') return 'rss'
  if (
    [
      'wsj',
      'bbc',
      'nytimes',
      'guardian',
      'cnn',
      'npr',
      'cnbc',
      'tech',
      'global_news',
      'global_tech',
      'global_finance',
      'global_programming',
      'global_startups',
      'china_news',
      'china_tech',
      'china_finance',
      'china_product'
    ].includes(raw)
  ) {
    return 'portal'
  }
  return raw
}

const feedPlatform = (feed: any) => {
  const explicit = normalizePlatform(feed?.source_platform)
  if (explicit) return explicit
  const sourceType = String(feed?.source_type || '').toLowerCase()
  if (sourceType === 'rss') return 'rss'
  if (sourceType === 'rsshub') return 'rss'
  return 'wechat'
}

const platformLabel = (platform: string) => PLATFORM_LABELS[platform] || platform.toUpperCase()

const channelSubline = (feed: any) => {
  const intro = String(feed?.intro || '').replace(/\s+/g, ' ').trim()
  if (intro) return intro
  return '暂无简介'
}

const filteredChannels = computed(() => {
  let list = channels.value
  if (activeTopicFeedIds.value.length) {
    const topicSet = new Set(activeTopicFeedIds.value)
    list = list.filter((x) => topicSet.has(String(x.id || '')))
  }
  if (activePlatform.value !== 'all') {
    list = list.filter((x) => feedPlatform(x) === activePlatform.value)
  }
  return [...list].sort((a, b) => {
    const ua = Number(a.unread_count || 0)
    const ub = Number(b.unread_count || 0)
    if (ua !== ub) return ub - ua
    return String(a.name || '').localeCompare(String(b.name || ''))
  })
})

const platformTabs = computed(() => {
  const fixed = ['all', ...PLATFORM_ORDER]
  const set = new Set<string>(fixed)
  channels.value.forEach((x) => set.add(feedPlatform(x)))
  const dynamic = Array.from(set).filter((x) => x !== 'all')
  dynamic.sort((a, b) => {
    const ia = PLATFORM_ORDER.indexOf(a)
    const ib = PLATFORM_ORDER.indexOf(b)
    if (ia >= 0 && ib >= 0) return ia - ib
    if (ia >= 0) return -1
    if (ib >= 0) return 1
    return a.localeCompare(b)
  })
  return ['all', ...dynamic].map((key) => ({ key, label: platformLabel(key) }))
})

const platformStats = computed(() => {
  const stats: Record<string, { feed_total: number; unread_total: number }> = {
    all: { feed_total: channels.value.length, unread_total: feedsStats.value.unread_total || 0 }
  }
  for (const c of channels.value) {
    const p = feedPlatform(c)
    if (!stats[p]) stats[p] = { feed_total: 0, unread_total: 0 }
    stats[p].feed_total += 1
    stats[p].unread_total += Number(c.unread_count || 0)
  }
  return stats
})

const allFeedsLabel = computed(() => {
  if (activeTopic.value?.name) return `${activeTopic.value.name} · 全部`
  return activePlatform.value === 'all' ? '全部订阅' : `${platformLabel(activePlatform.value)} · 全部`
})

const articlePlatform = (article: any) => {
  const fromArticle = normalizePlatform(String(article?.source_platform || ''))
  if (fromArticle) return fromArticle
  const feed = findFeedById(String(article?.mp_id || ''))
  return feed ? feedPlatform(feed) : (activePlatform.value !== 'all' ? activePlatform.value : 'wechat')
}

const normalizePlainText = (raw: string) => {
  const source = String(raw || '')
  // Some upstream fields contain truncated fragments like "<img src=\"..."
  // that are not valid HTML; strip them before generic normalization.
  const stripped = source.replace(/<[^>\n]*(>|$)/g, ' ')
  const fromHtml = htmlToPlainText(stripped)
  const normalized = normalizePortalText(fromHtml || stripped)
  const oneLine = normalized.replace(/\n+/g, ' ').trim()
  if (oneLine && oneLine.length < 120 && NOISE_RE.test(oneLine)) return ''
  return oneLine
}

const excerpt = (text: string) => {
  const t = normalizePlainText(text)
  if (!t) return ' '
  return t.length > 60 ? `${t.slice(0, 60)}…` : t
}

const proxiedWeChatImg = (url: string) => {
  const u = (url || '').trim()
  if (!u) return ''
  if (u.startsWith('/static/') || u.startsWith('/assets/') || u.startsWith('data:')) return u
  if (!/^https?:\/\//i.test(u)) return u
  try {
    const host = new URL(u).hostname
    const allow = ['mmbiz.qpic.cn', 'mmbiz.qlogo.cn', 'mmecoa.qpic.cn']
    if (!allow.includes(host)) return u
    const base = baseUrl.value ? `${baseUrl.value}/static/res/logo/` : '/static/res/logo/'
    return `${base}${u}`
  } catch {
    return u
  }
}

const channelAvatar = (feed: any) => {
  const cover = proxiedWeChatImg(String(feed?.cover || ''))
  if (cover) return cover
  return PLATFORM_LOGOS[feedPlatform(feed)] || '/static/default-avatar.png'
}

const sourceLogo = (nameOrPlatform: string) => {
  const key = String(nameOrPlatform || '').trim().toLowerCase()
  if (!key) return PLATFORM_LOGOS.portal
  if (key.includes('雪球')) return PLATFORM_LOGOS.xueqiu
  if (key.includes('知乎')) return PLATFORM_LOGOS.zhihu
  if (key.includes('微博')) return PLATFORM_LOGOS.weibo
  if (key.includes('头条')) return PLATFORM_LOGOS.toutiao
  if (key.includes('百家')) return PLATFORM_LOGOS.baijiahao
  if (key.includes('bbc') || key.includes('wsj') || key.includes('guardian') || key.includes('nytimes')) {
    return PLATFORM_LOGOS.portal
  }
  return PLATFORM_LOGOS[key] || PLATFORM_LOGOS.portal
}

const normalizeUrl = (src: string) => {
  const raw = String(src || '').trim()
  if (!raw) return ''
  if (raw.startsWith('//')) return `https:${raw}`
  return raw
}

const extractFirstImageFromHtml = (html: string) => {
  const raw = String(html || '').trim()
  if (!raw || typeof window === 'undefined') return ''
  try {
    const parser = new DOMParser()
    const doc = parser.parseFromString(raw, 'text/html')
    const img = doc.querySelector('img')
    const src = normalizeUrl(String(img?.getAttribute('src') || img?.getAttribute('data-src') || ''))
    return proxiedWeChatImg(src)
  } catch {
    return ''
  }
}

const articleThumb = (article: any) => {
  const pic = proxiedWeChatImg(String(article?.pic_url || article?._thumb || ''))
  if (pic) return pic
  const fromDesc = extractFirstImageFromHtml(String(article?.description || ''))
  if (fromDesc) return fromDesc
  const fromContent = extractFirstImageFromHtml(String(article?.content || ''))
  if (fromContent) return fromContent
  return sourceLogo(String(article?.mp_name || articlePlatform(article)))
}

const NOISE_RE =
  /(点击上方|长按识别|扫码|二维码|关注我们|关注公众号|商务合作|转载请|免责声明|本文来源|本文来自|投稿|联系方式|电话|微信|QQ|邮箱|阅读原文|广告|推广|版权所有|原创不易|欢迎转发)/i

const splitIntoReadableLines = (raw: string) => {
  const text = String(raw || '')
    .replace(/\r\n?/g, '\n')
    .replace(/\u00a0/g, ' ')
    .replace(/\u3000/g, ' ')
    .replace(/[ \t]+/g, ' ')
    .replace(/\n{3,}/g, '\n\n')

  const rough = text
    .split('\n')
    .map((x) => x.trim())
    .filter(Boolean)

  const lines: string[] = []
  for (const row of rough) {
    const line = String(row || '').trim()
    if (!line) continue
    if (line.length <= 140) {
      lines.push(line)
      continue
    }
    // Very long single-line portal text: split by comma-like punctuation to improve readability.
    const tokens = line.split(/([，,、])/g).map((x) => x.trim()).filter(Boolean)
    const parts: string[] = []
    for (let i = 0; i < tokens.length; i++) {
      const t = tokens[i]
      if (i < tokens.length - 1 && /^[，,、]$/.test(tokens[i + 1])) {
        parts.push(`${t}${tokens[i + 1]}`)
        i += 1
      } else {
        parts.push(t)
      }
    }
    if (parts.length <= 1) {
      // No punctuation at all: force-wrap by length to avoid giant one-line blocks.
      const chunkSize = 78
      for (let i = 0; i < line.length; i += chunkSize) {
        const chunk = line.slice(i, i + chunkSize).trim()
        if (chunk) lines.push(chunk)
      }
      continue
    }
    let buf = ''
    for (const part of parts) {
      const next = `${buf}${part}`
      if (next.length >= 70) {
        lines.push(next.trim())
        buf = ''
      } else {
        buf = next
      }
    }
    if (buf.trim()) lines.push(buf.trim())
  }
  return lines
}

const normalizeWechatText = (raw: string) => {
  const text = String(raw || '')
    .replace(/\r\n?/g, '\n')
    .replace(/\u00a0/g, ' ')
    .replace(/\u3000/g, ' ')
    .replace(/[ \t]+/g, ' ')
    .replace(/\n{3,}/g, '\n\n')

  return text
    .split('\n')
    .map((line) => line.trim())
    .filter((line) => line && !(line.length < 120 && NOISE_RE.test(line)))
    .join('\n')
}

const cleanTextLines = (raw: string) =>
  splitIntoReadableLines(raw)
    .filter((x) => !(x.length < 120 && NOISE_RE.test(x)))
    .join('\n')

const escapeHtml = (raw: string) =>
  String(raw || '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;')

const textToPreviewHtml = (raw: string, opts?: { preserveParagraphs?: boolean }) => {
  const source = opts?.preserveParagraphs ? normalizeWechatText(raw) : cleanTextLines(raw)
  const lines = source
    .replace(/\u00a0/g, ' ')
    .replace(/[ \t]+\n/g, '\n')
    .replace(/\n{3,}/g, '\n\n')
    .split('\n')
    .map((x) => x.trim())
    .filter(Boolean)

  if (!lines.length) return ''

  const blocks: string[] = []
  let listItems: string[] = []
  const detectHeading = (line: string): { level: number; text: string } | null => {
    const markdownHeading = line.match(/^(#{1,4})\s+(.+)$/)
    if (markdownHeading) {
      return { level: Math.min(4, markdownHeading[1].length), text: markdownHeading[2] }
    }
    const cnPrimary = line.match(/^[一二三四五六七八九十]+[、.．]\s*(.+)$/)
    if (cnPrimary) return { level: 2, text: cnPrimary[1] }
    const cnSecondary = line.match(/^（[一二三四五六七八九十]+）\s*(.+)$/)
    if (cnSecondary) return { level: 3, text: cnSecondary[1] }
    const digitHeading = line.match(/^\d+[、.．]\s*(.+)$/)
    if (digitHeading) return { level: 3, text: digitHeading[1] }
    return null
  }

  const flushList = () => {
    if (listItems.length) {
      blocks.push(`<ul>${listItems.join('')}</ul>`)
      listItems = []
    }
  }

  for (const line of lines) {
    const quote = line.match(/^>\s*(.+)$/)
    if (quote) {
      flushList()
      blocks.push(`<blockquote>${escapeHtml(quote[1])}</blockquote>`)
      continue
    }
    const bullet = line.match(/^[-*•·]\s+(.+)$/) || line.match(/^\d+[\.、]\s+(.+)$/)
    if (bullet) {
      listItems.push(`<li>${escapeHtml(bullet[1])}</li>`)
      continue
    }
    const heading = detectHeading(line)
    if (heading) {
      flushList()
      blocks.push(`<h${heading.level}>${escapeHtml(heading.text)}</h${heading.level}>`)
      continue
    }
    flushList()
    blocks.push(`<p>${escapeHtml(line)}</p>`)
  }
  flushList()
  return blocks.join('')
}

const htmlToPlainText = (raw: string) => {
  const html = String(raw || '').trim()
  if (!html || typeof window === 'undefined') return ''
  try {
    const doc = new DOMParser().parseFromString(html, 'text/html')
    return String(doc.body.textContent || '')
  } catch {
    return ''
  }
}

const normalizePortalText = (raw: string) => {
  const base = String(raw || '')
    .replace(/!\[[^\]]*\]\(([^)]+)\)/g, ' ')
    .replace(/\[([^\]]+)\]\((https?:\/\/[^)]+)\)/g, '$1')
    .replace(/<[^>]+>/g, ' ')
    .replace(/https?:\/\/\S+/g, ' ')
    .replace(/[ \t]+/g, ' ')
    .replace(/\n{3,}/g, '\n\n')

  const lines = cleanTextLines(base)
    .split('\n')
    .map((x) => x.trim())
    .filter(Boolean)

  const seen = new Set<string>()
  const deduped = lines.filter((line) => {
    if (seen.has(line)) return false
    seen.add(line)
    return true
  })
  return deduped.join('\n')
}

const cleanArticleHtml = (raw: string) => {
  const html = String(raw || '').trim()
  if (!html || typeof window === 'undefined') return ''
  try {
    const parser = new DOMParser()
    const doc = parser.parseFromString(html, 'text/html')
    const body = doc.body
    body
      .querySelectorAll(
        'script,style,noscript,iframe,form,button,header,footer,nav,.qr_code_pc_outer,#js_pc_qr_code,.original_area_primary,.wx_profile_card_inner,.advertisement'
      )
      .forEach((el) => el.remove())

    const allow = new Set([
      'p',
      'br',
      'h1',
      'h2',
      'h3',
      'h4',
      'h5',
      'blockquote',
      'div',
      'section',
      'article',
      'span',
      'ul',
      'ol',
      'li',
      'strong',
      'em',
      'b',
      'i',
      'code',
      'pre',
      'img',
      'a',
      'hr',
      'table',
      'thead',
      'tbody',
      'tr',
      'th',
      'td',
      'figure',
      'figcaption'
    ])

    body.querySelectorAll('*').forEach((el) => {
      const tag = el.tagName.toLowerCase()
      if (!allow.has(tag)) {
        const parent = el.parentNode
        if (parent) {
          while (el.firstChild) parent.insertBefore(el.firstChild, el)
          parent.removeChild(el)
        }
        return
      }

      Array.from(el.attributes).forEach((attr) => {
        const name = attr.name.toLowerCase()
        if (name.startsWith('on') || name === 'style' || name === 'class' || name === 'id') {
          el.removeAttribute(attr.name)
        }
      })

      if (tag === 'a') {
        const href = normalizeUrl(String(el.getAttribute('href') || ''))
        if (!href) {
          el.removeAttribute('href')
        } else {
          el.setAttribute('href', href)
          el.setAttribute('target', '_blank')
          el.setAttribute('rel', 'noopener noreferrer nofollow')
        }
      }

      if (tag === 'img') {
        const src = normalizeUrl(String(el.getAttribute('src') || el.getAttribute('data-src') || ''))
        if (!src) {
          el.remove()
          return
        }
        el.setAttribute('src', proxiedWeChatImg(src))
        el.setAttribute('loading', 'lazy')
      }
    })

    body.querySelectorAll('p,li,figcaption,blockquote').forEach((el) => {
      const text = String(el.textContent || '').trim()
      if (!text) {
        if (!el.querySelector('img')) el.remove()
        return
      }
      if (text.length < 120 && NOISE_RE.test(text)) el.remove()
    })

    // Split oversized plain paragraphs only for non-WeChat / portal-like content.
    body.querySelectorAll('p').forEach((el) => {
      if (el.querySelector('img,table,pre,code,ul,ol,blockquote')) return
      const rawText = String(el.textContent || '').trim()
      const parentIsWechat =
        body.querySelector('#js_content, .rich_media_content, .rich_media_content_primary') ||
        /rich_media|js_content|weixin/i.test(String(raw))
      if (!rawText || rawText.length < 140 || parentIsWechat) return
      const lines = splitIntoReadableLines(rawText).filter((x) => !(x.length < 120 && NOISE_RE.test(x)))
      if (lines.length <= 1) return
      const frag = doc.createDocumentFragment()
      for (const line of lines) {
        const p = doc.createElement('p')
        p.textContent = line
        frag.appendChild(p)
      }
      el.replaceWith(frag)
    })

    // Fallback: if content is plain text nodes (no block tags), wrap into <p> paragraphs.
    const hasBlock = !!body.querySelector('p,h1,h2,h3,h4,h5,ul,ol,blockquote,table,figure,pre')
    const fallbackText = String(body.textContent || '').trim()
    if (!hasBlock && fallbackText) {
      const lines = splitIntoReadableLines(fallbackText).filter((x) => !(x.length < 120 && NOISE_RE.test(x)))
      if (lines.length) {
        body.innerHTML = lines.map((line) => `<p>${escapeHtml(line)}</p>`).join('')
      }
    }

    return String(body.innerHTML || '').trim()
  } catch {
    return ''
  }
}

const buildFullText = (content: string, description: string) => {
  const cleanedHtml = cleanArticleHtml(content) || cleanArticleHtml(description)
  if (cleanedHtml) return { html: cleanedHtml, text: htmlToPlainText(cleanedHtml) }
  const parser = typeof window !== 'undefined' ? new DOMParser() : null
  let text = String(description || '')
  if (parser && /<[^>]+>/.test(text)) {
    try {
      const doc = parser.parseFromString(text, 'text/html')
      text = String(doc.body.textContent || '')
    } catch {
      // ignore
    }
  }
  return { html: '', text: cleanTextLines(text) }
}

const openActiveArticleUrl = () => {
  const url = String(activeArticleUrl.value || '').trim()
  if (!url) return
  window.open(url, '_blank', 'noopener,noreferrer')
}

const previewHtml = computed(() => {
  const p = String(activeArticlePlatform.value || '').toLowerCase()
  const html = String(activeArticleContentHtml.value || '').trim()
  if (html) return html
  const portalRaw = String(activeArticleContentText.value || htmlToPlainText(html) || activeArticleDesc.value || '')
  const txt = p === 'wechat'
    ? normalizeWechatText(String(activeArticleContentText.value || activeArticleDesc.value || '')).trim()
    : normalizePortalText(portalRaw).trim()
  if (!txt) return ''
  return textToPreviewHtml(txt, { preserveParagraphs: p === 'wechat' })
})

const descFallbackText = computed(() => normalizePlainText(activeArticleDesc.value))
const summaryText = computed(() => {
  const raw = String(insight.value?.summary || '')
  const normalized = normalizePlainText(raw)
  if (normalized) return normalized
  if (!descFallbackText.value) return '暂无摘要，点击快速生成即可。'
  return descFallbackText.value.length > 320 ? `${descFallbackText.value.slice(0, 320)}…` : descFallbackText.value
})
const insightHighlightText = computed(() => normalizePlainText(String(insight.value?.key_points?.highlight || '')))
const insightPoints = computed(() =>
  Array.isArray(insight.value?.key_points?.points)
    ? (insight.value?.key_points?.points || [])
        .map((item: any) => normalizePlainText(String(item || '')))
        .filter(Boolean)
    : []
)
const keyInfoFallbackText = computed(() => {
  if (!descFallbackText.value) return '暂无关键信息，点击重新生成即可。'
  return descFallbackText.value.length > 240 ? `${descFallbackText.value.slice(0, 240)}…` : descFallbackText.value
})

const shouldAutoFetchContent = (article: any) => {
  // WeChat 与多源都走同一正文抓取接口（后端按 source_type 选择抓取器）。
  const id = String(article?.id || '').trim()
  const url = String(article?.url || '').trim()
  if (!id || !url) return false
  return hasToken.value
}

const shouldMarkAsRead = (article: any) => {
  return hasToken.value && articlePlatform(article) === 'wechat'
}

const shouldLoadInsight = (_article: any) => true

const pad2 = (n: number) => String(n).padStart(2, '0')
const formatDate = (ts: number) => {
  const d = new Date(ts * 1000)
  return `${d.getFullYear()}.${pad2(d.getMonth() + 1)}.${pad2(d.getDate())}`
}

const formatRelative = (ts: number) => {
  if (!ts) return ''
  const diff = Date.now() - ts * 1000
  const mins = Math.floor(diff / 60000)
  if (mins < 60) return `${mins} 分钟前`
  const hrs = Math.floor(mins / 60)
  if (hrs < 24) return `${hrs} 小时前`
  const days = Math.floor(hrs / 24)
  return `${days} 天前`
}

const groupedArticles = computed(() => {
  const groups: Record<string, any[]> = {}
  for (const a of articles.value) {
    const key = formatDate(a.publish_time)
    if (!groups[key]) groups[key] = []
    groups[key].push(a)
  }
  return Object.keys(groups)
    .sort((a, b) => (a > b ? -1 : 1))
    .map(date => ({ date, items: groups[date] }))
})

const unreadOnly = ref(false)
const backfillPages = ref<number>(10)
const topics = ref<any[]>([])
const feedsStats = ref({ unread_total: 0, article_total: 0, feed_total: 0 })

const normalizeTopicMpIds = (raw: any): string[] => {
  if (!raw) return []
  if (Array.isArray(raw)) {
    return raw
      .map(x => String((x && (x.id ?? x.mp_id ?? x)) || '').trim())
      .filter(Boolean)
  }
  if (typeof raw === 'string') {
    const s = raw.trim()
    if (!s) return []
    try {
      return normalizeTopicMpIds(JSON.parse(s))
    } catch {
      // Fallback for non-JSON legacy values (comma-separated).
      return s
        .split(',')
        .map(x => x.trim())
        .filter(Boolean)
    }
  }
  if (typeof raw === 'object') {
    // Fallback for unexpected shapes.
    if (Array.isArray((raw as any).list)) return normalizeTopicMpIds((raw as any).list)
  }
  return []
}

const findFeedById = (id: string) => channels.value.find((x) => x.id === id)

const isSourceFeed = (feed: ChannelFeedItem | undefined) => {
  const st = String(feed?.source_type || '').toLowerCase()
  if (st === 'rss' || st === 'rsshub') return true
  const platform = normalizePlatform(String((feed as any)?.source_platform || ''))
  if (platform && platform !== 'wechat') return true
  const sourceUrl = String((feed as any)?.source_url || '').trim()
  return !!sourceUrl
}

const toErrorMessage = (err: any, fallback: string) => {
  if (!err) return fallback
  const direct = String(err?.message || '').trim()
  if (direct && direct !== '[object Object]') return direct
  const detail = err?.detail
  const nested =
    (typeof detail === 'string' ? detail : '') ||
    String(detail?.message || detail?.msg || '').trim() ||
    String(err?.response?.data?.message || err?.response?.data?.detail || '').trim()
  return nested && nested !== '[object Object]' ? nested : fallback
}

const articleIdentity = (article: any) => {
  const id = String(article?.id || '').trim()
  if (id) return id
  return String(article?.url || article?.link || '').trim()
}

const articleKey = (article: any) => {
  const identity = articleIdentity(article)
  if (identity) return identity
  return `${String(article?.mp_id || '')}-${String(article?.publish_time || 0)}-${String(article?.title || '')}`
}

const readArticleListCache = (): Record<string, any> => {
  try {
    const raw = sessionStorage.getItem(ARTICLE_LIST_CACHE_KEY)
    if (!raw) return {}
    const parsed = JSON.parse(raw)
    return parsed && typeof parsed === 'object' ? parsed : {}
  } catch {
    return {}
  }
}

const writeArticleListCache = (cache: Record<string, any>) => {
  try {
    sessionStorage.setItem(ARTICLE_LIST_CACHE_KEY, JSON.stringify(cache))
  } catch {
    // ignore
  }
}

const buildArticleListCacheKey = () => {
  const channelId = String(activeChannelId.value || 'all').trim() || 'all'
  const topicId = String(activeTopic.value?.id || '').trim()
  const scopedFeedIds =
    channelId === 'all' ? filteredChannels.value.map((item) => String(item.id || '').trim()).filter(Boolean).join(',') : ''
  return [
    hasToken.value ? 'auth' : 'public',
    channelId,
    String(activePlatform.value || 'all'),
    topicId,
    unreadOnly.value ? '1' : '0',
    String(articleKw.value || '').trim().toLowerCase(),
    scopedFeedIds,
  ].join('|')
}

const getArticleListCache = (cacheKey: string): any[] | null => {
  const key = String(cacheKey || '').trim()
  if (!key) return null
  const cache = readArticleListCache()
  const row = cache[key]
  if (!row || typeof row !== 'object') return null
  const items = Array.isArray(row.items) ? row.items : null
  const ts = Number(row.ts || 0)
  if (!items || !ts) return null
  if (Date.now() - ts > ARTICLE_LIST_CACHE_TTL_MS) {
    delete cache[key]
    writeArticleListCache(cache)
    return null
  }
  return items
}

const setArticleListCache = (cacheKey: string, items: any[]) => {
  const key = String(cacheKey || '').trim()
  if (!key || !Array.isArray(items)) return
  const cache = readArticleListCache()
  cache[key] = { ts: Date.now(), items }
  const keys = Object.keys(cache)
  if (keys.length > ARTICLE_LIST_CACHE_MAX) {
    keys
      .sort((a, b) => Number(cache[a]?.ts || 0) - Number(cache[b]?.ts || 0))
      .slice(0, keys.length - ARTICLE_LIST_CACHE_MAX)
      .forEach((k) => delete cache[k])
  }
  writeArticleListCache(cache)
}

const readArticleDetailCache = (): Record<string, any> => {
  try {
    const raw = sessionStorage.getItem(ARTICLE_DETAIL_CACHE_KEY)
    if (!raw) return {}
    const parsed = JSON.parse(raw)
    return parsed && typeof parsed === 'object' ? parsed : {}
  } catch {
    return {}
  }
}

const writeArticleDetailCache = (cache: Record<string, any>) => {
  try {
    sessionStorage.setItem(ARTICLE_DETAIL_CACHE_KEY, JSON.stringify(cache))
  } catch {
    // ignore
  }
}

const getArticleDetailCache = (articleId: string) => {
  const id = String(articleId || '').trim()
  if (!id) return null
  const cache = readArticleDetailCache()
  const row = cache[id]
  return row && typeof row === 'object' ? row : null
}

const setArticleDetailCache = (articleId: string, payload: any) => {
  const id = String(articleId || '').trim()
  if (!id || !payload || typeof payload !== 'object') return
  const cache = readArticleDetailCache()
  cache[id] = { ...payload, ts: Date.now() }
  const keys = Object.keys(cache)
  if (keys.length > ARTICLE_DETAIL_CACHE_MAX) {
    keys
      .sort((a, b) => Number(cache[a]?.ts || 0) - Number(cache[b]?.ts || 0))
      .slice(0, keys.length - ARTICLE_DETAIL_CACHE_MAX)
      .forEach((k) => delete cache[k])
  }
  writeArticleDetailCache(cache)
}

const normalizeFeedPatch = (raw: any): ChannelFeedItem => ({
  id: String(raw?.id || '').trim(),
  name: String(raw?.name || '').trim(),
  cover: String(raw?.cover || raw?.avatar || '').trim(),
  intro: String(raw?.intro || raw?.mp_intro || '').trim(),
  source_type: String(raw?.source_type || 'wechat').toLowerCase(),
  source_platform: normalizePlatform(String(raw?.source_platform || '')),
  source_url: String(raw?.source_url || '').trim(),
  unread_count: Number(raw?.unread_count || 0),
  article_count: Number(raw?.article_count || 0),
  latest_publish_time: Number(raw?.latest_publish_time || 0),
})

const scheduleOptimisticFeedSync = () => {
  if (optimisticFeedSyncTimer) clearTimeout(optimisticFeedSyncTimer)
  optimisticFeedSyncTimer = setTimeout(() => {
    triggerLoadFeeds({ background: true })
    if (activeChannelId.value) triggerLoadArticles({ background: true })
    optimisticFeedSyncTimer = null
  }, 260)
}

const applyOptimisticFeedAdded = (raw: any) => {
  const next = normalizeFeedPatch(raw)
  if (!next.id) return
  const list = [...channels.value]
  const index = list.findIndex((item) => String(item.id || '') === next.id)
  if (index >= 0) list[index] = { ...list[index], ...next }
  else list.unshift(next)
  channels.value = list
  feedsStats.value = {
    ...feedsStats.value,
    feed_total: index >= 0 ? feedsStats.value.feed_total : feedsStats.value.feed_total + 1,
  }
}

const applyOptimisticFeedRemoved = (feedId: string) => {
  const id = String(feedId || '').trim()
  if (!id) return
  const existed = channels.value.some((item) => String(item.id || '') === id)
  channels.value = channels.value.filter((item) => String(item.id || '') !== id)
  activeTopicFeedIds.value = activeTopicFeedIds.value.filter((item) => String(item || '') !== id)
  if (existed) {
    feedsStats.value = {
      ...feedsStats.value,
      feed_total: Math.max(0, Number(feedsStats.value.feed_total || 0) - 1),
    }
  }
  if (activeChannelId.value === id) {
    activeChannelId.value = 'all'
    activeChannelName.value = allFeedsLabel.value
    resetReaderState()
  }
}

const handleFeedChanged = (detail: SubscriptionFeedChangedDetail) => {
  if (!hasToken.value) return
  if (detail.action === 'added') applyOptimisticFeedAdded(detail.feed)
  else applyOptimisticFeedRemoved(detail.feed.id)
  scheduleOptimisticFeedSync()
}

const resetReaderState = () => {
  activeArticleId.value = ''
  activeArticleTitle.value = ''
  activeArticleDesc.value = ''
  activeArticleSource.value = ''
  activeArticlePublished.value = 0
  activeArticleUrl.value = ''
  activeArticlePlatform.value = 'wechat'
  activeArticleContentHtml.value = ''
  activeArticleContentText.value = ''
  readerTab.value = 'preview'
  insight.value = null
}

const triggerLoadArticles = (opts?: { background?: boolean }) => {
  loadArticles(opts).catch(() => {})
}

const triggerLoadFeeds = (opts?: { background?: boolean }) => {
  loadFeeds(opts).catch(() => {})
}

const requestAuthDialog = (tab: 'login' | 'register' = 'login', need: 'none' | 'plaza' = 'none') => {
  notifyInfo(tab === 'register' ? '请先注册后继续' : '请先登录')
  window.dispatchEvent(
    new CustomEvent('dasheng-auth-required', {
      detail: { tab, need, redirect: '/channels' },
    }),
  )
}

const handleDeleteFeed = (feed: ChannelFeedItem) => {
  if (!hasToken.value) {
    requestAuthDialog('login')
    return
  }
  const feedId = String(feed?.id || '').trim()
  if (!feedId) {
    notifyError('订阅ID无效，删除失败')
    return
  }
  if (deletingFeedId.value) {
    notifyInfo('正在删除上一条，请稍候')
    return
  }
  Modal.confirm({
    title: `取消订阅「${feed.name || '该订阅'}」`,
    content: '仅取消当前账号自己的订阅，不会删除系统公共源。',
    okText: '确认删除',
    cancelText: '取消',
    okButtonProps: { status: 'danger' as any },
    onOk: () => {
      deletingFeedId.value = feedId
      // UX first: remove from UI immediately, submit delete in background.
      applyOptimisticFeedRemoved(feedId)
      notifySuccess('已取消订阅')
      ;(async () => {
        try {
          if (isSourceFeed(feed)) {
            await deleteSourceFeed(feedId, { hard: false })
          } else {
            await deleteMpApi(feedId, { hard: false })
          }
        } catch (e: any) {
          notifyError(toErrorMessage(e, '取消订阅失败，已自动回滚列表'))
          triggerLoadFeeds({ background: true })
        } finally {
          deletingFeedId.value = ''
        }
      })()
    }
  })
}

const setPlatform = (platform: string, silent?: boolean) => {
  const raw = String(platform || 'all').trim().toLowerCase()
  activePlatform.value = raw === 'all' ? 'all' : (normalizePlatform(raw) || 'all')
  if (!silent) {
    const query: any = { ...(route.query || {}) }
    if (activePlatform.value === 'all') delete query.platform
    else query.platform = activePlatform.value
    query.channel_id = 'all'
    router.replace({ path: '/channels', query }).catch(() => {})
  }
  if (activeChannelId.value === 'all') {
    activeChannelName.value = allFeedsLabel.value
  }
  activeChannelId.value = 'all'
  activeChannelName.value = allFeedsLabel.value
  articles.value = []
  resetReaderState()
  triggerLoadArticles()
}

const showAllFeeds = () => {
  activeTopic.value = null
  activeTopicFeedIds.value = []
  activeChannelId.value = 'all'
  activeChannelName.value = allFeedsLabel.value
  articles.value = []
  resetReaderState()
  router.replace({
    path: '/channels',
    query: activePlatform.value !== 'all' ? { channel_id: 'all', platform: activePlatform.value } : { channel_id: 'all' }
  }).catch(() => {})
  triggerLoadFeeds()
  triggerLoadArticles()
}

	const loadTopics = async () => {
	  try {
	    const res: any = await listTags({ offset: 0, limit: 200 })
	    topics.value = res?.list || res || []
	  } catch {
	    topics.value = []
	  }
	}

const loadFeeds = async (opts?: { background?: boolean }) => {
	  const background = !!opts?.background
	  if (background) channelsRefreshing.value = true
	  else channelsLoading.value = true
		  try {
			    if (hasToken.value) {
			      const res: any = await getChannelFeeds({ kw: channelKw.value, limit: 200, offset: 0, sort: 'recent' })
			      channels.value = (res.list || []).map((x: any) => ({
              ...x,
              source_type: String(x?.source_type || 'wechat').toLowerCase(),
              source_platform: normalizePlatform(String(x?.source_platform || ''))
            }))
			      feedsStats.value = res.stats || feedsStats.value
			    } else {
			      const res: any = await getPublicChannels({ kw: channelKw.value, limit: 200, offset: 0 })
			      channels.value = (res.list || []).map((c: any) => ({
              ...c,
              source_type: String(c?.source_type || 'wechat').toLowerCase(),
              source_platform: normalizePlatform(String(c?.source_platform || '')),
              unread_count: 0,
              article_count: 0,
              latest_publish_time: 0
            }))
			      feedsStats.value = { unread_total: 0, article_total: 0, feed_total: channels.value.length }
			    }

    if (!activeChannelId.value) {
      const q = (route.query.channel_id as string) || ''
      if (q && (q === 'all' || channels.value.some(c => c.id === q))) {
        selectChannel(q, true)
      } else if (filteredChannels.value.length) {
        selectChannel(filteredChannels.value[0].id, true)
      }
    } else if (activeChannelId.value !== 'all' && !channels.value.some((c) => c.id === activeChannelId.value)) {
      activeChannelId.value = 'all'
      triggerLoadArticles({ background: true })
    } else if (activeChannelId.value !== 'all' && !filteredChannels.value.some((c) => c.id === activeChannelId.value)) {
      activeChannelId.value = 'all'
      triggerLoadArticles({ background: true })
    }
		  } catch (e: any) {
	    if (!background) notifyError(e?.message || '加载频道失败')
	  } finally {
	    channelsLoading.value = false
	    channelsRefreshing.value = false
	}
}

const scheduleFastRefreshPolls = (opts?: { channelId?: string }) => {
  const channelId = String(opts?.channelId || activeChannelId.value || '').trim()
  for (const delay of FAST_REFRESH_DELAYS_MS) {
    setTimeout(() => {
      loadFeeds({ background: true })
      if (!channelId || channelId === 'all' || activeChannelId.value === channelId) {
        loadArticles({ background: true })
      }
    }, delay)
  }
}

const scheduleArticleWarmupPolls = (article: any) => {
  const articleId = String(article?.id || '')
  if (!articleId) return
  for (const delay of ARTICLE_WARMUP_DELAYS_MS) {
    setTimeout(() => {
      if (activeArticleId.value !== articleId) return
      loadArticleDetail(article, { silent: true, skipQuick: true }).catch(() => {})
      if (shouldLoadInsight(article)) {
        loadInsight(articleId).catch(() => {})
      }
    }, delay)
  }
}

const scheduleInsightWarmup = (articleId: string) => {
  const aid = String(articleId || '').trim()
  if (!aid || !hasToken.value) return
  if (insightWarmupTriggered.has(aid)) return
  insightWarmupTriggered.add(aid)
  warmupInsights(aid).catch(() => {})
}

const warmArticleReader = (article: any) => {
  const articleId = String(article?.id || '')
  if (!articleId || !hasToken.value || !shouldAutoFetchContent(article)) return
  if (autoFetchedContent.has(articleId)) return
  autoFetchedContent.add(articleId)
  fetchArticleContent(articleId, { force: false, async_mode: true })
    .catch(() => {})
  if (shouldLoadInsight(article)) {
    loadInsight(articleId).catch(() => {})
  }
  scheduleArticleWarmupPolls(article)
}

const maybeAutoUpdateChannel = async (mpId: string) => {
  if (!hasToken.value) return
  const id = String(mpId || '').trim()
  if (!id || id === 'all') return
  const feed = findFeedById(id)
  if (!feed) return

  const sourceFeed = isSourceFeed(feed)
  const minInterval = sourceFeed ? SOURCE_AUTO_UPDATE_MIN_INTERVAL_MS : AUTO_UPDATE_MIN_INTERVAL_MS
  const last = autoUpdatedAt.get(id) || 0
  if (Date.now() - last < minInterval) return
  autoUpdatedAt.set(id, Date.now())

  // Source feeds must not block channel switch/read experience.
  if (sourceFeed) {
    refreshSourceFeed(id, { async_mode: true, min_interval_seconds: 600 }).catch(() => {})
    setTimeout(() => {
      if (activeChannelId.value === id) {
        loadArticles({ background: true })
      }
    }, 1800)
    return
  }

  autoUpdateLoading.value = true
  try {
    await UpdateMps(id, { start_page: 0, end_page: 1 })
  } catch {
    // ignore
  } finally {
    autoUpdateLoading.value = false
  }
  scheduleFastRefreshPolls({ channelId: id })
}

const refreshAllSubscriptions = async () => {
  if (!hasToken.value) {
    requestAuthDialog('login')
    return
  }
  if (refreshAllLoading.value) return
  const now = Date.now()
  if (now - refreshAllLastAt.value < REFRESH_ALL_MIN_INTERVAL_MS) {
    notifyInfo('操作太频繁，请稍后再试')
    return
  }
  refreshAllLastAt.value = now
  refreshAllLoading.value = true
  try {
    const [wxRes, srcRes] = await Promise.allSettled([
      UpdateMps('all', { start_page: 0, end_page: 1 }),
      refreshAllSourceFeeds({ limit: 400 })
    ])
    const queued = wxRes.status === 'fulfilled' ? Number((wxRes.value as any)?.queued || 0) : 0
    const sourceQueued = srcRes.status === 'fulfilled' ? Number((srcRes.value as any)?.queued || 0) : 0
    const sourceChanged = srcRes.status === 'fulfilled' ? Number((srcRes.value as any)?.changed_items || 0) : 0
    if (sourceQueued > 0) {
      notifySuccess(`刷新任务已触发（公众号队列 ${queued}，多源队列 ${sourceQueued}）`)
    } else {
      notifySuccess(`刷新任务已触发（公众号队列 ${queued}，RSS新增 ${sourceChanged}）`)
    }
  } catch (e: any) {
    notifyError(e?.message || String(e || '刷新失败'))
  } finally {
    refreshAllLoading.value = false
  }

  scheduleBatchInsightsWarmup()
  loadFeeds({ background: true })
  if (activeChannelId.value) loadArticles({ background: true })
  scheduleFastRefreshPolls()
}

const loadArticles = async (opts?: { background?: boolean }) => {
  if (!activeChannelId.value) return
  const cacheKey = buildArticleListCacheKey()
  const background = Boolean(opts?.background)
  const cachedRows = !background ? getArticleListCache(cacheKey) : null
  const hasCachedRows = Array.isArray(cachedRows)

  if (hasCachedRows) {
    articles.value = cachedRows || []
    if (activeArticleId.value && !articles.value.some((a) => articleIdentity(a) === String(activeArticleId.value))) {
      activeArticleId.value = ''
    }
    if (!activeArticleId.value && articles.value.length) {
      selectArticle(articles.value[0])
    }
  }

  const requestId = ++articlesRequestSeq
  if (background) articlesRefreshing.value = true
  else articlesLoading.value = !hasCachedRows
  try {
    let nextArticles: any[] = []
    if (hasToken.value) {
      const scopedFeedIds = activeChannelId.value === 'all' ? filteredChannels.value.map((x) => x.id) : []
      const res: any = await getChannelArticles({
        mp_id: activeChannelId.value === 'all' ? '' : activeChannelId.value,
        mp_ids: activeTopicFeedIds.value.length ? activeTopicFeedIds.value : (scopedFeedIds.length ? scopedFeedIds : undefined),
        search: articleKw.value,
        limit: 80,
        offset: 0,
        unread_only: unreadOnly.value,
        with_total: false,
      })
      nextArticles = (res.list || [])
        .map((item: any) => ({ ...item, _thumb: articleThumb(item) }))
        .sort((a: any, b: any) => Number(b?.publish_time || 0) - Number(a?.publish_time || 0))
    } else {
      if (activeChannelId.value === 'all') {
        nextArticles = []
      } else {
        const res: any = await getPublicChannelArticles(activeChannelId.value, { kw: articleKw.value, limit: 80, offset: 0 })
        nextArticles = (res.list || []).map((item: any) => ({ ...item, _thumb: articleThumb(item) }))
        activeChannelName.value = res.channel?.name || activeChannelName.value
      }
    }

    if (requestId !== articlesRequestSeq) return
    articles.value = nextArticles
    setArticleListCache(cacheKey, nextArticles)
    if (activeArticleId.value && !articles.value.some((a) => articleIdentity(a) === String(activeArticleId.value))) {
      activeArticleId.value = ''
    }
    if (!activeArticleId.value && articles.value.length) {
      selectArticle(articles.value[0])
    }
  } catch (e: any) {
    if (!background && !hasCachedRows) notifyError(e?.message || '加载文章失败')
  } finally {
    if (requestId === articlesRequestSeq) {
      articlesLoading.value = false
      articlesRefreshing.value = false
    }
  }
}

const loadArticleDetail = async (
  article: any,
  opts?: { silent?: boolean; skipQuick?: boolean }
) => {
  const articleId = articleIdentity(article)
  if (!articleId) return
  const silent = !!opts?.silent
  const skipQuick = !!opts?.skipQuick
  if (silent) {
    const lastAt = articleDetailFetchedAt.get(articleId) || 0
    if (Date.now() - lastAt < DETAIL_REFRESH_MIN_INTERVAL_MS) return
  }
  articleDetailFetchedAt.set(articleId, Date.now())
  const requestId = ++articleDetailRequestSeq

  if (!silent) articleDetailLoading.value = true
  try {
    if (!skipQuick) {
      const quick = buildFullText(String(article?.content || ''), String(article?.description || ''))
      activeArticleContentHtml.value = quick.html
      activeArticleContentText.value = quick.text
      activeArticleUrl.value = String(article?.url || article?.link || '')
      activeArticleSource.value = String(article?.mp_name || activeChannelName.value || '')
      activeArticlePublished.value = Number(article?.publish_time || 0)
    }

    const localCached = getArticleDetailCache(articleId)
    if (localCached) {
      activeArticleUrl.value = String(localCached.url || activeArticleUrl.value || '')
      activeArticleSource.value = String(localCached.source || activeArticleSource.value || '')
      activeArticlePublished.value = Number(localCached.publish_time || activeArticlePublished.value || 0)
      activeArticlePlatform.value = normalizePlatform(String(localCached.platform || '')) || activeArticlePlatform.value
      if (String(localCached.content_html || '').trim()) {
        activeArticleContentHtml.value = String(localCached.content_html || '')
      }
      if (String(localCached.content_text || '').trim()) {
        activeArticleContentText.value = String(localCached.content_text || '')
      }
    }

    let detail: any = null
    try {
      detail = await getArticleDetailPublic(articleId)
    } catch {
      detail = null
    }

    if (detail) {
      if (requestId !== articleDetailRequestSeq || articleId !== activeArticleId.value) return
      activeArticleUrl.value = String(detail?.url || activeArticleUrl.value || '')
      activeArticleSource.value = String(detail?.mp_name || activeArticleSource.value || '')
      activeArticlePublished.value = Number(detail?.publish_time || activeArticlePublished.value || 0)
      if (detail?.source_platform) {
        activeArticlePlatform.value = normalizePlatform(String(detail?.source_platform || '')) || activeArticlePlatform.value
      }
      const full = buildFullText(String(detail?.content || ''), String(detail?.description || article?.description || ''))
      activeArticleContentHtml.value = full.html
      activeArticleContentText.value = full.text
      setArticleDetailCache(articleId, {
        url: activeArticleUrl.value,
        source: activeArticleSource.value,
        publish_time: activeArticlePublished.value,
        platform: activeArticlePlatform.value,
        content_html: activeArticleContentHtml.value,
        content_text: activeArticleContentText.value,
      })
    }

    if ((!detail?.content || !detail?.description) && shouldAutoFetchContent(article)) {
      warmArticleReader(article)
    }
  } finally {
    if (!silent && requestId === articleDetailRequestSeq) {
      articleDetailLoading.value = false
    }
  }
}

const loadInsight = async (articleId: string) => {
  insightLoading.value = true
  try {
    if (hasToken.value) {
      const r: any = await getAuthedInsights(articleId, { include_llm: true })
      insight.value = r
      // Background caching is async; poll a bit so "精华速览/关键信息/全文拆解" won't stay empty.
      const missingSummary = !String(r?.summary || '').trim()
      const missingKp = !r?.key_points || !r?.key_points?.points?.length
      const missingBd = !r?.llm_breakdown?.outline?.length
      const shouldRetry = (missingSummary || missingKp || missingBd) && Number(r?.status || 0) !== 9
      if (shouldRetry && insightRetry.value < INSIGHT_RETRY_MAX && articleId === activeArticleId.value) {
        insightRetry.value += 1
        if (insightRetryTimer) clearTimeout(insightRetryTimer)
        const delay = INSIGHT_RETRY_DELAYS_MS[Math.min(insightRetry.value - 1, INSIGHT_RETRY_DELAYS_MS.length - 1)]
        insightRetryTimer = setTimeout(() => loadInsight(articleId), delay)
      }
    } else {
      const res: any = await getPublicInsights(articleId)
      insight.value = res
    }
  } catch (e: any) {
    insight.value = null
  } finally {
    insightLoading.value = false
  }
}

const generateKeyPointsNow = async () => {
  const aid = String(activeArticleId.value || '').trim()
  if (!aid || !hasToken.value) return
  if (keyPointsGenerating.value) return
  keyPointsGenerating.value = true
  try {
    await generateAuthedKeyPoints(aid, true)
    await loadInsight(aid)
    notifySuccess('关键信息已更新')
  } catch (e: any) {
    notifyError(e?.message || '关键信息生成失败')
  } finally {
    keyPointsGenerating.value = false
  }
}

const generateSummaryNow = async () => {
  const aid = String(activeArticleId.value || '').trim()
  if (!aid || !hasToken.value) return
  if (summaryGenerating.value) return
  summaryGenerating.value = true
  try {
    await generateAiSummary(aid, true)
    await loadInsight(aid)
    notifySuccess('AI摘要已更新')
  } catch (e: any) {
    notifyError(e?.message || 'AI摘要生成失败')
  } finally {
    summaryGenerating.value = false
  }
}

const scheduleBatchInsightsWarmup = () => {
  if (!hasToken.value) return
  // Refresh is async; trigger warmup in staggered windows to catch newly入库文章.
  for (const delay of [1500, 6000, 15000]) {
    setTimeout(() => {
      batchCacheInsights({ limit: INSIGHTS_BATCH_LIMIT }).catch(() => {})
    }, delay)
  }
}

const selectChannel = (id: string, silent?: boolean) => {
  activeChannelId.value = id
  articles.value = []
  resetReaderState()
  const ch = channels.value.find(c => c.id === id)
  activeChannelName.value = id === 'all' ? allFeedsLabel.value : ch?.name || ''
  if (!silent) {
    const query: any = { channel_id: id, ...(activePlatform.value !== 'all' ? { platform: activePlatform.value } : {}) }
    if (activeTopic.value?.id) query.topic_id = String(activeTopic.value.id)
    else delete query.topic_id
    router.replace({ path: '/channels', query }).catch(() => {})
  }
  // Auto refresh newest articles on page refresh / channel switch.
  if (id !== 'all') {
    maybeAutoUpdateChannel(id).catch(() => {})
  }
  triggerLoadArticles()
}

const selectArticle = (article: any) => {
  const articleId = articleIdentity(article)
  if (!articleId) {
    notifyError('文章ID无效，无法打开')
    return
  }
  readerTab.value = 'preview'
  activeArticleId.value = articleId
  activeArticleTitle.value = article?.title || articleId
  activeArticleDesc.value = (article?.description || '').trim()
  activeArticleSource.value = String(article?.mp_name || activeChannelName.value || '')
  activeArticlePublished.value = Number(article?.publish_time || 0)
  activeArticlePlatform.value = articlePlatform(article)
  insightRetry.value = 0
  if (insightRetryTimer) {
    clearTimeout(insightRetryTimer)
    insightRetryTimer = null
  }
  loadArticleDetail(article).catch(() => {})
  if (shouldLoadInsight(article)) {
    scheduleInsightWarmup(articleId)
    loadInsight(articleId).catch(() => {})
  } else {
    insight.value = null
  }
  if (hasToken.value) {
    warmArticleReader(article)
    if (shouldMarkAsRead(article)) {
      setArticleRead(articleId, true)
        .then(() => {
          article.is_read = 1
          triggerLoadFeeds({ background: true })
        })
        .catch(() => {})
    }
    // If digest missing, backfill via backend list API to populate "精华速览"
    if (!activeArticleDesc.value && shouldAutoFetchContent(article)) {
      backfillArticle(articleId, { max_pages: Math.max(1, backfillPages.value || 10) })
        .then((res: any) => {
          if (!res?.updated) return
          return loadArticles({ background: true }).then(() => {
            const updated = articles.value.find(a => articleIdentity(a) === articleId)
            if (updated) {
              activeArticleDesc.value = (updated?.description || '').trim()
            }
            loadInsight(articleId).catch(() => {})
            loadArticleDetail(updated || article).catch(() => {})
          })
        })
        .catch(() => {})
    }
  }
}

const onArticleDblClick = async (article: any) => {
  if (!article) return
  const directUrl = String(article.url || article.link || '')
  if (directUrl) {
    window.open(directUrl, '_blank', 'noopener,noreferrer')
    return
  }
  const articleId = String(article.id || '')
  if (!articleId) return
  try {
    const res: any = await getArticleDetailPublic(articleId)
    const url = String(res?.url || '')
    if (url) window.open(url, '_blank', 'noopener,noreferrer')
    else notifyInfo('未找到原文链接')
  } catch (e: any) {
    notifyError(e?.message || '打开原文失败')
  }
}

const showNewUserGuideIfNeeded = () => {
  const raw = localStorage.getItem('dasheng_new_user_guide')
  if (!raw) return
  localStorage.removeItem('dasheng_new_user_guide')
  let defaultSubscribed = 0
  try {
    const parsed = JSON.parse(raw)
    defaultSubscribed = Number(parsed?.default_subscribed || 0)
  } catch {
    defaultSubscribed = 0
  }
  const summary = defaultSubscribed > 0 ? `系统已为你自动订阅 ${defaultSubscribed} 个默认频道。` : '你还没有默认频道。'
  Modal.confirm({
    title: '欢迎使用大圣之怒订阅助手',
    content: `${summary} 建议先在订阅广场选择一批你关注的博主/来源。若要添加微信里的自定义博主，请点击顶部扫码授权后再搜索添加。`,
    okText: '去添加订阅',
    cancelText: '稍后',
    onOk: () => {
      router.push('/channels?plaza=1')
    }
  })
}

const selectTopic = (t: any, silent?: boolean) => {
  activeTopic.value = t
  activeTopicFeedIds.value = normalizeTopicMpIds(t?.mps_id)
  activePlatform.value = 'all'
  selectChannel('all', !!silent)
}

const handleTagsUpdated = () => {
  loadTopics().catch(() => {})
}

watch(
  () => route.query.channel_id,
  (val: any) => {
    if (val && typeof val === 'string' && val !== activeChannelId.value) {
      if (val === 'all' || channels.value.some(c => c.id === val)) {
        selectChannel(val, true)
      }
    }
  }
)

watch(
  () => route.query.platform,
  (val: any) => {
    const next = String(val || '').trim().toLowerCase()
    const normalized = next ? (normalizePlatform(next) || 'all') : 'all'
    if (normalized !== activePlatform.value) {
      setPlatform(normalized, true)
    }
  }
)

watch(
  () => route.query.topic_id,
  (val: any) => {
    if (!val || typeof val !== 'string') {
      if (activeTopic.value) showAllFeeds()
      return
    }
    const t = topics.value.find(x => String(x.id) === val)
    if (t) selectTopic(t, true)
  }
)

onMounted(async () => {
  handleViewportResize()
  window.addEventListener('resize', handleViewportResize, { passive: true })
  stopFeedChangedListener = onChannelFeedChanged(handleFeedChanged)
  window.addEventListener('tags-updated', handleTagsUpdated as EventListener)
  const q = (route.query.channel_id as string) || ''
  if (q) activeChannelId.value = q
  const platformQ = String((route.query.platform as string) || '').trim().toLowerCase()
  if (platformQ) {
    activePlatform.value = normalizePlatform(platformQ) || 'all'
  }
  await loadTopics()
  await loadFeeds()
  if (activeChannelId.value === 'all') {
    activeChannelName.value = allFeedsLabel.value
    triggerLoadArticles({ background: true })
  }

  const tid = (route.query.topic_id as string) || ''
  if (tid) {
    const t = topics.value.find(x => String(x.id) === tid)
    if (t) selectTopic(t, true)
  }

  if (pollTimer) clearInterval(pollTimer)
  pollTimer = setInterval(() => {
    if (document.hidden) return
    if (channelsLoading.value || channelsRefreshing.value || articlesLoading.value || articlesRefreshing.value) return
    if (!activeChannelId.value) return
    loadFeeds({ background: true })
    loadArticles({ background: true })
  }, AUTO_POLL_MS)

  showNewUserGuideIfNeeded()
})

onUnmounted(() => {
  window.removeEventListener('resize', handleViewportResize)
  if (stopFeedChangedListener) {
    stopFeedChangedListener()
    stopFeedChangedListener = null
  }
  window.removeEventListener('tags-updated', handleTagsUpdated as EventListener)
  if (optimisticFeedSyncTimer) {
    clearTimeout(optimisticFeedSyncTimer)
    optimisticFeedSyncTimer = null
  }
  if (pollTimer) {
    clearInterval(pollTimer)
    pollTimer = null
  }
  if (insightRetryTimer) {
    clearTimeout(insightRetryTimer)
    insightRetryTimer = null
  }
})
</script>

<style scoped>
.channels-page {
  height: calc(100vh - var(--app-header-height));
  overflow: hidden;
  background: var(--app-page-bg);
}
.channels-layout {
  height: 100%;
  overflow-x: auto;
  overflow-y: hidden;
  flex-wrap: nowrap;
}
.sider {
  width: var(--sider-width, 236px);
  min-width: var(--sider-width, 236px);
  max-width: var(--sider-width, 236px);
  flex: 0 0 var(--sider-width, 236px);
  position: relative;
  z-index: 3;
  border-right: 1px solid var(--app-border-soft);
  background: var(--app-surface-1);
  overflow: hidden;
  display: flex;
  flex-direction: column;
  min-height: 0;
  box-shadow: inset -1px 0 0 rgba(255, 255, 255, 0.25);
}
.content {
  min-width: 460px;
  flex: 1 1 auto;
  position: relative;
  z-index: 1;
}
.reader {
  width: 700px;
  min-width: 700px;
  max-width: 700px;
  flex: 0 0 700px;
  position: relative;
  z-index: 2;
}
.sider-top {
  padding: 9px 8px 7px;
  display: grid;
  grid-template-rows: 34px 36px;
  gap: 6px;
}
.sider :deep(.arco-spin) {
  display: block;
  width: 100%;
  max-width: 100%;
  min-width: 0;
}
.sider :deep(.arco-spin-content) {
  display: block;
  width: 100%;
  max-width: 100%;
  min-width: 0;
}
.sider > * {
  width: 100%;
  max-width: 100%;
  min-width: 0;
}
.sider :deep(.arco-list),
.sider :deep(.arco-list-wrapper),
.sider :deep(.arco-list-content-wrapper),
.sider :deep(.arco-list-content),
.sider :deep(.arco-list-item-main) {
  width: 100% !important;
  max-width: 100% !important;
  min-width: 0 !important;
  overflow-x: hidden !important;
  box-sizing: border-box !important;
}
.topic-tabs {
  display: flex;
  overflow-x: auto;
  padding: 0 0 2px;
  gap: 6px;
  align-items: center;
}
.topic-chip {
  flex: 0 0 auto;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 0 9px;
  height: 28px;
  border: 1px solid transparent;
  border-radius: 999px;
  background: transparent;
  color: var(--color-text-2);
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  white-space: nowrap;
}
.topic-chip:hover {
  color: var(--color-text-1);
  background: color-mix(in srgb, var(--color-fill-2) 90%, transparent);
}
.topic-chip.active {
  color: var(--brand-blue-7);
  border-color: color-mix(in srgb, var(--brand-blue-5) 42%, transparent);
  background: color-mix(in srgb, var(--brand-blue-1) 84%, transparent);
}
.sider-search {
  padding-top: 0;
  min-width: 0;
}
.sider-search :deep(.arco-input-wrapper),
.search-input {
  height: 32px;
}
.sider-search :deep(.arco-input),
.search-input :deep(.arco-input) {
  height: 100%;
  font-size: 14px;
}
.sider-list {
  flex: 1;
  width: 100%;
  max-width: 100%;
  overflow-y: auto;
  overflow-x: hidden;
  padding: 8px;
  min-height: 0;
  box-sizing: border-box;
}
.channel-list {
  padding-bottom: 8px;
  width: 100%;
  max-width: 100%;
}
.channel-list :deep(.arco-list-item) {
  padding: 0 !important;
  min-height: 0 !important;
  border: none !important;
  width: 100% !important;
  max-width: 100% !important;
}
.channel-list :deep(.arco-list-item-content) {
  padding: 0 !important;
  width: 100% !important;
  max-width: 100% !important;
  min-width: 0 !important;
  display: block !important;
  overflow: hidden;
}
.channel-item {
  width: 100%;
  max-width: 100%;
  min-width: 0;
  padding: 0;
  border-radius: 14px;
  cursor: pointer;
  margin: 0 0 6px;
}
.channel-item-row {
  width: 100%;
  max-width: 100%;
  min-width: 0;
  box-sizing: border-box;
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 6px 8px;
  border-radius: 13px;
  min-height: 42px;
  flex-wrap: nowrap;
  background: var(--app-surface-2);
  border: 1px solid var(--app-border-soft);
  box-shadow: var(--app-shadow-card);
  position: relative;
}
.channel-item-row.editing {
  gap: 8px;
  padding-right: 64px;
}
.feed-delete-btn {
  position: absolute;
  right: 8px;
  top: 50%;
  transform: translateY(-50%);
  z-index: 3;
  pointer-events: auto;
  min-width: 50px;
  height: 24px;
  padding: 0 6px !important;
  border-radius: 999px;
  font-weight: 700;
  color: #fff !important;
  border-color: rgba(var(--danger-6), 0.88) !important;
  background: rgba(var(--danger-6), 0.9) !important;
  box-shadow: 0 2px 8px rgba(var(--danger-6), 0.28);
}
.channel-item.active {
  background: transparent;
}
.channel-item.active .channel-item-row {
  background: color-mix(in srgb, var(--brand-blue-1) 74%, transparent);
  border-color: color-mix(in srgb, var(--brand-blue-5) 45%, transparent);
  box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--brand-blue-4) 35%, transparent);
}
.channel-item:hover {
  background: transparent;
}
.channel-item:hover .channel-item-row {
  background: color-mix(in srgb, var(--color-fill-2) 88%, transparent);
}
.channel-item.active:hover {
  background: transparent;
}
.channel-item.active:hover .channel-item-row {
  background: color-mix(in srgb, var(--brand-blue-1) 74%, transparent);
}
.channel-item :deep(.arco-badge-number) {
  transform: translateY(2px);
}
.channel-name {
  font-weight: 600;
  line-height: 20px;
  font-size: 14px;
  letter-spacing: -0.2px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  flex: 1;
}
.channel-main {
  min-width: 0;
  flex: 1;
}
.channel-platform {
  color: var(--color-text-3);
  font-size: 11px;
  line-height: 1.2;
  margin-top: -1px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.channel-platform-compact {
  font-size: 10px;
}
.channel-item :deep(.arco-badge-number) {
  font-size: 12px;
  line-height: 18px;
  height: 18px;
  min-width: 18px;
  padding: 0 6px;
}
.channel-intro {
  display: none;
}
.content {
  padding: 12px 12px 10px;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  min-height: 0;
  background: var(--app-page-bg);
}
.content-head {
  display: grid;
  grid-template-rows: 34px 34px;
  gap: 6px;
  margin-bottom: 9px;
}
.content-search-row {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}
.content-head-top {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}
.platform-tabs {
  display: flex;
  gap: 6px;
  padding-bottom: 2px;
  overflow-x: auto;
  flex: 1 1 auto;
  min-width: 0;
}
.platform-tab {
  border: 1px solid transparent;
  border-radius: 999px;
  background: transparent;
  padding: 0 9px;
  height: 28px;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  white-space: nowrap;
  flex: 0 0 auto;
  color: var(--color-text-2);
  cursor: pointer;
}
.platform-tab-name {
  font-size: 14px;
  font-weight: 600;
}
.platform-tab-name-compact {
  font-size: 12px;
}
.platform-tab-count {
  color: var(--color-text-3);
  font-size: 12px;
  font-weight: 600;
}
.platform-tab-count-compact {
  font-size: 11px;
}
.platform-tab.active {
  color: var(--brand-blue-7);
  border-color: color-mix(in srgb, var(--brand-blue-5) 42%, transparent);
  background: color-mix(in srgb, var(--brand-blue-1) 84%, transparent);
}
.platform-tab.active .platform-tab-count {
  color: var(--brand-blue-7);
}
.search-btn {
  min-width: 64px;
  height: 32px !important;
  border-radius: 10px;
}
.refresh-all-btn.arco-btn-primary {
  background: var(--brand-blue-6) !important;
  border-color: var(--brand-blue-6) !important;
  box-shadow: 0 6px 14px color-mix(in srgb, var(--brand-blue-6) 28%, transparent) !important;
}
.refresh-all-btn.arco-btn-primary:hover,
.refresh-all-btn.arco-btn-primary:not(.arco-btn-disabled):hover {
  background: var(--brand-blue-7) !important;
  border-color: var(--brand-blue-7) !important;
}
.search-input {
  width: 320px;
  max-width: min(38vw, 420px);
  min-width: 220px;
  flex: 0 1 320px;
}
.content-search-row .refresh-all-btn {
  height: 32px !important;
  border-radius: 10px;
}
.status-inline-tag {
  height: 26px;
  line-height: 24px;
  border-radius: 8px;
  font-weight: 600;
  margin-left: 2px;
  flex: 0 0 auto;
}
.muted {
  color: var(--color-text-3);
  font-size: 12px;
}
.empty {
  padding: 32px;
  color: var(--color-text-3);
}
.articles {
  flex: 1;
  overflow: auto;
  padding-right: 8px;
  min-height: 0;
}
.articles-spin {
  flex: 1;
  min-height: 0;
  display: flex;
}
.articles-spin :deep(.arco-spin) {
  flex: 1;
  min-height: 0;
  display: flex;
}
.articles-spin :deep(.arco-spin-content) {
  flex: 1;
  min-height: 0;
  display: flex;
}
.articles-area {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
}
.date-sep {
  margin: 8px 0 6px;
  font-weight: 700;
  color: var(--color-text-2);
  font-size: 12px;
}
.article-cards {
  display: grid;
  grid-template-columns: 1fr;
  gap: 6px;
}
.article-card {
  border-radius: 12px;
  border: 1px solid var(--app-border-soft);
  background: var(--app-surface-2);
  box-shadow: var(--app-shadow-card);
}
.article-card :deep(.arco-card-body) {
  padding: 8px !important;
}
.article-card.active {
  border-color: color-mix(in srgb, var(--brand-blue-5) 62%, transparent);
  box-shadow: 0 0 0 2px color-mix(in srgb, var(--brand-blue-5) 20%, transparent), var(--app-shadow-card);
}
.article-card.read {
  opacity: 1;
  background: color-mix(in srgb, var(--brand-blue-1) 86%, transparent);
  border-color: color-mix(in srgb, var(--brand-blue-4) 38%, transparent);
}
.article-row {
  display: grid;
  grid-template-columns: 68px 1fr;
  gap: 8px;
  align-items: center;
}
.thumb {
  width: 68px;
  height: 48px;
  border-radius: 8px;
  overflow: hidden;
  background: var(--color-fill-2);
}
.thumb img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}
.thumb-placeholder {
  width: 100%;
  height: 100%;
}
.body {
  min-width: 0;
}
.article-title-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 6px;
  margin-bottom: 1px;
}
.article-title {
  font-weight: 700;
  font-size: 14px;
  line-height: 1.3;
  margin-bottom: 0;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  flex: 1;
}
.article-head-meta {
  display: inline-flex;
  align-items: center;
  min-width: 0;
  flex: 0 0 auto;
}
.article-source {
  flex: 0 0 auto;
  max-width: 108px;
  color: var(--color-text-3);
  font-size: 11px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.article-publish-time {
  color: var(--color-text-3);
  font-size: 11px;
  white-space: nowrap;
}
.article-subtitle {
  color: var(--color-text-3);
  font-size: 12px;
  line-height: 1.35;
  margin-bottom: 0;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.dot {
  margin: 0 6px;
}
.reader {
  border-left: 1px solid var(--app-border-soft);
  background: var(--app-surface-1);
  overflow: hidden;
}
.reader-inner {
  padding: 12px 13px;
  height: calc(100vh - var(--app-header-height));
  overflow: auto;
}
.reader-title {
  font-weight: 800;
  font-size: 16px;
  margin-bottom: 8px;
}
.reader-meta-row {
  display: flex;
  align-items: center;
  gap: 4px;
  color: var(--color-text-3);
  font-size: 12px;
  margin-bottom: 10px;
}
.open-origin-btn {
  color: var(--brand-blue-6) !important;
}
.reader-section-title {
  font-size: 13px;
  font-weight: 700;
  color: var(--color-text-1);
  margin-bottom: 8px;
}
.reader-section-title.inline {
  margin-top: 12px;
}
.reader-tabs {
  display: flex;
  gap: 6px;
  margin-bottom: 10px;
  overflow-x: auto;
}
.reader-tabs.single-line {
  flex-wrap: nowrap;
  white-space: nowrap;
}
.reader-tab {
  border: 1px solid transparent;
  border-radius: 999px;
  background: transparent;
  height: 28px;
  padding: 0 10px;
  font-size: 12px;
  font-weight: 700;
  color: var(--color-text-3);
  cursor: pointer;
  white-space: nowrap;
}
.reader-tab.active {
  color: var(--brand-blue-7);
  border-color: color-mix(in srgb, var(--brand-blue-5) 42%, transparent);
  background: color-mix(in srgb, var(--brand-blue-1) 84%, transparent);
}
.section-body {
  color: var(--color-text-2);
  font-size: 14px;
  line-height: 1.7;
}
.highlight {
  font-weight: 700;
  margin-bottom: 8px;
  padding: 10px;
  border-radius: 10px;
  background: var(--color-fill-2);
}
.text {
  color: var(--color-text-2);
}
.kp-list {
  margin-top: 10px;
}
.kp-item {
  align-items: flex-start;
}
.kp-bullet {
  display: inline-flex;
  min-width: 20px;
  height: 20px;
  border-radius: 999px;
  align-items: center;
  justify-content: center;
  background: var(--color-fill-2);
  color: var(--color-text-3);
  margin-right: 8px;
  font-size: 12px;
}
.kp-text {
  flex: 1;
}
.error {
  margin-top: 8px;
  color: rgb(var(--danger-6));
  font-size: 12px;
  white-space: pre-wrap;
}
.kp-idx {
  display: inline-block;
  min-width: 18px;
  color: var(--color-text-3);
}
.json {
  white-space: pre-wrap;
  word-break: break-word;
  background: var(--color-fill-2);
  padding: 10px;
  border-radius: 10px;
}
.reader-actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  margin-top: 10px;
}
.reader-actions.preview-actions {
  margin-top: 6px;
}
.summary-box {
  border-radius: 10px;
  border: 1px solid var(--app-border-soft);
  background: color-mix(in srgb, var(--app-surface-2) 93%, transparent);
  padding: 10px 12px;
  color: var(--color-text-2);
  font-size: 14px;
  line-height: 1.85;
  white-space: pre-wrap;
}
.full-title {
  font-weight: 800;
  font-size: 18px;
  margin-bottom: 8px;
}
.full-meta {
  margin-bottom: 12px;
}
.full-content :deep(img) {
  max-width: 100%;
  border-radius: 8px;
  margin: 10px 0;
}
.full-content {
  color: var(--color-text-2);
  font-size: 14px;
  line-height: 1.85;
}
.full-content :deep(h1),
.full-content :deep(h2),
.full-content :deep(h3),
.full-content :deep(h4) {
  margin: 14px 0 8px;
  line-height: 1.35;
  font-weight: 800;
  color: var(--color-text-1);
  border-radius: 10px;
  padding: 8px 10px;
}
.full-content :deep(h1) {
  font-size: 18px;
  border-left: 4px solid rgba(var(--danger-6), 0.62);
  background: rgba(var(--danger-6), 0.08);
}
.full-content :deep(h2) {
  font-size: 16px;
  border-left: 4px solid rgba(var(--success-6), 0.62);
  background: rgba(var(--success-6), 0.09);
}
.full-content :deep(h3) {
  font-size: 15px;
  border-left: 4px solid rgba(var(--primary-6), 0.62);
  background: rgba(var(--primary-6), 0.1);
}
.full-content :deep(h4) {
  font-size: 14px;
  border-left: 4px solid rgba(var(--warning-6), 0.62);
  background: rgba(var(--warning-6), 0.09);
}
.full-content :deep(a) {
  color: var(--brand-blue-6);
  word-break: break-word;
}
.full-content :deep(ul),
.full-content :deep(ol) {
  margin: 8px 0 10px;
  padding-left: 20px;
}
.full-content :deep(p),
.full-content :deep(li),
.full-content :deep(blockquote) {
  font-size: 14px;
  line-height: 1.85;
  color: var(--color-text-2);
}
.full-content :deep(p + p) {
  margin-top: 8px;
}
.full-content :deep(blockquote) {
  margin: 10px 0;
  padding: 10px 12px;
  border-left: 4px solid rgba(var(--primary-6), 0.65);
  background: rgba(var(--primary-6), 0.08);
  border-radius: 0 10px 10px 0;
}
.full-content :deep(strong),
.full-content :deep(b) {
  color: var(--color-text-1);
  font-weight: 800;
}
.full-content :deep(em),
.full-content :deep(i) {
  color: var(--color-text-1);
  font-style: italic;
}
.full-content :deep(u) {
  text-decoration-color: rgba(var(--warning-6), 0.95);
  text-decoration-thickness: 2px;
  text-underline-offset: 2px;
}
.full-content :deep(table) {
  width: 100%;
  border-collapse: collapse;
  margin: 10px 0;
  font-size: 13px;
}
.full-content :deep(th),
.full-content :deep(td) {
  border: 1px solid var(--color-neutral-3);
  padding: 6px 8px;
  text-align: left;
  vertical-align: top;
}
.full-content :deep(pre) {
  white-space: pre-wrap;
  word-break: break-word;
  background: color-mix(in srgb, var(--color-fill-2) 78%, transparent);
  border-radius: 8px;
  padding: 10px 12px;
  line-height: 1.6;
}
.full-content :deep(code) {
  white-space: pre-wrap;
  word-break: break-word;
  background: color-mix(in srgb, var(--color-fill-2) 78%, transparent);
  border-radius: 6px;
  padding: 1px 5px;
}

body[arco-theme='dark'] .topic-chip.active,
body[arco-theme='dark'] .platform-tab.active,
body[arco-theme='dark'] .reader-tab.active {
  color: var(--brand-blue-2);
  border-color: color-mix(in srgb, var(--brand-blue-5) 40%, transparent);
  background: color-mix(in srgb, var(--brand-blue-9) 56%, transparent);
}

body[arco-theme='dark'] .article-card.read,
body[arco-theme='dark'] .channel-item.active .channel-item-row {
  background: color-mix(in srgb, var(--brand-blue-9) 48%, transparent);
  border-color: color-mix(in srgb, var(--brand-blue-6) 38%, transparent);
}
</style>
