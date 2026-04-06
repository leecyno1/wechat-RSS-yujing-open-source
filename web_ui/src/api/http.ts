import axios from 'axios'
import { clearAuthSession, getToken } from '@/utils/auth'
import { notifyError } from '@/utils/notify'
import router from '@/router'

const normalizeValidationText = (msg: string): string => {
  const text = String(msg || '').trim()
  if (!text) return ''
  let m = text.match(/Input should be less than or equal to (\d+)/i)
  if (m) return `输入值不能大于 ${m[1]}`
  m = text.match(/Input should be greater than or equal to (\d+)/i)
  if (m) return `输入值不能小于 ${m[1]}`
  m = text.match(/String should have at most (\d+) characters?/i)
  if (m) return `文本长度不能超过 ${m[1]} 个字符`
  m = text.match(/String should have at least (\d+) characters?/i)
  if (m) return `文本长度不能少于 ${m[1]} 个字符`
  if (/Field required/i.test(text)) return '缺少必填字段'
  return text
}

const extractErrorMessage = (raw: any): string => {
  if (typeof raw === 'string') return normalizeValidationText(raw)
  if (raw == null) return ''
  if (typeof raw === 'number' || typeof raw === 'boolean') return String(raw)
  if (Array.isArray(raw)) {
    return raw.map((x) => extractErrorMessage(x)).filter(Boolean).join('；')
  }
  const errList = raw?.data?.errors || raw?.detail?.errors || raw?.errors
  if (Array.isArray(errList) && errList.length > 0) {
    const first = errList[0] || {}
    const field = String(first?.field || '').trim()
    const msg = normalizeValidationText(String(first?.message || first?.msg || first || '').trim())
    if (field && msg) return `${field}: ${msg}`
    if (msg) return msg
  }
  const msg = raw?.message || raw?.msg || raw?.error || raw?.detail?.message || raw?.detail
  if (typeof msg === 'string') return msg
  if (msg && typeof msg === 'object') return extractErrorMessage(msg)
  return ''
}

const shouldSuppressValidationToast = (msg: string): boolean => {
  const text = String(msg || '')
  if (!text) return false
  return /Input should be less than or equal to \d+/i.test(text)
    || /Input should be greater than or equal to \d+/i.test(text)
    || /String should have at most \d+ characters?/i.test(text)
    || /String should have at least \d+ characters?/i.test(text)
}
// 创建axios实例
const http = axios.create({
  baseURL: (import.meta.env.VITE_API_BASE_URL || '') + 'api/v1/',
  timeout: 100000,
  headers: {
    'Content-Type': 'application/json',
    'Accept': 'application/json'
  }
})

// 请求拦截器
http.interceptors.request.use(
  config => {
    const token = getToken()
    if (token) {
      config.headers['Authorization'] = `Bearer ${token}`
    }
    return config
  },
  error => {
    return Promise.reject(error)
  }
)

// 响应拦截器
http.interceptors.response.use(
  response => {
    const silentError = Boolean((response.config as any)?.silentError)
    // 处理标准响应格式
    if (response.data?.code === 0) {
      return response.data?.data||response.data?.detail||response.data||response
    }
    if(response.data?.code==401){
      clearAuthSession()
      const redirect = String(router.currentRoute.value?.fullPath || '/channels')
      router.push({ path: '/channels', query: { auth: '1', tab: 'login', redirect } })
      return Promise.reject("未登录或登录已过期，请重新登录。")
    }
    const data=response.data?.detail||response.data
    const errorMsg = extractErrorMessage(data) || '请求失败'
    const suppressToast = shouldSuppressValidationToast(errorMsg)
    const contentType = String(response.headers['content-type'] || '')
    if(contentType.includes('application/json')) {
      if (!silentError && !suppressToast) notifyError(errorMsg, { dedupeKey: `http:${errorMsg}` })
    }else{
      return response.data
    }
    return Promise.reject(errorMsg)
  },
  error => {
     const silentError = Boolean((error?.config as any)?.silentError)
     const statusCode = Number(error?.response?.status || error?.status || 0)
     if(statusCode === 401){
      clearAuthSession()
      const redirect = String(router.currentRoute.value?.fullPath || '/channels')
      router.push({ path: '/channels', query: { auth: '1', tab: 'login', redirect } })
    }
    // console.log(error)
    // 统一错误处理
     const errorMsg =extractErrorMessage(error?.response?.data) || extractErrorMessage(error) || '请求错误'
    const suppressToast = shouldSuppressValidationToast(errorMsg)
    if (!silentError && !suppressToast) notifyError(errorMsg, { dedupeKey: `http:${errorMsg}` })
    return Promise.reject(errorMsg)
  }
)

export default http
