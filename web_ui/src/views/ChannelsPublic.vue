<template>
  <div class="channels-page">
    <a-layout class="channels-layout">
      <a-layout-sider class="sider" :width="300">
        <div class="sider-top">
          <div class="sider-title">
            <span>订阅</span>
            <a-button size="mini" type="outline" :loading="markAllLoading" @click="markAllReadForCurrent">
              全部已读
            </a-button>
          </div>
          <div class="sider-tabs">
            <a-button
              class="tab-btn"
              :type="leftTab === 'feeds' ? 'primary' : 'outline'"
              size="small"
              @click="showAllFeeds"
            >
              全部订阅
              <a-badge v-if="feedsStats.unread_total" :count="feedsStats.unread_total" :max-count="99" />
            </a-button>
            <a-button
              class="tab-btn"
              :type="leftTab === 'topics' ? 'primary' : 'outline'"
              size="small"
              @click="leftTab = 'topics'"
            >
              我的专题
              <a-badge :count="topics.length" :max-count="99" />
            </a-button>
          </div>

          <div class="sider-search">
            <a-input v-model="channelKw" allow-clear placeholder="搜索订阅" @press-enter="loadFeeds" />
          </div>
        </div>

        <a-spin :loading="channelsLoading">
          <div v-if="leftTab === 'feeds'" class="sider-list">
            <div class="sider-section">
              <div class="section-title">已订阅频道</div>
              <a-select v-model="feedSort" size="small" style="width: 120px" @change="loadFeeds">
                <a-option value="recent">最近更新</a-option>
                <a-option value="created">创建时间</a-option>
                <a-option value="name">名称</a-option>
              </a-select>
            </div>
              <a-list :bordered="false" class="channel-list">
              <a-list-item class="channel-item" :class="{ active: activeChannelId === 'all' }" @click="selectChannel('all')">
                <div class="channel-item-row" title="查看所有文章">
                  <a-avatar :size="20" :image-url="AvatarAll">
                    <img :src="AvatarAll" />
                  </a-avatar>
                  <div class="channel-name">全部订阅</div>
                  <a-badge class="channel-badge" :count="feedsStats.unread_total" :max-count="99" />
                </div>
              </a-list-item>

              <a-list-item
                v-for="c in channels"
                :key="c.id"
                class="channel-item"
                :class="{ active: c.id === activeChannelId }"
                @click="selectChannel(c.id)"
              >
                <div class="channel-item-row" :title="c.intro || c.name">
                  <a-avatar :size="20" :image-url="proxiedWeChatImg(c.cover) || '/static/default-avatar.png'">
                    <img :src="proxiedWeChatImg(c.cover) || '/static/default-avatar.png'" />
                  </a-avatar>
                  <div class="channel-name">{{ c.name }}</div>
                  <a-badge class="channel-badge" :count="c.unread_count" :max-count="99" />
                </div>
              </a-list-item>
            </a-list>
          </div>

          <div v-else class="sider-list">
            <div class="sider-section">
              <div class="section-title">我的专题</div>
              <a-button size="small" type="outline" @click="goTopics">管理专题</a-button>
            </div>
            <a-list :bordered="false" class="channel-list">
              <a-list-item v-for="t in topics" :key="t.id" class="channel-item" @click.stop="selectTopic(t)">
                <div class="channel-item-row" :title="t.intro || t.name">
                  <a-avatar :size="20">
                    <img :src="t.cover ? (baseUrl + t.cover) : '/static/logo.svg'" />
                  </a-avatar>
                  <div class="channel-name">{{ t.name }}</div>
                </div>
              </a-list-item>
            </a-list>
          </div>
        </a-spin>
      </a-layout-sider>

      <a-layout-content class="content">
        <div class="toolbar">
          <div class="toolbar-left">
            <a-input v-model="articleKw" class="search-input" allow-clear placeholder="搜索关键词" @press-enter="loadArticles" />
            <a-button size="small" @click="loadArticles" :loading="articlesLoading">搜索</a-button>
            <a-select v-model="articleSort" size="small" style="width: 120px">
              <a-option value="time">按时间</a-option>
            </a-select>
            <a-switch v-model="unreadOnly" size="small" @change="loadArticles" />
            <span class="muted">仅看未读</span>
          </div>
          <div class="toolbar-right">
            <a-tag v-if="activeChannelName" color="blue">{{ activeChannelName }}</a-tag>
            <a-button v-if="activeChannelId && activeChannelId !== 'all'" size="small" type="outline" @click="copyShareLink">
              复制分享链接
            </a-button>
            <a-button type="outline" @click="goPlaza">频道广场</a-button>
            <a-button type="outline" @click="goCreateChannel">创建频道</a-button>
            <a-button type="outline" @click="goExport">导入OPML</a-button>
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
                    :key="a.id"
                    class="article-card"
                    :class="{ active: a.id === activeArticleId, read: (a as any).is_read }"
                    :hoverable="true"
                    @click="selectArticle(a)"
                    @dblclick.stop="onArticleDblClick(a)"
                  >
                    <div class="article-row">
                      <div class="thumb">
                        <img
                          v-if="a.pic_url"
                          :src="proxiedWeChatImg(a.pic_url)"
                          loading="lazy"
                          referrerpolicy="no-referrer"
                          @error="(e:any) => { try { (e.target as HTMLImageElement).src = '/static/default-avatar.png' } catch {} }"
                        />
                        <div v-else class="thumb-placeholder" />
                      </div>
                      <div class="body">
                        <div class="article-title">{{ a.title }}</div>
                        <div class="article-subtitle">{{ excerpt(a.description) }}</div>
                        <div class="article-meta">
                          <span>{{ a.mp_name || activeChannelName }}</span>
                          <span class="dot">·</span>
                          <span>{{ formatRelative(a.publish_time) }}</span>
                          <span class="dot">·</span>
                          <span>{{ a.word_count }} 字</span>
                        </div>
                      </div>
                    </div>
                  </a-card>
                </div>
              </template>
            </div>
          </div>
        </a-spin>
      </a-layout-content>

      <a-layout-sider class="reader" :width="420">
        <div class="reader-inner">
          <div v-if="!activeArticleId" class="empty">选择一篇文章查看速览</div>
          <a-spin v-else :loading="insightLoading">
            <div class="reader-title">{{ activeArticleTitle }}</div>

            <a-tabs type="rounded" size="small">
              <a-tab-pane key="brief" title="精华速览">
                <div class="section-body">
                  <div v-if="insight?.key_points?.highlight" class="highlight">{{ insight.key_points.highlight }}</div>
                  <div class="text">{{ insight?.summary || activeArticleDesc || '暂无摘要（后台会自动抓取/生成，请稍后）' }}</div>
                  <a-list v-if="insight?.key_points?.points?.length" :bordered="false" class="kp-list">
                    <a-list-item v-for="(p, idx) in insight.key_points.points" :key="idx" class="kp-item">
                      <span class="kp-bullet">{{ idx + 1 }}</span>
                      <span class="kp-text">{{ p }}</span>
                    </a-list-item>
                  </a-list>
                  <div v-if="insight?.error" class="error">{{ insight.error }}</div>
                </div>
              </a-tab-pane>
              <a-tab-pane key="keys" title="关键信息">
                <div class="section-body">
                  <a-list v-if="insight?.key_points?.points?.length" :bordered="false">
                    <a-list-item v-for="(p, idx) in insight.key_points.points" :key="idx">
                      <span class="kp-idx">{{ idx + 1 }}</span>
                      <span>{{ p }}</span>
                    </a-list-item>
                  </a-list>
                  <a-list v-else-if="insight?.headings?.length" :bordered="false">
                    <a-list-item v-for="(h, idx) in insight.headings" :key="idx">
                      <span :style="{ paddingLeft: h.level === 2 ? '12px' : '0px' }">
                        {{ h.level === 2 ? '· ' : '' }}{{ h.text }}
                      </span>
                    </a-list-item>
                  </a-list>
                  <div v-else class="text">暂无关键信息</div>
                </div>
              </a-tab-pane>
              <a-tab-pane key="breakdown" title="全文拆解">
                <div class="section-body">
                  <div v-if="insight?.llm_breakdown?.outline?.length" class="outline">
                    <div v-for="(node, idx) in insight.llm_breakdown.outline" :key="idx" class="outline-node">
                      <div class="outline-heading">• {{ node.heading }}</div>
                      <ul v-if="node.bullets?.length" class="outline-bullets">
                        <li v-for="(b, j) in node.bullets" :key="j">{{ b }}</li>
                      </ul>
                      <div v-if="node.children?.length" class="outline-children">
                        <div v-for="(c, k) in node.children" :key="k" class="outline-node child">
                          <div class="outline-heading">· {{ c.heading }}</div>
                          <ul v-if="c.bullets?.length" class="outline-bullets">
                            <li v-for="(b2, j2) in c.bullets" :key="j2">{{ b2 }}</li>
                          </ul>
                        </div>
                      </div>
                    </div>
                  </div>
                  <div v-else class="text">暂无拆解结果（需要配置 LLM；后台会自动抓取正文并生成，请稍后）</div>
                  <div v-if="insight?.error" class="error">{{ insight.error }}</div>
                </div>
              </a-tab-pane>
            </a-tabs>
          </a-spin>
        </div>
      </a-layout-sider>
    </a-layout>

    <a-drawer v-model:visible="contentDrawerVisible" width="880px" :footer="false" title="全文阅读">
      <a-spin :loading="contentLoading">
        <div class="full-title">{{ activeArticleTitle }}</div>
        <div v-if="activeArticleUrl" class="full-meta">
          <a-link :href="activeArticleUrl" target="_blank">原文链接</a-link>
        </div>
        <div class="full-content" v-html="activeArticleContent"></div>
      </a-spin>
    </a-drawer>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Message } from '@arco-design/web-vue'
import { ProxyImage } from '@/utils/constants'
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
  markAllRead,
  markAllReadMulti,
  setArticleRead,
  ChannelFeedItem
} from '@/api/channels'
import { UpdateMps } from '@/api/subscription'
import { listTags } from '@/api/tagManagement'

const route = useRoute()
const router = useRouter()

const channelsLoading = ref(false)
const channels = ref<ChannelFeedItem[]>([])
const channelKw = ref('')
const activeChannelId = ref<string>('')
const activeChannelName = ref<string>('')

const articlesLoading = ref(false)
const articles = ref<any[]>([])
const articleKw = ref('')
const activeArticleId = ref<string>('')
const activeArticleTitle = ref<string>('')
const activeArticleDesc = ref<string>('')

const insightLoading = ref(false)
const insight = ref<PublicInsights | null>(null)
const insightRetry = ref(0)
const INSIGHT_RETRY_MAX = 10
let insightRetryTimer: any = null
const autoFetchedContent = new Set<string>()

const contentDrawerVisible = ref(false)
const contentLoading = ref(false)
const activeArticleContent = ref<string>('')
const activeArticleUrl = ref<string>('')

const markAllLoading = ref(false)
const autoUpdateLoading = ref(false)
const autoUpdatedAt = new Map<string, number>()
const AUTO_UPDATE_MIN_INTERVAL_MS = 2 * 60 * 1000

const hasToken = computed(() => !!localStorage.getItem('token'))
const baseUrl = computed(() => (import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, ''))

const excerpt = (text: string) => {
  const t = (text || '').trim()
  if (!t) return ' '
  return t.length > 60 ? `${t.slice(0, 60)}…` : t
}

const AvatarAll = '/static/logo.svg'

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

const leftTab = ref<'feeds' | 'topics'>('feeds')
	const feedSort = ref('recent')
	const articleSort = ref('time')
	const unreadOnly = ref(false)
	const backfillPages = ref<number>(10)
	const topics = ref<any[]>([])
	const feedsStats = ref({ unread_total: 0, article_total: 0, feed_total: 0 })
const activeTopic = ref<any | null>(null)
const activeTopicFeedIds = ref<string[]>([])
const lastFeedChannelId = ref<string>('all')

const showAllFeeds = async () => {
  activeTopic.value = null
  activeTopicFeedIds.value = []
  leftTab.value = 'feeds'
  if (lastFeedChannelId.value) {
    activeChannelId.value = lastFeedChannelId.value
  }
  await loadFeeds()
  // If we restored a valid channel, refresh list immediately.
  if (activeChannelId.value) {
    await selectChannel(activeChannelId.value, true)
  }
}

	const loadTopics = async () => {
	  try {
	    const res: any = await listTags({ offset: 0, limit: 200 })
	    topics.value = res?.list || res || []
	  } catch {
	    topics.value = []
	  }
	}

const loadFeeds = async () => {
  channelsLoading.value = true
  try {
	    if (hasToken.value) {
	      const res: any = await getChannelFeeds({ kw: channelKw.value, limit: 200, offset: 0, sort: feedSort.value })
	      channels.value = res.list || []
	      feedsStats.value = res.stats || feedsStats.value
	    } else {
	      const res: any = await getPublicChannels({ kw: channelKw.value, limit: 200, offset: 0 })
	      channels.value = (res.list || []).map((c: any) => ({ ...c, unread_count: 0, article_count: 0, latest_publish_time: 0 }))
	      feedsStats.value = { unread_total: 0, article_total: 0, feed_total: channels.value.length }
	    }

    if (!activeChannelId.value) {
      const q = (route.query.channel_id as string) || ''
      if (q && (q === 'all' || channels.value.some(c => c.id === q))) {
        selectChannel(q, true)
      } else if (channels.value.length) {
        selectChannel(channels.value[0].id, true)
      }
    }
  } catch (e: any) {
    Message.error(e?.message || '加载频道失败')
  } finally {
    channelsLoading.value = false
  }
}

const maybeAutoUpdateChannel = async (mpId: string) => {
  if (!hasToken.value) return
  const id = String(mpId || '').trim()
  if (!id || id === 'all') return

  const last = autoUpdatedAt.get(id) || 0
  if (Date.now() - last < AUTO_UPDATE_MIN_INTERVAL_MS) return
  autoUpdatedAt.set(id, Date.now())

  autoUpdateLoading.value = true
  try {
    // Best-effort: trigger backend sync (non-blocking; backend does its own throttling).
    await UpdateMps(id, { start_page: 0, end_page: 1 })
  } catch {
    // ignore
  } finally {
    autoUpdateLoading.value = false
  }

  // The backend updates in a background thread; poll list a few times to reflect fresh rows.
  for (const delay of [2000, 6000, 12000]) {
    setTimeout(() => {
      if (activeChannelId.value === id) {
        loadFeeds()
        loadArticles()
      }
    }, delay)
  }
}

const loadArticles = async () => {
  if (!activeChannelId.value) return
  articlesLoading.value = true
  try {
    if (hasToken.value) {
      const res: any = await getChannelArticles({
        mp_id: activeTopicFeedIds.value.length ? '' : activeChannelId.value === 'all' ? '' : activeChannelId.value,
        mp_ids: activeTopicFeedIds.value.length ? activeTopicFeedIds.value : undefined,
        search: articleKw.value,
        limit: 80,
        offset: 0,
        unread_only: unreadOnly.value
      })
      articles.value = res.list || []
    } else {
      if (activeChannelId.value === 'all') {
        articles.value = []
      } else {
        const res: any = await getPublicChannelArticles(activeChannelId.value, { kw: articleKw.value, limit: 80, offset: 0 })
        articles.value = res.list || []
        activeChannelName.value = res.channel?.name || activeChannelName.value
      }
    }

    if (!activeArticleId.value && articles.value.length) {
      selectArticle(articles.value[0])
    }
  } catch (e: any) {
    Message.error(e?.message || '加载文章失败')
  } finally {
    articlesLoading.value = false
  }
}

const loadInsight = async (articleId: string) => {
  insightLoading.value = true
  try {
    if (hasToken.value) {
      const r: any = await getAuthedInsights(articleId, { include_llm: true })
      insight.value = r
      // Background caching is async; poll a bit so "精华速览/关键信息/全文拆解" won't stay empty.
      const missingKp = !r?.key_points || !r?.key_points?.points?.length
      const missingBd = !r?.llm_breakdown?.outline?.length
      const shouldRetry = (missingKp || missingBd) && Number(r?.status || 0) !== 9
      if (shouldRetry && insightRetry.value < INSIGHT_RETRY_MAX && articleId === activeArticleId.value) {
        insightRetry.value += 1
        if (insightRetryTimer) clearTimeout(insightRetryTimer)
        insightRetryTimer = setTimeout(() => loadInsight(articleId), 1600)
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

const selectChannel = async (id: string, silent?: boolean) => {
  if (id === 'all') {
    activeTopic.value = null
    activeTopicFeedIds.value = []
  }
  if (!id.startsWith('topic:')) {
    lastFeedChannelId.value = id
  }
  activeChannelId.value = id
  activeArticleId.value = ''
  activeArticleTitle.value = ''
  insight.value = null
  const ch = channels.value.find(c => c.id === id)
  if (id.startsWith('topic:')) {
    activeChannelName.value = activeTopic.value?.name || '专题'
  } else {
    activeChannelName.value = id === 'all' ? '全部订阅' : ch?.name || ''
  }
  if (!silent) {
    router.replace({ path: '/channels', query: id.startsWith('topic:') ? { topic_id: id.replace(/^topic:/, '') } : { channel_id: id } })
  }
  // Auto refresh newest articles on page refresh / channel switch.
  if (!id.startsWith('topic:')) maybeAutoUpdateChannel(id)
  await loadArticles()
}

const selectArticle = async (article: any) => {
  const articleId = String(article.id)
  activeArticleId.value = articleId
  activeArticleTitle.value = article?.title || articleId
  activeArticleDesc.value = (article?.description || '').trim()
  insightRetry.value = 0
  if (insightRetryTimer) {
    clearTimeout(insightRetryTimer)
    insightRetryTimer = null
  }
  await loadInsight(articleId)
  if (hasToken.value) {
    // Auto fetch content for better reading & LLM breakdown (best-effort, once per session per article).
    if (!autoFetchedContent.has(articleId)) {
      autoFetchedContent.add(articleId)
      fetchArticleContent(articleId, { force: false })
        .then(() => loadInsight(articleId))
        .catch(() => {})
    }
    try {
      await setArticleRead(articleId, true)
      article.is_read = 1
      loadFeeds()
    } catch {
      // ignore
    }
    // If digest missing, backfill via backend list API to populate "精华速览"
    if (!activeArticleDesc.value) {
      try {
        const res: any = await backfillArticle(articleId, { max_pages: Math.max(1, backfillPages.value || 10) })
        if (res?.updated) {
          await loadArticles()
          // reload current article from list to refresh digest snippet
          const updated = articles.value.find(a => String(a.id) === articleId)
          if (updated) {
            activeArticleDesc.value = (updated?.description || '').trim()
          }
          await loadInsight(articleId)
        }
      } catch {
        // ignore
      }
    }
  }
}

const onArticleDblClick = async (article: any) => {
  if (!article) return
  const articleId = String(article.id || '')
  if (articleId && articleId !== activeArticleId.value) {
    await selectArticle(article)
  }
  await openFullContent()
}

const copyShareLink = async () => {
  try {
    const url = `${window.location.origin}/channels?channel_id=${encodeURIComponent(activeChannelId.value)}`
    await navigator.clipboard.writeText(url)
    Message.success('已复制分享链接')
  } catch (e) {
    Message.error('复制失败')
  }
}

const openFullContent = async () => {
  if (!activeArticleId.value) return
  contentLoading.value = true
  try {
    const res: any = await getArticleDetailPublic(activeArticleId.value)
    activeArticleUrl.value = res.url || ''
    let html = res.content || ''
    if (!(html || '').trim() && hasToken.value) {
      try {
        await fetchArticleContent(activeArticleId.value, { force: false })
        const res2: any = await getArticleDetailPublic(activeArticleId.value)
        activeArticleUrl.value = res2.url || activeArticleUrl.value
        html = res2.content || ''
      } catch {
        // ignore
      }
    }
    activeArticleContent.value = ProxyImage(html || '')
    contentDrawerVisible.value = true
  } catch (e: any) {
    Message.error(e?.message || '获取全文失败')
  } finally {
    contentLoading.value = false
  }
}

const markAllReadForCurrent = async () => {
  if (!hasToken.value) {
    Message.info('请先登录')
    return
  }
  markAllLoading.value = true
  try {
    if (activeTopicFeedIds.value.length) {
      await markAllReadMulti({ mp_ids: activeTopicFeedIds.value, kw: articleKw.value })
    } else {
      await markAllRead({
        mp_id: activeChannelId.value === 'all' ? undefined : activeChannelId.value,
        kw: articleKw.value
      })
    }
    Message.success('已标记已读')
    await loadFeeds()
    await loadArticles()
  } catch (e: any) {
    Message.error(e?.message || '操作失败')
  } finally {
    markAllLoading.value = false
  }
}

const goPlaza = () => router.push('/add-subscription')
const goCreateChannel = () => router.push('/tags/add')
const goExport = () => router.push('/export/records')
	const goTopics = () => router.push('/tags')

const selectTopic = async (t: any) => {
  try {
    activeTopic.value = t
    activeTopicFeedIds.value = JSON.parse(t.mps_id || '[]').map((x: any) => String(x.id || x))
    leftTab.value = 'topics'
    await selectChannel(`topic:${String(t.id)}`, false)
  } catch {
    Message.error('专题数据异常')
  }
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
  () => route.query.topic_id,
  (val: any) => {
    if (!val || typeof val !== 'string') return
    const t = topics.value.find(x => String(x.id) === val)
    if (t) selectTopic(t)
  }
)

onMounted(async () => {
  const q = (route.query.channel_id as string) || ''
  if (q) activeChannelId.value = q
  await loadTopics()
  await loadFeeds()

  const tid = (route.query.topic_id as string) || ''
  if (tid) {
    const t = topics.value.find(x => String(x.id) === tid)
    if (t) await selectTopic(t)
  }
})
</script>

<style scoped>
.channels-page {
  height: calc(100vh - 64px);
}
.channels-layout {
  height: 100%;
}
.sider {
  border-right: 1px solid var(--color-neutral-3);
  background: var(--color-bg-1);
  overflow: hidden;
  display: flex;
  flex-direction: column;
  min-height: 0;
}
.sider-top {
  padding: 12px;
  display: grid;
  gap: 10px;
}
.sider-title {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-weight: 700;
  font-size: 16px;
}
.sider-tabs {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
}
.tab-btn {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.sider-search {
  padding-top: 4px;
}
.sider-list {
  flex: 1;
  overflow: auto;
  padding: 6px;
  min-height: 0;
}
.sider-section {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 6px 6px 10px;
}
.section-title {
  font-weight: 700;
  color: var(--color-text-2);
}
.channel-list {
  padding-bottom: 8px;
}
.channel-item {
  padding: 0;
  border-radius: 10px;
  cursor: pointer;
}
.channel-item :deep(.arco-list-item) {
  padding: 0;
  min-height: 0;
}
.channel-item :deep(.arco-list-item-content) {
  padding: 0;
}
.channel-item-row {
  width: 100%;
  min-width: 0;
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 1px 8px;
  border-radius: 8px;
  min-height: 22px;
  flex-wrap: nowrap;
}
.channel-item.active {
  background: transparent;
}
.channel-item.active .channel-item-row {
  background: var(--color-fill-2);
}
.channel-item:hover {
  background: transparent;
}
.channel-item:hover .channel-item-row {
  background: var(--color-fill-1);
}
.channel-item.active:hover {
  background: transparent;
}
.channel-item.active:hover .channel-item-row {
  background: var(--color-fill-2);
}
.channel-item :deep(.arco-badge-number) {
  transform: translateY(2px);
}
.channel-name {
  font-weight: 600;
  line-height: 20px;
  font-size: 12px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  flex: 1;
}
.channel-item :deep(.arco-badge-number) {
  font-size: 11px;
  line-height: 16px;
  height: 16px;
  min-width: 16px;
  padding: 0 4px;
}
.channel-badge {
  flex: 0 0 auto;
}
.channel-intro {
  display: none;
}
.content {
  padding: 12px;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  min-height: 0;
}
.toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  margin-bottom: 10px;
  flex-wrap: nowrap;
}
.toolbar-left {
  display: flex;
  gap: 8px;
  align-items: center;
  min-width: 0;
}
.toolbar-right {
  display: flex;
  gap: 8px;
  align-items: center;
  flex-wrap: nowrap;
}
.search-input {
  width: 320px;
  max-width: 420px;
  min-width: 180px;
  flex: 1 1 auto;
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
  margin: 10px 0 8px;
  font-weight: 700;
  color: var(--color-text-2);
}
.article-cards {
  display: grid;
  grid-template-columns: 1fr;
  gap: 10px;
}
.article-card {
  border-radius: 12px;
  border: 1px solid var(--color-neutral-3);
}
.article-card.active {
  border-color: var(--color-primary-6);
}
.article-card.read {
  opacity: 0.75;
}
.article-row {
  display: grid;
  grid-template-columns: 92px 1fr;
  gap: 12px;
  align-items: center;
}
.thumb {
  width: 92px;
  height: 68px;
  border-radius: 10px;
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
.article-title {
  font-weight: 700;
  margin-bottom: 6px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.article-subtitle {
  color: var(--color-text-3);
  font-size: 13px;
  margin-bottom: 6px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.article-meta {
  color: var(--color-text-3);
  font-size: 12px;
}
.dot {
  margin: 0 6px;
}
.reader {
  border-left: 1px solid var(--color-neutral-3);
  background: var(--color-bg-1);
  overflow: hidden;
}
.reader-inner {
  padding: 12px;
  height: calc(100vh - 64px);
  overflow: auto;
}
.reader-title {
  font-weight: 800;
  font-size: 16px;
  margin-bottom: 12px;
}
.section-body {
  color: var(--color-text-2);
  font-size: 13px;
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
.outline {
  display: grid;
  gap: 10px;
}
.outline-node {
  padding: 10px;
  border-radius: 10px;
  background: var(--color-fill-1);
  border: 1px solid var(--color-neutral-3);
}
.outline-node.child {
  margin-top: 8px;
  background: var(--color-bg-1);
}
.outline-heading {
  font-weight: 700;
  margin-bottom: 6px;
}
.outline-bullets {
  margin: 0;
  padding-left: 18px;
  color: var(--color-text-2);
}
.outline-children {
  margin-top: 8px;
  display: grid;
  gap: 8px;
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
}
</style>
