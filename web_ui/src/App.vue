<template>
  <a-config-provider size="small">
    <a-layout class="app-container">
      <a-layout-header v-if="route.path !== '/login'" class="app-header">
        <div class="header-inner">
          <div class="brand">
            <router-link class="brand-link" to="/channels">
              <img class="brand-logo" :src="brandHeaderLogo" alt="品牌 Logo" />
              <span class="brand-main-title">大圣之怒</span>
              <span class="brand-sub-title">订阅助手</span>
            </router-link>
            <a-tooltip
              v-if="hasLogined"
              :content="!haswxLogined ? '未授权，请扫码登录' : '点我扫码授权'"
              position="bottom"
            >
              <icon-scan
                class="brand-scan"
                @click="showAuthQrcode()"
                :style="{ color: !haswxLogined ? 'var(--color-danger-6)' : 'var(--color-text-2)' }"
              />
            </a-tooltip>
          </div>

          <div class="header-nav">
            <Navbar />
          </div>

          <div class="header-actions">
            <a-space v-if="showChannelsHeaderActions" size="small" class="channel-header-actions">
              <a-button
                size="small"
                type="outline"
                class="header-action-btn"
                @click="openSubscriptionPlaza"
              >
                订阅广场
              </a-button>
              <a-button
                size="small"
                type="outline"
                class="header-action-btn"
                @click="openTagPlaza"
              >
                频道广场
              </a-button>
              <a-button
                v-if="hasLogined"
                size="small"
                :type="channelsEditMode ? 'primary' : 'outline'"
                class="header-action-btn"
                @click="channelsEditMode = !channelsEditMode"
              >
                {{ channelsEditMode ? '完成' : '编辑订阅' }}
              </a-button>
            </a-space>
            <div class="switch-item">
              <span class="switch-label">系统</span>
              <a-switch v-model="followSystemTheme" size="small" />
            </div>
            <div class="switch-item">
              <span class="switch-label">深色</span>
              <a-switch v-model="manualDarkTheme" size="small" :disabled="followSystemTheme" />
            </div>
            <div class="switch-item">
              <span class="switch-label">翻译</span>
              <a-switch v-model="languageEnabled" size="small" />
            </div>

            <a-dropdown v-if="hasLogined" position="br" trigger="click">
              <div class="user-pill">
                <a-avatar :size="28">
                  <img v-if="userInfo.avatar" :src="userInfo.avatar" alt="avatar" />
                  <icon-user v-else />
                </a-avatar>
                <span class="username">{{ userInfo.username }}</span>
              </div>
              <template #content>
                <a-doption @click="goToEditUser">
                  <template #icon><icon-user /></template>
                  个人中心
                </a-doption>
                <a-doption @click="goToChangePassword">
                  <template #icon><icon-lock /></template>
                  修改密码
                </a-doption>
                <a-doption @click="showAuthQrcode">
                  <template #icon><icon-scan /></template>
                  扫码授权
                </a-doption>
                <a-doption @click="handleLogout">
                  <template #icon><icon-user /></template>
                  退出登录
                </a-doption>
              </template>
            </a-dropdown>
            <a-button v-else size="small" type="primary" @click="openAuthDialog({ tab: 'login' })">
              登录 / 注册
            </a-button>
          </div>
        </div>
        <WechatAuthQrcode ref="qrcodeRef" />
        <a-modal
          v-model:visible="subscriptionPlazaVisible"
          title="订阅广场"
          :footer="false"
          width="1120px"
          unmount-on-close
        >
          <div class="plaza-modal-body">
            <AddSubscription embedded />
          </div>
        </a-modal>
        <a-modal
          v-model:visible="tagPlazaVisible"
          title="频道广场"
          :footer="false"
          width="1040px"
          unmount-on-close
        >
          <div class="tag-plaza-modal">
            <a-tabs v-model:active-key="tagPlazaTab" size="small">
              <a-tab-pane key="plaza" title="频道广场">
                <div class="tag-plaza-toolbar">
                  <a-input
                    v-model="tagPlazaKeyword"
                    size="small"
                    allow-clear
                    placeholder="搜索频道广场"
                    @press-enter="searchTagPlaza"
                  />
                  <a-button size="small" type="outline" @click="searchTagPlaza">搜索</a-button>
                </div>
                <a-spin :loading="tagPlazaLoading">
                  <div v-if="tagPlazaItems.length" class="tag-plaza-grid">
                    <div v-for="tag in tagPlazaItems" :key="tag.id" class="tag-plaza-card">
                      <div class="tag-plaza-main">
                        <a-avatar :size="42" :image-url="tagCover(tag)">
                          <img :src="tagCover(tag)" />
                        </a-avatar>
                        <div class="tag-plaza-text">
                          <div class="tag-plaza-name-row">
                            <div class="tag-plaza-name">{{ tag.name }}</div>
                            <div class="tag-plaza-count">{{ Number(tag.mp_count || 0) }} 源</div>
                          </div>
                          <div class="tag-plaza-desc">{{ tag.creator_display || tag.creator_nickname || tag.creator_username || '频道广场' }}</div>
                        </div>
                      </div>
                      <a-button
                        size="small"
                        type="primary"
                        :disabled="!!tag.is_mine"
                        :loading="tagPlazaUsingId === tag.id"
                        @click="useTag(tag)"
                      >
                        {{ tag.is_mine ? '已添加' : '加入频道' }}
                      </a-button>
                    </div>
                  </div>
                  <div v-else class="tag-plaza-empty">暂无可用频道。</div>
                </a-spin>
              </a-tab-pane>

              <a-tab-pane key="mine" title="我的频道管理">
                <div class="tag-manage-toolbar">
                  <a-input
                    v-model="myTagForm.name"
                    size="small"
                    :max-length="40"
                    class="tag-manage-input-name"
                    placeholder="频道名称（必填）"
                  />
                  <a-input
                    v-model="myTagForm.intro"
                    size="small"
                    :max-length="120"
                    class="tag-manage-input-intro"
                    placeholder="频道简介（选填）"
                  />
                  <a-button size="small" type="outline" @click="showFeedSelector = true">
                    选择订阅项（{{ myTagForm.mps_id.length }}）
                  </a-button>
                  <a-button
                    size="small"
                    type="primary"
                    :loading="myTagSaving"
                    @click="saveMyTag"
                  >
                    {{ myTagEditingId ? '更新频道' : '创建频道' }}
                  </a-button>
                  <a-button v-if="myTagEditingId" size="small" type="outline" @click="resetMyTagForm">
                    取消编辑
                  </a-button>
                </div>

                <div class="tag-manage-search">
                  <a-input
                    v-model="myTagKeyword"
                    size="small"
                    allow-clear
                    class="tag-manage-filter"
                    placeholder="搜索我的频道"
                  />
                  <a-button size="small" type="outline" :loading="myTagsLoading" @click="fetchMyTags">
                    刷新
                  </a-button>
                </div>

                <a-spin :loading="myTagsLoading">
                  <div v-if="filteredMyTags.length" class="tag-plaza-grid">
                    <div v-for="tag in filteredMyTags" :key="tag.id" class="tag-plaza-card">
                      <div class="tag-plaza-main">
                        <a-avatar :size="42" :image-url="tagCover(tag)">
                          <img :src="tagCover(tag)" />
                        </a-avatar>
                        <div class="tag-plaza-text">
                          <div class="tag-plaza-name-row">
                            <div class="tag-plaza-name">{{ tag.name }}</div>
                            <div class="tag-plaza-count">{{ myTagMpsCount(tag) }} 源</div>
                          </div>
                          <div class="tag-plaza-desc">{{ tag.intro || '暂无简介' }}</div>
                        </div>
                      </div>
                      <a-space size="mini">
                        <a-button size="mini" type="outline" @click="editMyTag(tag)">编辑</a-button>
                        <a-button
                          size="mini"
                          status="danger"
                          :loading="myTagDeletingId === tag.id"
                          @click="removeMyTag(tag)"
                        >
                          删除
                        </a-button>
                      </a-space>
                    </div>
                  </div>
                  <div v-else class="tag-plaza-empty">你还没有创建频道。</div>
                </a-spin>
              </a-tab-pane>
            </a-tabs>
          </div>
        </a-modal>
        <a-modal
          v-model:visible="showFeedSelector"
          title="选择订阅项"
          :footer="false"
          width="960px"
          unmount-on-close
        >
          <FeedMultiSelect ref="feedSelectorRef" v-model="myTagForm.mps_id" />
          <template #footer>
            <a-button type="primary" size="small" @click="showFeedSelector = false">确定</a-button>
          </template>
        </a-modal>
        <a-modal
          v-model:visible="authDialogVisible"
          :title="authTab === 'login' ? '登录账号' : '注册账号'"
          width="560px"
          :footer="false"
          unmount-on-close
        >
          <div class="auth-modal-intro">
            <img class="auth-intro-logo" :src="brandHeaderLogo" alt="品牌 Logo" />
            <div class="auth-intro-text">
              <div class="auth-intro-title">大圣之怒订阅助手</div>
              <div class="auth-intro-desc">
                游客可直接浏览默认订阅。登录后可创建个人订阅、刷新同步，并在订阅广场添加自定义博主。
              </div>
              <div class="auth-intro-features">公众号与多平台抓取 · 频道化聚合 · 定时刷新与摘要</div>
            </div>
          </div>

          <a-tabs v-model:active-key="authTab" size="small" type="rounded">
            <a-tab-pane key="login" title="登录">
              <a-form :model="loginForm" layout="vertical">
                <a-form-item field="username" label="帐号">
                  <a-input v-model="loginForm.username" placeholder="请输入帐号" />
                </a-form-item>
                <a-form-item field="password" label="密码">
                  <a-input-password v-model="loginForm.password" placeholder="请输入密码" />
                </a-form-item>
                <a-button type="primary" long :loading="authSubmitting" @click="submitLogin">
                  登录
                </a-button>
              </a-form>
            </a-tab-pane>

            <a-tab-pane key="register" title="注册">
              <a-form :model="registerForm" layout="vertical">
                <a-form-item field="username" label="帐号">
                  <a-input v-model="registerForm.username" placeholder="2-50位帐号" />
                </a-form-item>
                <a-form-item field="password" label="密码">
                  <a-input-password v-model="registerForm.password" placeholder="至少6位密码" />
                </a-form-item>
                <a-form-item field="email" label="邮箱">
                  <a-input v-model="registerForm.email" placeholder="name@example.com" />
                </a-form-item>
                <a-form-item field="verify_code" label="邮箱验证码">
                  <a-space style="width: 100%;">
                    <a-input v-model="registerForm.verify_code" placeholder="请输入验证码" />
                    <a-button
                      type="outline"
                      :loading="authCodeSending"
                      :disabled="authCodeSending || authCodeCooldown > 0"
                      @click="sendRegisterCode"
                    >
                      {{ authCodeCooldown > 0 ? `${authCodeCooldown}s` : '发送验证码' }}
                    </a-button>
                  </a-space>
                </a-form-item>
                <a-button type="primary" long :loading="authSubmitting" @click="submitRegister">
                  注册并登录
                </a-button>
              </a-form>
            </a-tab-pane>
          </a-tabs>
        </a-modal>
    </a-layout-header>

    <a-layout>
      <a-layout>
        <a-layout-content class="app-content">
          <router-view />
        </a-layout-content>
      </a-layout>
    </a-layout>
  </a-layout>
  </a-config-provider>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, provide, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Message, Modal } from '@arco-design/web-vue'
import { getCurrentUser, login, logout, refreshToken, register, sendRegisterEmailCode } from '@/api/auth'
import { getSysInfo } from '@/api/sysInfo'
import Navbar from '@/components/Layout/Navbar.vue'
import WechatAuthQrcode from '@/components/WechatAuthQrcode.vue'
import AddSubscription from '@/views/AddSubscription.vue'
import FeedMultiSelect from '@/components/FeedMultiSelect.vue'
import { initBrowserNotification } from '@/utils/browserNotification'
import { translatePage, setCurrentLanguage } from '@/utils/translate'
import { getThemeMode, setThemeMode, type ThemeMode } from '@/utils/theme'
import brandHeaderLogo from '@/assets/logo-original.png'
import { listTagPlaza, useTagFromPlaza, listTags, createTag, updateTag, deleteTag, type TagPlazaItem } from '@/api/tagManagement'
import { pickDefaultChannelLogo } from '@/constants/channelLogos'
import { clearAuthSession, getToken, isTokenExpiringSoon, setAuthSession, ensureTokenExpire } from '@/utils/auth'
import type { Tag } from '@/types/tagManagement'

type AuthTab = 'login' | 'register'

const themeMode = ref<ThemeMode>(getThemeMode())
const setThemeModeLocal = (mode: ThemeMode) => {
  themeMode.value = mode
  setThemeMode(mode)
}
const followSystemTheme = computed<boolean>({
  get: () => themeMode.value === 'system',
  set: (v) => {
    if (v) {
      setThemeModeLocal('system')
      return
    }
    const isDarkNow = document.body?.getAttribute('arco-theme') === 'dark'
    setThemeModeLocal(isDarkNow ? 'dark' : 'light')
  }
})
const manualDarkTheme = computed<boolean>({
  get: () => themeMode.value === 'dark',
  set: (v) => setThemeModeLocal(v ? 'dark' : 'light')
})

const currentLanguage = ref(localStorage.getItem('language') || 'chinese_simplified')
const languageBackup = ref(localStorage.getItem('language_backup') || 'chinese_simplified')
const languageEnabled = computed<boolean>({
  get: () => String(currentLanguage.value || '').trim().length > 0,
  set: (v) => {
    if (v) {
      const next = String(languageBackup.value || 'chinese_simplified') || 'chinese_simplified'
      currentLanguage.value = next
      setCurrentLanguage(next)
      return
    }
    if (String(currentLanguage.value || '').trim()) {
      languageBackup.value = currentLanguage.value
      localStorage.setItem('language_backup', languageBackup.value)
    }
    currentLanguage.value = ''
    setCurrentLanguage('')
  }
})

const _errMsg = (e: any, fallback = '操作失败') => {
  if (typeof e === 'string' && e.trim()) return e
  const msg = e?.message || e?.detail?.message || e?.response?.data?.message || e?.response?.data?.detail?.message
  return typeof msg === 'string' && msg.trim() ? msg : fallback
}

const qrcodeRef = ref()
const showAuthQrcode = () => {
  qrcodeRef.value?.startAuth()
}
provide('showAuthQrcode', showAuthQrcode)
const channelsEditMode = ref(false)
provide('channelsEditMode', channelsEditMode)

const subscriptionPlazaVisible = ref(false)
const tagPlazaVisible = ref(false)
const tagPlazaTab = ref<'plaza' | 'mine'>('plaza')
const tagPlazaLoading = ref(false)
const tagPlazaUsingId = ref('')
const tagPlazaKeyword = ref('')
const tagPlazaItems = ref<TagPlazaItem[]>([])
const myTagsLoading = ref(false)
const myTagSaving = ref(false)
const myTagDeletingId = ref('')
const myTagKeyword = ref('')
const myTagEditingId = ref('')
const myTags = ref<Tag[]>([])
const showFeedSelector = ref(false)
const feedSelectorRef = ref<InstanceType<typeof FeedMultiSelect> | null>(null)
const myTagForm = ref<{ name: string; intro: string; cover: string | null; status: number; mps_id: any[] }>({
  name: '',
  intro: '',
  cover: null,
  status: 1,
  mps_id: [],
})
const showChannelsHeaderActions = computed(() => route.path.startsWith('/channels'))

const tagCover = (tag: TagPlazaItem | Tag) => {
  const cover = String(tag?.cover || '').trim()
  if (cover) return cover
  return pickDefaultChannelLogo(String(tag?.name || ''))
}

const parseTagFeeds = (raw: any): any[] => {
  if (Array.isArray(raw)) return raw
  try {
    const parsed = JSON.parse(String(raw || '[]'))
    return Array.isArray(parsed) ? parsed : []
  } catch {
    return []
  }
}

const myTagMpsCount = (tag: Tag) => parseTagFeeds((tag as any)?.mps_id).length

const filteredMyTags = computed(() => {
  const q = String(myTagKeyword.value || '').trim().toLowerCase()
  if (!q) return myTags.value
  return myTags.value.filter((tag) => {
    const hay = `${tag.name || ''} ${tag.intro || ''}`.toLowerCase()
    return hay.includes(q)
  })
})

const resetMyTagForm = () => {
  myTagEditingId.value = ''
  myTagForm.value = {
    name: '',
    intro: '',
    cover: null,
    status: 1,
    mps_id: [],
  }
}

const fetchMyTags = async () => {
  myTagsLoading.value = true
  try {
    const res: any = await listTags({ offset: 0, limit: 300 })
    myTags.value = res?.list || []
  } catch (e: any) {
    Message.error(_errMsg(e, '获取我的频道失败'))
    myTags.value = []
  } finally {
    myTagsLoading.value = false
  }
}

const saveMyTag = async () => {
  const name = String(myTagForm.value.name || '').trim()
  if (!name) {
    Message.info('请先输入频道名称')
    return
  }
  if (!myTagForm.value.mps_id.length) {
    Message.info('请先选择至少一个订阅项')
    return
  }
  myTagSaving.value = true
  try {
    const payload: any = {
      name,
      intro: String(myTagForm.value.intro || '').trim(),
      cover: String(myTagForm.value.cover || '').trim() || pickDefaultChannelLogo(name),
      status: 1,
      mps_id: JSON.stringify(myTagForm.value.mps_id || []),
    }
    if (myTagEditingId.value) {
      await updateTag(myTagEditingId.value, payload)
      Message.success('频道已更新')
    } else {
      await createTag(payload)
      Message.success('频道已创建')
    }
    resetMyTagForm()
    await Promise.allSettled([fetchMyTags(), fetchTagPlaza()])
    window.dispatchEvent(new Event('tags-updated'))
  } catch (e: any) {
    Message.error(_errMsg(e, '保存频道失败'))
  } finally {
    myTagSaving.value = false
  }
}

const editMyTag = (tag: Tag) => {
  myTagEditingId.value = String(tag.id || '')
  const name = String(tag.name || '').trim()
  myTagForm.value = {
    name,
    intro: String(tag.intro || '').trim(),
    cover: String(tag.cover || '').trim() || pickDefaultChannelLogo(name),
    status: Number(tag.status || 1) === 1 ? 1 : 0,
    mps_id: parseTagFeeds((tag as any).mps_id),
  }
  tagPlazaTab.value = 'mine'
}

const removeMyTag = (tag: Tag) => {
  const id = String(tag.id || '')
  if (!id || myTagDeletingId.value) return
  Modal.confirm({
    title: '删除频道',
    content: `确认删除频道「${tag.name || '未命名'}」吗？`,
    onOk: async () => {
      myTagDeletingId.value = id
      try {
        await deleteTag(id)
        Message.success('频道已删除')
        if (myTagEditingId.value === id) resetMyTagForm()
        await Promise.allSettled([fetchMyTags(), fetchTagPlaza()])
        window.dispatchEvent(new Event('tags-updated'))
      } catch (e: any) {
        Message.error(_errMsg(e, '删除频道失败'))
      } finally {
        myTagDeletingId.value = ''
      }
    },
  })
}

const fetchTagPlaza = async () => {
  tagPlazaLoading.value = true
  try {
    const res: any = await listTagPlaza({
      offset: 0,
      limit: 60,
      keyword: String(tagPlazaKeyword.value || '').trim().slice(0, 100),
    })
    tagPlazaItems.value = res?.list || []
  } catch (e: any) {
    Message.error(_errMsg(e, '获取频道广场失败'))
  } finally {
    tagPlazaLoading.value = false
  }
}

const openTagPlaza = async () => {
  if (!hasLogined.value) {
    openAuthDialog({ tab: 'register', afterLogin: 'none' })
    return
  }
  tagPlazaVisible.value = true
  tagPlazaTab.value = 'plaza'
  await Promise.allSettled([fetchTagPlaza(), fetchMyTags()])
}

const searchTagPlaza = async () => {
  await fetchTagPlaza()
}

const useTag = async (tag: TagPlazaItem) => {
  if (!hasLogined.value) {
    openAuthDialog({ tab: 'login', afterLogin: 'none' })
    return
  }
  if (!tag?.id || tagPlazaUsingId.value) return
  tagPlazaUsingId.value = tag.id
  try {
    const res: any = await useTagFromPlaza(tag.id)
    Message.success(res?.message || '已添加到我的频道')
    await fetchTagPlaza()
    window.dispatchEvent(new Event('tags-updated'))
  } catch (e: any) {
    Message.error(_errMsg(e, '使用频道失败'))
  } finally {
    tagPlazaUsingId.value = ''
  }
}

const router = useRouter()
const route = useRoute()
const isValidEmail = (email: string) => /^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$/.test(String(email || '').trim())
const authDialogVisible = ref(false)
const authTab = ref<AuthTab>('login')
const authSubmitting = ref(false)
const authCodeSending = ref(false)
const authCodeCooldown = ref(0)
const authAfterLogin = ref<'none' | 'open-subscription-plaza'>('none')
const authRedirectPath = ref('')
let authCodeTimer: ReturnType<typeof setInterval> | null = null
const loginForm = ref({ username: '', password: '' })
const registerForm = ref({ username: '', password: '', email: '', verify_code: '' })

const userInfo = ref({ username: '', avatar: '' })
const haswxLogined = ref(true)
const hasLogined = ref(false)
const tokenRefreshing = ref(false)
const TOKEN_REFRESH_CHECK_INTERVAL_MS = 2 * 60 * 1000
const TOKEN_REFRESH_THRESHOLD_MS = 15 * 60 * 1000
let tokenRefreshTimer: ReturnType<typeof setInterval> | null = null
const isAuthenticated = computed(() => {
  hasLogined.value = !!getToken()
  return hasLogined.value
})

const scheduleTokenRefresh = async (force = false) => {
  if (!getToken()) return
  ensureTokenExpire()
  if (!force && !isTokenExpiringSoon(TOKEN_REFRESH_THRESHOLD_MS)) return
  if (tokenRefreshing.value) return
  tokenRefreshing.value = true
  try {
    const res: any = await refreshToken()
    if (res?.access_token) {
      setAuthSession(String(res.access_token || ''), Number(res?.expires_in || 0))
    }
  } catch {
    // 401 会在 http 拦截器里统一清会话并跳登录，这里不重复处理。
  } finally {
    tokenRefreshing.value = false
  }
}

const startTokenRefreshLoop = () => {
  if (!getToken()) return
  if (tokenRefreshTimer) return
  tokenRefreshTimer = setInterval(() => {
    scheduleTokenRefresh(false).catch(() => {})
  }, TOKEN_REFRESH_CHECK_INTERVAL_MS)
  document.addEventListener('visibilitychange', onVisibilityChange)
}

const stopTokenRefreshLoop = () => {
  if (tokenRefreshTimer) {
    clearInterval(tokenRefreshTimer)
    tokenRefreshTimer = null
  }
  document.removeEventListener('visibilitychange', onVisibilityChange)
}

const onVisibilityChange = () => {
  if (document.hidden) return
  scheduleTokenRefresh(false).catch(() => {})
}

const fetchUserInfo = async () => {
  try {
    const res = await getCurrentUser()
    userInfo.value = res
    localStorage.setItem('current_user_role', String(res?.role || 'user'))
    window.dispatchEvent(new Event('user-role-updated'))
  } catch (error) {
    console.error('获取用户信息失败', error)
    localStorage.removeItem('current_user_role')
    window.dispatchEvent(new Event('user-role-updated'))
  }
}

const fetchSysInfo = async () => {
  try {
    const res = await getSysInfo()
    haswxLogined.value = res?.wx?.login || false
  } catch (error) {
    console.error('获取系统信息失败', error)
  }
}

const startAuthCodeCooldown = (seconds = 60) => {
  authCodeCooldown.value = Math.max(0, Number(seconds || 60))
  if (authCodeTimer) clearInterval(authCodeTimer)
  authCodeTimer = setInterval(() => {
    authCodeCooldown.value = Math.max(0, authCodeCooldown.value - 1)
    if (authCodeCooldown.value <= 0 && authCodeTimer) {
      clearInterval(authCodeTimer)
      authCodeTimer = null
    }
  }, 1000)
}

const openAuthDialog = (opts?: { tab?: AuthTab; afterLogin?: 'none' | 'open-subscription-plaza'; redirect?: string }) => {
  authTab.value = (opts?.tab || authTab.value || 'login') as AuthTab
  authAfterLogin.value = opts?.afterLogin || authAfterLogin.value || 'none'
  authRedirectPath.value = String(opts?.redirect || authRedirectPath.value || '').trim()
  if (!loginForm.value.username) loginForm.value.username = String(userInfo.value.username || '').trim()
  if (!registerForm.value.username) registerForm.value.username = String(userInfo.value.username || '').trim()
  authDialogVisible.value = true
}

const normalizeRedirect = (raw: string) => {
  const value = String(raw || '').trim()
  if (!value || !value.startsWith('/')) return ''
  if (value.startsWith('/login')) return '/channels'
  return value
}

const showFirstLoginHint = () => {
  const username = String(userInfo.value.username || '').trim().toLowerCase() || 'default'
  const key = `dasheng_onboarding_hint_seen_${username}`
  if (localStorage.getItem(key)) return
  localStorage.setItem(key, '1')
  Modal.info({
    title: '首次使用提示',
    content:
      '建议先在“订阅广场”选择一批博主。若要添加微信里的自定义博主，请点击顶部扫码授权，再到订阅广场搜索添加。',
    okText: '知道了',
  })
}

const afterAuthSuccess = async (opts?: { openPlaza?: boolean }) => {
  hasLogined.value = true
  ensureTokenExpire()
  startTokenRefreshLoop()
  await Promise.allSettled([fetchUserInfo(), fetchSysInfo()])
  showFirstLoginHint()

  const shouldOpenPlaza = !!opts?.openPlaza || authAfterLogin.value === 'open-subscription-plaza'
  const redirect = normalizeRedirect(authRedirectPath.value)
  authAfterLogin.value = 'none'
  authRedirectPath.value = ''

  if (redirect && redirect !== route.fullPath) {
    await router.push(redirect)
  } else if (!route.path.startsWith('/channels')) {
    await router.push('/channels')
  }
  if (shouldOpenPlaza) {
    subscriptionPlazaVisible.value = true
  }
}

const submitLogin = async () => {
  if (authSubmitting.value) return
  const username = String(loginForm.value.username || '').trim()
  const password = String(loginForm.value.password || '')
  if (!username) {
    Message.error('请输入帐号')
    return
  }
  if (!password) {
    Message.error('请输入密码')
    return
  }
  authSubmitting.value = true
  try {
    const res: any = await login({ username, password })
    if (!res?.access_token) throw new Error('登录失败，请稍后重试')
    setAuthSession(String(res.access_token || ''), Number(res?.expires_in || 0))
    authDialogVisible.value = false
    await afterAuthSuccess()
    Message.success('登录成功')
  } catch (e: any) {
    Message.error(_errMsg(e, '登录失败'))
  } finally {
    authSubmitting.value = false
  }
}

const sendRegisterCode = async () => {
  if (authCodeSending.value || authCodeCooldown.value > 0) return
  const email = String(registerForm.value.email || '').trim()
  if (!isValidEmail(email)) {
    Message.error('请输入有效邮箱')
    return
  }
  authCodeSending.value = true
  try {
    const res: any = await sendRegisterEmailCode({ email })
    startAuthCodeCooldown(60)
    Message.success(`验证码已发送（有效期约 ${Number(res?.ttl_minutes || 10)} 分钟）`)
  } catch (e: any) {
    Message.error(_errMsg(e, '发送验证码失败'))
  } finally {
    authCodeSending.value = false
  }
}

const submitRegister = async () => {
  if (authSubmitting.value) return
  const username = String(registerForm.value.username || '').trim()
  const password = String(registerForm.value.password || '')
  const email = String(registerForm.value.email || '').trim()
  const verifyCode = String(registerForm.value.verify_code || '').trim()
  if (username.length < 2) {
    Message.error('请输入至少2位帐号')
    return
  }
  if (password.length < 6) {
    Message.error('请输入至少6位密码')
    return
  }
  if (!isValidEmail(email)) {
    Message.error('请输入有效邮箱')
    return
  }
  if (!verifyCode) {
    Message.error('请输入邮箱验证码')
    return
  }
  authSubmitting.value = true
  try {
    const res: any = await register({ username, password, email, verify_code: verifyCode })
    if (!res?.access_token) throw new Error('注册失败，请稍后重试')
    setAuthSession(String(res.access_token || ''), Number(res?.expires_in || 0))
    authDialogVisible.value = false
    await afterAuthSuccess({ openPlaza: true })
    Message.success('注册成功，请先选择你感兴趣的订阅源')
  } catch (e: any) {
    Message.error(_errMsg(e, '注册失败'))
  } finally {
    authSubmitting.value = false
  }
}

const goToEditUser = () => router.push({ name: 'EditUser' })
const goToChangePassword = () => router.push({ name: 'ChangePassword' })

const handleLogout = async () => {
  try {
    await logout()
    clearAuthSession()
    window.dispatchEvent(new Event('user-role-updated'))
    router.push('/channels')
  } catch {
    Message.error('退出登录失败')
  }
}

const openSubscriptionPlaza = () => {
  if (hasLogined.value) {
    subscriptionPlazaVisible.value = true
    return
  }
  openAuthDialog({ tab: 'register', afterLogin: 'open-subscription-plaza' })
}

const maybeOpenSubscriptionPlaza = async () => {
  if (!hasLogined.value) return
  if (!route.path.startsWith('/channels')) return
  const q = String((route.query as any)?.plaza || '').trim().toLowerCase()
  if (!(q === '1' || q === 'true' || q === 'yes')) return
  subscriptionPlazaVisible.value = true
  const nextQuery = { ...(route.query as any) }
  delete nextQuery.plaza
  try {
    await router.replace({ path: route.path, query: nextQuery })
  } catch {
    // ignore
  }
}

const maybeOpenAuthDialogByQuery = async () => {
  if (!route.path.startsWith('/channels')) return
  const authQ = String((route.query as any)?.auth || '').trim().toLowerCase()
  if (!(authQ === '1' || authQ === 'true' || authQ === 'yes')) return
  const tabRaw = String((route.query as any)?.tab || '').trim().toLowerCase()
  const tab: AuthTab = tabRaw === 'register' ? 'register' : 'login'
  const needRaw = String((route.query as any)?.need || '').trim().toLowerCase()
  const afterLogin = needRaw === 'plaza' ? 'open-subscription-plaza' : 'none'
  const redirect = String((route.query as any)?.redirect || '').trim()
  openAuthDialog({ tab, afterLogin, redirect })
  const nextQuery: Record<string, any> = { ...(route.query as any) }
  delete nextQuery.auth
  delete nextQuery.tab
  delete nextQuery.need
  delete nextQuery.redirect
  try {
    await router.replace({ path: route.path, query: nextQuery })
  } catch {
    // ignore
  }
}

const handleAuthRequiredEvent = (e: Event) => {
  const detail = ((e as CustomEvent).detail || {}) as {
    tab?: AuthTab
    need?: 'plaza' | 'none'
    redirect?: string
  }
  openAuthDialog({
    tab: detail?.tab === 'register' ? 'register' : 'login',
    afterLogin: detail?.need === 'plaza' ? 'open-subscription-plaza' : 'none',
    redirect: detail?.redirect || '',
  })
}

	onMounted(() => {
	  if (isAuthenticated.value) fetchUserInfo()
	  if (isAuthenticated.value) {
      ensureTokenExpire()
      scheduleTokenRefresh(false).catch(() => {})
      startTokenRefreshLoop()
    }
	  initBrowserNotification()
	  translatePage()
	  fetchSysInfo()
    maybeOpenSubscriptionPlaza().catch(() => {})
    maybeOpenAuthDialogByQuery().catch(() => {})
    window.addEventListener('dasheng-auth-required', handleAuthRequiredEvent as EventListener)
	})

onUnmounted(() => {
  stopTokenRefreshLoop()
  if (authCodeTimer) {
    clearInterval(authCodeTimer)
    authCodeTimer = null
  }
  window.removeEventListener('dasheng-auth-required', handleAuthRequiredEvent as EventListener)
})

watch(
  () => route.fullPath,
  () => {
    hasLogined.value = !!getToken()
    if (!route.path.startsWith('/channels')) {
      channelsEditMode.value = false
    }
	    if (hasLogined.value) {
	      fetchUserInfo()
        startTokenRefreshLoop()
        scheduleTokenRefresh(false).catch(() => {})
        maybeOpenSubscriptionPlaza().catch(() => {})
	    } else {
        stopTokenRefreshLoop()
        channelsEditMode.value = false
	    }
      maybeOpenAuthDialogByQuery().catch(() => {})
	  }
	)
</script>

<style scoped>
.app-container {
  min-height: 100vh;
}

.app-header {
  padding: 0 10px;
  height: var(--app-header-height);
  position: sticky;
  top: 0;
  z-index: 100;
  background: color-mix(in srgb, var(--app-surface-1) 94%, transparent);
  backdrop-filter: blur(16px) saturate(145%);
  border-bottom: 1px solid var(--app-border-soft);
}

.header-inner {
  width: 100%;
  height: 100%;
  display: flex;
  align-items: center;
  gap: 12px;
}

.brand {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
}

.brand-link {
  display: inline-flex;
  align-items: center;
  justify-content: flex-start;
  height: 42px;
  max-width: 100%;
  padding: 0;
  border-radius: 10px;
  text-decoration: none;
}

.brand-logo {
  width: auto;
  height: 40px;
  object-fit: contain;
  border-radius: 8px;
  display: block;
  flex: 0 0 auto;
}

.brand-sub-title {
  font-size: 14px;
  font-weight: 800;
  letter-spacing: 0;
  line-height: 1;
  color: var(--brand-blue-6);
  white-space: nowrap;
}

.brand-main-title {
  font-size: 14px;
  font-weight: 900;
  letter-spacing: 0;
  line-height: 1;
  color: var(--brand-red-6);
  white-space: nowrap;
}

.brand-link:hover {
  text-decoration: none;
}

.brand-scan {
  cursor: pointer;
  color: var(--color-text-2);
  transition: color 0.2s ease;
}

.brand-scan:hover {
  color: var(--brand-red-6);
}

.header-nav {
  flex: 1 1 auto;
  min-width: 0;
  display: flex;
  justify-content: flex-start;
  overflow-x: auto;
  overflow-y: hidden;
  scrollbar-width: none;
}

.header-nav::-webkit-scrollbar {
  display: none;
}

.header-actions {
  display: flex;
  align-items: center;
  gap: 6px;
  flex: 0 0 auto;
}

.channel-header-actions {
  margin-right: 2px;
  padding: 3px;
  border-radius: 11px;
  border: 1px solid var(--app-border-soft);
  background: var(--app-surface-1);
  box-shadow: var(--app-shadow-card);
}

.header-action-btn {
  height: 32px !important;
  border-radius: 8px;
  padding: 0 10px;
  font-weight: 600;
  border-color: var(--app-border-soft);
  background: color-mix(in srgb, var(--app-surface-2) 95%, transparent);
}

.switch-item {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 3px 7px;
  border-radius: 10px;
  border: 1px solid var(--app-border-soft);
  background: var(--app-surface-1);
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.34);
}
.switch-label {
  font-size: 11px;
  color: var(--color-text-2);
  letter-spacing: -0.1px;
}

.user-pill {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 4px 10px;
  border-radius: 999px;
  border: 1px solid var(--app-border-soft);
  background: var(--app-surface-1);
  cursor: pointer;
  box-shadow: var(--app-shadow-card);
}

.username {
  font-size: 13px;
  color: var(--color-text-1);
}

.plaza-modal-body {
  max-height: min(78vh, 860px);
  overflow: auto;
}

.tag-plaza-modal {
  display: grid;
  gap: 12px;
}

.tag-plaza-toolbar {
  display: flex;
  align-items: center;
  gap: 8px;
}

.tag-manage-toolbar {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  margin-bottom: 8px;
}

.tag-manage-search {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 10px;
}

.tag-manage-input-name {
  width: 180px;
}

.tag-manage-input-intro {
  width: min(320px, 46vw);
}

.tag-manage-filter {
  width: min(300px, 46vw);
}

.tag-plaza-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
}

.tag-plaza-card {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 12px;
  border-radius: 14px;
  border: 1px solid var(--app-border-soft);
  background: var(--app-surface-2);
  box-shadow: var(--app-shadow-card);
}

.tag-plaza-main {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
  flex: 1;
}

.tag-plaza-text {
  min-width: 0;
  flex: 1;
}

.tag-plaza-name-row {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.tag-plaza-name {
  font-size: 14px;
  font-weight: 700;
  color: var(--color-text-1);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.tag-plaza-count {
  flex: 0 0 auto;
  color: var(--color-text-3);
  font-size: 12px;
}

.tag-plaza-desc,
.tag-plaza-empty {
  color: var(--color-text-3);
  font-size: 12px;
}

.tag-plaza-desc {
  margin-top: 4px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.auth-modal-intro {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 10px;
  padding: 10px;
  border-radius: 12px;
  border: 1px solid var(--app-border-soft);
  background: var(--app-surface-1);
  box-shadow: var(--app-shadow-card);
}

.auth-intro-logo {
  width: 36px;
  height: 36px;
  object-fit: contain;
  border-radius: 8px;
  flex: 0 0 auto;
}

.auth-intro-text {
  min-width: 0;
}

.auth-intro-title {
  font-size: 14px;
  font-weight: 800;
  color: var(--color-text-1);
}

.auth-intro-desc {
  margin-top: 2px;
  font-size: 12px;
  color: var(--color-text-3);
  line-height: 1.45;
}

.auth-intro-features {
  margin-top: 4px;
  font-size: 11px;
  color: var(--color-text-3);
}

.app-content {
  background: var(--color-bg-1);
  min-height: calc(100vh - var(--app-header-height));
}

@media (max-width: 1100px) {
  .tag-plaza-grid {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 720px) {
  .brand-link {
    height: 38px;
  }
  .brand-logo {
    height: 36px;
  }
  .brand-sub-title {
    font-size: 14px;
  }
  .brand-main-title {
    font-size: 14px;
  }
  .brand-scan {
    display: none;
  }
  .header-actions {
    display: none !important;
  }
}
</style>
