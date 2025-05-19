<template>
  <div class="edit-user">
    <a-page-header
      title="修改个人信息"
      subtitle="更新您的账户信息"
      :show-back="true"
      @back="goBack"
    />
    
    <a-card>
      <a-form
        :model="form"
        :rules="rules"
        @submit="handleSubmit"
        layout="vertical"
      >
        <a-form-item label="头像">
          <a-upload
            :custom-request="handleUploadChange"
            :file-list="fileList"
            :show-file-list="false"
            accept="image/*"
            :limit="1"
            :max-size="2048"
            @exceed="handleExceed"
            @error="handleUploadError"
          >
            <template #upload-button>
              <div class="avatar-upload">
                <a-avatar :size="80">
                  <img 
                    v-if="form.avatar" 
                    :src="form.avatar" 
                    alt="avatar"
                    @error="handleImageError"
                  >
                  <icon-user v-else />
                </a-avatar>
                <div class="upload-mask">
                  <icon-edit />
                </div>
              </div>
            </template>
          </a-upload>
        </a-form-item>
        
        <a-form-item label="用户名" field="username">
          <a-input
            v-model="form.username"
            placeholder="请输入用户名"
            allow-clear
          >
            <template #prefix><icon-user /></template>
          </a-input>
        </a-form-item>
        
        <a-form-item label="昵称" field="nickname">
          <a-input
            v-model="form.nickname"
            placeholder="请输入昵称"
            allow-clear
          >
            <template #prefix><icon-user /></template>
          </a-input>
        </a-form-item>
        
        <a-form-item label="邮箱" field="email">
          <a-input
            v-model="form.email"
            placeholder="请输入邮箱"
            allow-clear
          >
            <template #prefix><icon-email /></template>
          </a-input>
        </a-form-item>
        
        <a-form-item>
          <a-space>
            <a-button type="primary" html-type="submit" :loading="loading">
              保存修改
            </a-button>
            <a-button @click="resetForm">重置</a-button>
          </a-space>
        </a-form-item>
      </a-form>
    </a-card>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { Message } from '@arco-design/web-vue'
import { getUserInfo, updateUserInfo, uploadAvatar } from '@/api/user'

const router = useRouter()
const loading = ref(false)
const fileList = ref([])

const form = ref({
  username: '',
  nickname: '',
  email: '',
  avatar: ''
})

const rules = {
  username: [{ required: true, message: '请输入用户名' }],
  email: [
    { required: true, message: '请输入邮箱' },
    { type: 'email', message: '请输入有效的邮箱地址' }
  ]
}

const handleUploadChange = async (options: any) => {
  const { file } = options
  
  // 文件类型验证
  if (!file.file.type.startsWith('image/')) {
    Message.error('请选择图片文件 (JPEG/PNG)')
    return
  }

  // 文件大小验证 (2MB)
  if (file.file.size > 2 * 1024 * 1024) {
    Message.error('图片大小不能超过2MB')
    return
  }

  try {
    Message.loading('正在上传头像...')
    const formData = new FormData()
    formData.append('avatar', file.file)
    const res = await uploadAvatar(formData)
    form.value.avatar = res.data.avatar
    Message.success('头像上传成功')
  } catch (error) {
    console.error('上传错误:', error)
    Message.error(`上传失败: ${error.response?.data?.message || error.message || '服务器错误'}`)
  } finally {
    Message.clear()
  }
}

const handleExceed = () => {
  Message.warning('只能上传一个头像文件')
}

const handleUploadError = (error: Error) => {
  Message.error(`上传出错: ${error.message || '文件上传失败'}`)
}

const handleImageError = (e: Event) => {
  const img = e.target as HTMLImageElement
  img.src = '/vite.svg'
}

const fetchUserInfo = async () => {
  loading.value = true
  try {
    const res = await getUserInfo()
    console.log('用户信息响应:', res) // 调试日志
    console.log('用户信息:', res)
    form.value = {
      username: res.username,
      nickname: res.nickname || res.username,
      email: res.email || '',
      avatar: res.avatar 
        ? (res.avatar.startsWith('http') 
            ? res.avatar 
            : `${import.meta.env.VITE_API_BASE_URL}${res.avatar}`)
        : `${import.meta.env.VITE_API_BASE_URL}/static/default-avatar.png`
    }
    console.log('表单数据:', form.value)
    console.log('表单数据:', form.value) // 调试日志
  } catch (error) {
    Message.error(`获取用户信息失败: ${error.message || '未知错误'}`)
    router.push('/login')
  } finally {
    loading.value = false
  }
}

const handleSubmit = async () => {
  loading.value = true
  try {
    Message.loading('正在更新信息...')
    await updateUserInfo(form.value)
    Message.success('信息更新成功')
    // 更新本地用户信息
    const res = await getUserInfo()
    form.value = {
      username: res.data.username,
      nickname: res.data.nickname || '',
      email: res.data.email || '',
      avatar: res.data.avatar || ''
    }
  } catch (error) {
    console.error('更新错误:', error)
    Message.error(`更新失败: ${error.response?.data?.message || error.message || '服务器错误'}`)
  } finally {
    loading.value = false
    Message.clear()
  }
}

const resetForm = () => {
  fetchUserInfo()
}

const goBack = () => {
  router.go(-1)
}

onMounted(() => {
  fetchUserInfo()
})
</script>

<style scoped>
.edit-user {
  padding: 20px;
  max-width: 600px;
  margin: 0 auto;
}

.avatar-upload {
  position: relative;
  width: 80px;
  height: 80px;
  cursor: pointer;
}

.upload-mask {
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  background-color: rgba(0, 0, 0, 0.5);
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  opacity: 0;
  transition: opacity 0.3s;
}

.avatar-upload:hover .upload-mask {
  opacity: 1;
}

.arco-form-item {
  margin-bottom: 20px;
}
</style>