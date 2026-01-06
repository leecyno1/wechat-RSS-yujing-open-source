<template>
  <a-layout class="app-container">
    <a-layout-header v-if="route.path !== '/login'" class="app-header">
      <div class="header-inner">
        <div class="brand">
          <img class="brand-logo" :src="logo" alt="logo" />
          <router-link class="brand-title" to="/channels">{{ appTitle }}</router-link>
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
          <a-select
            v-model:value="themeMode"
            class="theme-select"
            size="small"
            :trigger-props="{ autoFitPopupMinWidth: true }"
            @change="handleThemeChange"
          >
            <a-option value="system">System</a-option>
            <a-option value="light">Light</a-option>
            <a-option value="dark">Dark</a-option>
          </a-select>

          <a-select
            v-model:value="currentLanguage"
            class="lang-select"
            size="small"
            :trigger-props="{ autoFitPopupMinWidth: true }"
            @change="handleLanguageChange"
          >
            <a-option v-for="opt in languageOptions" :key="opt.value" :value="opt.value">
              {{ opt.label }}
            </a-option>
          </a-select>

          <a-tooltip v-if="hasLogined" content="关注后每天自动推送AI摘要与精选文章" position="bottom">
            <a-button class="promo-btn" type="text" @click="showPromoModal">关注柠檬博士</a-button>
          </a-tooltip>

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
        </div>
      </div>
      <WechatAuthQrcode ref="qrcodeRef" />
      <a-modal
        v-model:visible="promoVisible"
        title="关注「柠檬博士」"
        :footer="false"
        :style="{ zIndex: 1000 }"
        unmount-on-close
        @close="dismissPromo"
      >
	        <div style="text-align: center;">
	          <p>关注柠檬博士公众号，每天自动向你发送你定制的AI摘要和精选文章</p>
	          <div style="margin-top: 16px;">
	            <template v-if="wechatBinding.is_bound">
	              <img
	                v-if="!promoQrError"
	                :src="promoQrSrc"
	                alt="柠檬博士公众号二维码"
	                style="max-width: 320px; border-radius: 12px;"
	                @error="promoQrError = true"
	              />
	              <div v-else style="margin-top: 12px; color: var(--color-text-3); font-size: 12px;">
	                二维码未配置：请设置 `PROMO_QR_URL` 或放置 `data/promo_qr.png`（容器内路径 `/app/data/promo_qr.png`）。
	              </div>
	            </template>
	
	            <template v-else>
	              <a-spin :loading="bindQrcodeLoading">
	                <div style="display: inline-block;">
	                  <img
	                    v-if="bindQrcodeUrl && !bindQrcodeImgError"
	                    :src="bindQrcodeUrl"
	                    alt="绑定二维码"
	                    style="max-width: 320px; border-radius: 12px;"
	                    @error="bindQrcodeImgError = true"
	                  />
	                  <div
	                    v-else
	                    style="
	                      width: 320px;
	                      height: 320px;
	                      display: flex;
	                      align-items: center;
	                      justify-content: center;
	                      border-radius: 12px;
	                      border: 1px dashed var(--color-neutral-4);
	                      color: var(--color-text-3);
	                      font-size: 12px;
	                    "
	                  >
	                    {{ bindQrcodeError ? '绑定二维码生成失败' : '正在生成绑定二维码…' }}
	                  </div>
	                </div>
	              </a-spin>
	              <div v-if="bindQrcodeError" style="margin-top: 10px; color: var(--color-text-3); font-size: 12px;">
	                {{ bindQrcodeError }}（可先使用下方绑定码手动绑定）
	              </div>
	              <div v-else style="margin-top: 10px; color: var(--color-text-2); font-size: 13px;">
	                扫码关注（或已关注直接扫码）即可自动绑定
	              </div>
	            </template>
	          </div>

          <div style="max-width: 520px; margin: 18px auto 0; text-align: left;">
            <div v-if="bindingLoading" style="text-align: center; padding: 10px 0;">
              <a-spin size="large" />
            </div>

            <template v-else>
              <a-alert v-if="wechatBinding.is_bound" type="success" show-icon>
                已绑定（{{ wechatBinding.wechat_openid_masked || '已完成' }}），后续将按你的订阅发送每日精选与摘要。
              </a-alert>

	              <template v-else>
	                <a-alert type="info" show-icon>
	                  绑定步骤：扫码上方二维码关注/扫码 → 自动绑定 → 点击“刷新绑定状态”确认。
	                  如扫码失败，可把下方“绑定码”发给公众号完成绑定。
	                </a-alert>

                <div
                  style="
                    margin-top: 12px;
                    padding: 12px 14px;
                    border-radius: 14px;
                    border: 1px solid var(--color-border-2);
                    background: var(--color-bg-2);
                  "
                >
	                  <div style="display: flex; align-items: center; justify-content: space-between; gap: 10px;">
	                    <div style="text-align: left;">
	                      <div style="font-size: 12px; color: var(--color-text-3);">绑定码（备用）</div>
                      <div
                        style="
                          font-size: 20px;
                          font-weight: 650;
                          letter-spacing: 0.06em;
                          font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
                        "
                      >
                        {{ bindCodeText }}
                      </div>
                      <div v-if="bindCodeExpiresText" style="margin-top: 4px; font-size: 12px; color: var(--color-text-3);">
                        {{ bindCodeExpiresText }}
                      </div>
                    </div>

                    <a-space>
                      <a-button size="small" :loading="codeLoading" @click="copyBindCode" :disabled="!bindCodeText || bindCodeText === '-'">
                        复制
                      </a-button>
                      <a-button size="small" :loading="codeLoading" @click="generateBindCode(true)">
                        重新生成
                      </a-button>
                    </a-space>
                  </div>
                </div>
              </template>

              <div style="margin-top: 14px; text-align: center;">
                <a-space>
                  <a-button type="primary" :loading="bindingLoading" @click="refreshBinding">刷新绑定状态</a-button>
                  <a-button @click="dismissPromo">关闭</a-button>
                </a-space>
              </div>
            </template>
          </div>
        </div>
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
</template>

<script setup lang="ts">
import { computed, onMounted, provide, ref, watch } from 'vue'
	import { useRoute, useRouter } from 'vue-router'
	import { Message } from '@arco-design/web-vue'
	import { getCurrentUser, logout } from '@/api/auth'
	import { getSysInfo } from '@/api/sysInfo'
	import { createWechatBindCode, getWechatBindQrcode, getWechatBinding, type WechatBindCode, type WechatBindQrcodeInfo, type WechatBindingInfo } from '@/api/binding'
	import Navbar from '@/components/Layout/Navbar.vue'
	import WechatAuthQrcode from '@/components/WechatAuthQrcode.vue'
	import { initBrowserNotification } from '@/utils/browserNotification'
import { translatePage, setCurrentLanguage } from '@/utils/translate'
import { getThemeMode, setThemeMode, type ThemeMode } from '@/utils/theme'
import lemonIcon from '@/assets/lemon.svg'

const languageOptions = [
  { value: '', label: '语言：禁用' },
  { value: 'chinese_simplified', label: '语言：简体中文' },
  { value: 'english', label: '语言：English' },
]

const currentLanguage = ref(localStorage.getItem('language') || 'chinese_simplified')
const handleLanguageChange = (language: string) => {
  setCurrentLanguage(language)
  currentLanguage.value = language
}

const themeMode = ref<ThemeMode>(getThemeMode())
const handleThemeChange = (mode: ThemeMode) => {
  themeMode.value = mode
  setThemeMode(mode)
}
watch(themeMode, (m) => setThemeMode(m))

const PROMO_SEEN_KEY = 'promo_lemon_doctor_seen_v1'
const promoVisible = ref(false)
const promoQrSrc = computed(() => `/api/v1/wx/sys/promo/qr?v=1`)
const promoQrError = ref(false)

	const bindingLoading = ref(false)
	const codeLoading = ref(false)
	const wechatBinding = ref<WechatBindingInfo>({
	  user_id: '',
	  is_bound: false,
	  wechat_openid_masked: '',
	  wechat_unionid_masked: '',
	  bind_code: null,
	})

	const bindQrcodeLoading = ref(false)
	const bindQrcodeImgError = ref(false)
	const bindQrcodeError = ref('')
	const bindQrcode = ref<WechatBindQrcodeInfo>({})
	const bindQrcodeUrl = computed(() => bindQrcode.value?.qrcode_url || '')

const bindCodeText = computed(() => wechatBinding.value?.bind_code?.code || '-')
const bindCodeExpiresText = computed(() => {
  const c = wechatBinding.value?.bind_code
  if (c?.expires_in === undefined || c?.expires_in === null) return ''
  const mins = Math.max(0, Math.floor((c.expires_in || 0) / 60))
  return `有效期：约 ${mins} 分钟`
})

	const refreshBinding = async () => {
	  try {
	    bindingLoading.value = true
	    const data = await getWechatBinding()
	    wechatBinding.value = data
	  } catch (e: any) {
	    Message.error(e || '获取绑定状态失败')
	  } finally {
	    bindingLoading.value = false
	  }
	}

	const refreshBindQrcode = async () => {
	  if (wechatBinding.value?.is_bound) return
	  bindQrcodeError.value = ''
	  bindQrcodeImgError.value = false
	  try {
	    bindQrcodeLoading.value = true
	    const data = await getWechatBindQrcode()
	    bindQrcode.value = data || {}
	    if ((data as any)?.bind_code?.code) {
	      wechatBinding.value = { ...(wechatBinding.value as any), bind_code: (data as any).bind_code }
	    }
	  } catch (e: any) {
	    bindQrcode.value = {}
	    bindQrcodeError.value = e || '生成绑定二维码失败'
	  } finally {
	    bindQrcodeLoading.value = false
	  }
	}

	const generateBindCode = async (force = false) => {
	  try {
	    codeLoading.value = true
	    const code: WechatBindCode = await createWechatBindCode(force)
	    wechatBinding.value = {
	      ...(wechatBinding.value as any),
	      bind_code: code,
	    }
	    if (!wechatBinding.value?.is_bound) {
	      refreshBindQrcode()
	    }
	  } catch (e: any) {
	    Message.error(e || '生成绑定码失败')
	  } finally {
	    codeLoading.value = false
	  }
	}

const copyBindCode = async () => {
  const code = bindCodeText.value
  if (!code || code === '-') return
  try {
    await navigator.clipboard.writeText(code)
    Message.success('已复制绑定码')
  } catch {
    try {
      const el = document.createElement('textarea')
      el.value = code
      el.style.position = 'fixed'
      el.style.left = '-9999px'
      document.body.appendChild(el)
      el.focus()
      el.select()
      document.execCommand('copy')
      document.body.removeChild(el)
      Message.success('已复制绑定码')
    } catch {
      Message.error('复制失败，请手动复制')
    }
  }
}

	const showPromoModal = (e?: Event) => {
	  if (e) e.preventDefault()
	  promoQrError.value = false
	  bindQrcodeError.value = ''
	  bindQrcodeImgError.value = false
	  promoVisible.value = true
	  refreshBinding().then(() => {
	    if (!wechatBinding.value?.is_bound) {
	      refreshBindQrcode().then(() => {
	        if (!wechatBinding.value?.bind_code?.code) generateBindCode(false)
	      })
	    }
	  })
	}

const dismissPromo = () => {
  promoVisible.value = false
  localStorage.setItem(PROMO_SEEN_KEY, '1')
}

const qrcodeRef = ref()
const showAuthQrcode = () => {
  qrcodeRef.value?.startAuth()
}
provide('showAuthQrcode', showAuthQrcode)

const appTitle = computed(() => import.meta.env.VITE_APP_TITLE || 'Dr.Lemon订阅助手')
const logo = lemonIcon
const router = useRouter()
const route = useRoute()

const userInfo = ref({ username: '', avatar: '' })
const haswxLogined = ref(true)
const hasLogined = ref(false)
const isAuthenticated = computed(() => {
  hasLogined.value = !!localStorage.getItem('token')
  return hasLogined.value
})

const fetchUserInfo = async () => {
  try {
    const res = await getCurrentUser()
    userInfo.value = res
  } catch (error) {
    console.error('获取用户信息失败', error)
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

const goToEditUser = () => router.push({ name: 'EditUser' })
const goToChangePassword = () => router.push({ name: 'ChangePassword' })

const handleLogout = async () => {
  try {
    await logout()
    localStorage.removeItem('token')
    router.push('/login')
  } catch {
    Message.error('退出登录失败')
  }
}

	onMounted(() => {
	  if (isAuthenticated.value) fetchUserInfo()
	  initBrowserNotification()
	  translatePage()
	  fetchSysInfo()

	  if (isAuthenticated.value && !localStorage.getItem(PROMO_SEEN_KEY)) {
	    showPromoModal()
	  }
	})

watch(
  () => route.path,
  () => {
    hasLogined.value = !!localStorage.getItem('token')
	    if (hasLogined.value) {
	      fetchUserInfo()
	      if (!localStorage.getItem(PROMO_SEEN_KEY)) showPromoModal()
	    }
	  }
	)
</script>

<style scoped>
.app-container {
  min-height: 100vh;
}

.app-header {
  padding: 0 8px;
  height: var(--app-header-height);
  position: sticky;
  top: 0;
  z-index: 100;
  background: color-mix(in srgb, var(--color-bg-2) 92%, transparent);
  backdrop-filter: saturate(180%) blur(14px);
  border-bottom: 1px solid var(--color-border);
}

.header-inner {
  width: 100%;
  height: 100%;
  display: flex;
  align-items: center;
  gap: 14px;
}

.brand {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
}

.brand-logo {
  width: 28px;
  height: 28px;
  border-radius: 8px;
}

.brand-title {
  font-size: 14px;
  font-weight: 700;
  letter-spacing: -0.2px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  color: var(--color-text-1);
}

.brand-title:hover {
  text-decoration: none;
}

.brand-scan {
  cursor: pointer;
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
  gap: 10px;
  flex: 0 0 auto;
}

.theme-select,
.lang-select {
  width: 132px;
}

.header-actions :deep(.arco-select-view) {
  border-radius: 999px;
  background: color-mix(in srgb, var(--color-bg-2) 86%, transparent);
  color: var(--color-text-1);
}

.header-actions :deep(.arco-select-view-input),
.header-actions :deep(.arco-select-view-value) {
  color: var(--color-text-1);
}

.header-actions :deep(.arco-select-view-placeholder) {
  color: var(--color-text-3);
}

.header-actions :deep(.arco-select-view-icon) {
  color: var(--color-text-2);
}

.promo-btn :deep(.arco-btn) {
  border-radius: 999px;
  color: var(--lemon-accent, var(--color-warning-6));
}

.promo-btn :deep(.arco-btn:hover) {
  background: color-mix(in srgb, var(--lemon-accent, var(--color-warning-6)) 14%, transparent);
}

.user-pill {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 4px 10px;
  border-radius: 999px;
  border: 1px solid var(--color-border);
  background: color-mix(in srgb, var(--color-bg-2) 86%, transparent);
  cursor: pointer;
}

.username {
  font-size: 13px;
  color: var(--color-text-1);
}

.app-content {
  background: var(--color-bg-1);
  min-height: calc(100vh - var(--app-header-height));
}

@media (max-width: 720px) {
  .header-actions {
    display: none !important;
  }
}
</style>
