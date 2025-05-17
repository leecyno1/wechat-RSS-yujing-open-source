import axios from 'axios'
import { getToken } from '@/utils/auth'

// 创建axios实例
const http = axios.create({
  baseURL: (import.meta.env.VITE_API_BASE_URL || '') + 'api/v1/',
  timeout: 10000,
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
    // 处理标准响应格式
    if (response.data?.code === 0) {
      return response.data.data||response.data.detail
    }
    console.log(response.data.data||response.data.detail)
    const errorMsg = response.data?.message || '请求失败'
    // Message.error(errorMsg)
    return Promise.reject(response.data)
  },
  error => {
    // 统一错误处理
    const errorMsg = error.response?.data?.message || 
                    error.response?.data?.detail || 
                    error.message || 
                    '请求错误'
    // Message.error(errorMsg)
    return Promise.reject(errorMsg)
  }
)

export default http