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
            action="/api/upload"
            :file-list="fileList"
            @change="handleUploadChange"
            :show-file-list="false"
          >
            <template #upload-button>
              <div class="avatar-upload">
                <a-avatar :size="80">
                  <img v-if="form.avatar" :src="form.avatar" alt="avatar">
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
import { getUserInfo, updateUserInfo } from '@/api/user'

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

const handleUploadChange = async (file: any) => {
  try {
    const formData = new FormData()
    formData.append('file', file.file)
    const res = await uploadAvatar(formData)
    form.value.avatar = res.url
    Message.success('头像上传成功')
  } catch (error) {
    Message.error('头像上传失败')
  }
}

const fetchUserInfo = async () => {
  try {
    const res = await getUserInfo()
    form.value = {
      username: res.username,
      nickname: res.nickname,
      email: res.email,
      avatar: res.avatar
    }
  } catch (error) {
    Message.error('获取用户信息失败')
  }
}

const handleSubmit = async () => {
  loading.value = true
  try {
    await updateUserInfo(form.value)
    Message.success('信息更新成功')
  } catch (error) {
    Message.error('信息更新失败')
  } finally {
    loading.value = false
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