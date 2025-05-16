<template>
  <div class="login-container">
    <a-card class="login-card" :bordered="false">
      <template #title>
        <div class="login-title">
          <h2>微信公众号订阅助手</h2>
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
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { Message } from '@arco-design/web-vue'
import { login } from '@/api/auth'

const router = useRouter()
const loading = ref(false)
const form = ref({
  username: '',
  password: ''
})

const handleSubmit = async () => {
  loading.value = true
  try {
    try {
      const res = await login(form.value)
      console.log('登录响应:', res)
      
      // 存储token
      localStorage.setItem('token', res.access_token)
      console.log('Token已存储:', localStorage.getItem('token'))
      
      // 检查存储配额
      console.log('Storage剩余空间:', JSON.stringify(localStorage).length / 1024 + 'KB')
    } catch (error) {
      console.error('存储失败:', error)
      Message.error('登录状态保存失败: ' + error.message)
    }
    
    // 处理登录后重定向
    const redirect = router.currentRoute.value.query.redirect
    console.log('重定向目标:', redirect)
    await router.push(redirect ? redirect.toString() : '/')
    console.log('跳转完成')
  } catch (error) {
    console.log(error)
    Message.error('登录失败，请检查用户名和密码')
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
  height: 100vh;
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