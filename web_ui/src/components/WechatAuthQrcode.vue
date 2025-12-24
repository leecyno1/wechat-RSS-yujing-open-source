<template>
  <a-modal
    v-model:visible="visible"
    title="微信授权"
    :footer="false"
    :mask-closable="false"
    width="400px"
    @cancel="clearTimer"
  >
    <div class="qrcode-container">
      <div v-if="loading" class="loading">
        <a-spin size="large" />
        <p>正在获取二维码...</p>
      </div>
      <div v-else-if="qrcodeUrl" class="qrcode" style="text-align:center;">
        <img :src="qrcodeUrl" alt="微信授权二维码" />
        <a-tooltip content="扫码请选择公众号或者服务号，如果没有帐号，请点击下方注册" placement="top">
        <p>请使用微信扫码授权（{{ countdown }}s）</p>
        </a-tooltip>
        <a-space>
          <a-button size="small" @click="refreshQrcode" :loading="loading">刷新二维码</a-button>
        </a-space>
        <p>如果提示没有可用帐号码，请点此
          <a-tooltip content="注册时请选择公众号或者服务号" placement="top">
          <a-link href="https://mp.weixin.qq.com/cgi-bin/registermidpage?action=index&weblogo=1&lang=zh_CN" target="_blank">注册</a-link><br/>
          </a-tooltip>
        </p>
      </div>
      <div v-else class="error">
        <a-alert type="error" :message="errorMessage" />
        <a-button type="primary" @click="startAuth">重试</a-button>
      </div>
    </div>
  </a-modal>
</template>

<script lang="ts" setup>
import { ref } from 'vue'
import { QRCode, getQRCodeStatusOnce } from '@/api/auth'
import { Message } from '@arco-design/web-vue'

const emit = defineEmits(['success', 'error'])

const visible = ref(false)
const loading = ref(false)
const qrcodeUrl = ref('')
const errorMessage = ref('')
const countdown = ref(0)

let checkStatusTimer: number | null = null
let countdownTimer: number | null = null

const startAuth = async () => {
  try {
    visible.value = true
    loading.value = true
    errorMessage.value = ''
    
    // 获取二维码
    const res: any = await QRCode()
    qrcodeUrl.value = res?.code || ''
    loading.value = false

    // countdown & auto refresh
    countdown.value = Number(res?.expires_in || 120)
    if (countdownTimer) clearInterval(countdownTimer)
    countdownTimer = window.setInterval(() => {
      countdown.value = Math.max(0, countdown.value - 1)
      if (countdown.value === 0) {
        refreshQrcode()
      }
    }, 1000)

    // polling status
    if (checkStatusTimer) clearInterval(checkStatusTimer)
    checkStatusTimer = window.setInterval(async () => {
      try {
        const statusRes: any = await getQRCodeStatusOnce()
        if (statusRes?.login_status) {
          clearTimer()
          emit('success', statusRes)
          visible.value = false
        }
      } catch (err) {
        // ignore transient errors
      }
    }, 3000)
  } catch (err) {
    loading.value = false
    errorMessage.value = '获取二维码失败，请重试'
    emit('error', err)
  }
}

const refreshQrcode = async () => {
  if (loading.value) return
  try {
    loading.value = true
    const res: any = await QRCode()
    qrcodeUrl.value = res?.code || ''
    countdown.value = Number(res?.expires_in || 120)
  } catch (err) {
    Message.error('刷新二维码失败')
  } finally {
    loading.value = false
  }
}

const clearTimer = () => {
  if (checkStatusTimer) {
    clearInterval(checkStatusTimer)
    checkStatusTimer = null
  }
  if (countdownTimer) {
    clearInterval(countdownTimer)
    countdownTimer = null
  }
}

defineExpose({
  startAuth
})
</script>

<style scoped>
.qrcode-container {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 20px;
}

.loading,
.qrcode,
.error {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 16px;
}

.qrcode img {
  width: 200px;
  height: 200px;
}
</style>
