<template>
  <div class="login-container">
    <a-card class="login-card" :bordered="false">
      <template #title>
        <div class="login-title">
          <h2>{{ appTitle }}</h2>
        </div>
      </template>
      
      <a-form :model="form" @submit="handleSubmit">
        <a-form-item field="username" label="用户名">
          <a-input v-model="form.username" placeholder="请输入用户名">
            <template #prefix><icon-user /></template>
          </a-input>
        </a-form-item>
        
        <a-form-item field="password" label="密码">
          <a-input-password v-model="form.password" placeholder="请输入密码">
            <template #prefix><icon-lock /></template>
          </a-input-password>
        </a-form-item>
        
        <a-form-item>
          <a-button type="primary" html-type="submit" :loading="loading" long>
            登录
          </a-button>
        </a-form-item>
      </a-form>
    </a-card>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { useRouter } from 'vue-router'
import { Message } from '@arco-design/web-vue'
import { login } from '@/api/auth'

const appTitle = computed(() => import.meta.env.VITE_APP_LOGIN_TITLE || '登录')

const router = useRouter()
const loading = ref(false)
const form = ref({
  username: '',
  password: ''
})

const handleSubmit = async () => {
  loading.value = true
  try {
    // 使用URLSearchParams格式发送请求
    const formData = new URLSearchParams()
    formData.append('username', form.value.username)
    formData.append('password', form.value.password)
    
    const res = await login({
      username: form.value.username,
      password: form.value.password
    })
    
    if (res.access_token) {
      // 存储token和过期时间
      localStorage.setItem('token', res.access_token)
      localStorage.setItem('token_expire', 
        Date.now() + (res.expires_in * 1000))
      
      // 处理重定向
      const redirect = router.currentRoute.value.query.redirect
      await router.push(redirect ? redirect.toString() : '/')
      Message.success('登录成功')
    } else {
      throw new Error('无效的响应格式')
    }
  } catch (error) {
    console.error('登录错误:', error)
    const errorMsg = error.response?.data?.detail || 
                    error.response?.data?.message || 
                    error.message || 
                    '登录失败，请检查用户名和密码'
    Message.error(errorMsg)
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.login-container {
  display: flex;
  justify-content: center;
  align-items: center;
  height: 80vh;
}

.login-card {
  width: 400px;
  border-radius: 8px;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
}

.login-title {
  text-align: center;
}

.logo {
  width: 60px;
  height: 60px;
  margin-bottom: 16px;
}
</style>