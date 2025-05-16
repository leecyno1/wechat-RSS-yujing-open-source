import axios from 'axios'
import { Message } from '@arco-design/web-vue'

const service = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || '/api',
  timeout: 10000
})

// 请求拦截器
service.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem('token')
    if (token) {
      config.headers.Authorization = `Bearer ${token}`
    }
    return config
  },
  (error) => {
    return Promise.reject(error)
  }
)

// 响应拦截器
service.interceptors.response.use(
  (response) => {
    if (response.status !== 200) {
      Message.error('请求失败')
      return Promise.reject(new Error('请求失败'))
    }
    const res = response.data
    return res
  },
  (error) => {
    Message.error(error.message || '请求失败')
    return Promise.reject(error)
  }
)

export default service