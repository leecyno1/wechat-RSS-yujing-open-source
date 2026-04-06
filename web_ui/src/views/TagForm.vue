<script setup lang="ts">
import { computed, ref, onMounted, nextTick } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { getTag, createTag, updateTag } from '@/api/tagManagement'
import type { TagCreate } from '@/types/tagManagement'
import { notifyError, notifySuccess, notifyWarning } from '@/utils/notify'
import { uploadFile } from '@/api/file'
import FeedMultiSelect from '@/components/FeedMultiSelect.vue'
import { CHANNEL_LOGO_PRESETS, pickDefaultChannelLogo } from '@/constants/channelLogos'

const route = useRoute()
const router = useRouter()
const isEdit = ref(false)
const loading = ref(false)
const formLoading = ref(false)

const formModel = ref<TagCreate>({
  name: '',
  cover: null,
  intro: null,
  status: 1,
  mps_id: []
})

const rules = {
  name: [{ required: true, message: '请输入频道名称' }]
}

const fetchTag = async (id: string) => {
  try {
    loading.value = true
    const res: any = await getTag(id)
    let parsedMps: any[] = []
    try {
      parsedMps = JSON.parse(String(res?.mps_id || '[]'))
      if (!Array.isArray(parsedMps)) parsedMps = []
    } catch {
      parsedMps = []
    }
    formModel.value = {
      ...res,
      mps_id: parsedMps,
    }
    // 初始化选择器数据
    nextTick(() => {
      if (feedSelectorRef.value) {
        feedSelectorRef.value.parseSelected(formModel.value.mps_id as any[])
      }
    })
  } catch (error) {
    notifyError('获取频道详情失败')
  } finally {
    loading.value = false
  }
}

const handleUploadChange = async (options: any) => {
  const file = options.fileItem?.file || options.file
  
  // 文件类型验证
  if (!file?.type?.startsWith('image/')) {
    notifyWarning('请选择图片文件 (JPEG/PNG)')
    return
  }

  // 文件大小验证 (2MB)
  if (file.size > 2 * 1024 * 1024) {
    notifyWarning('图片大小不能超过2MB')
    return
  }

  try {
    const res = await uploadFile(file)
    console.log(res)
    formModel.value.cover = res.url
  } catch (error) {
    console.error('上传错误:', error)
    notifyError(`上传失败: ${(error as any)?.response?.data?.message || (error as any)?.message || '服务器错误'}`)
  } 
  return false
}

const handleExceed = () => {
  notifyWarning('只能上传一个封面文件')
}

const handleUploadError = (error: Error) => {
  notifyError(`上传出错: ${error.message || '文件上传失败'}`)
}

const showFeedSelector = ref(false)
const feedSelectorRef = ref<InstanceType<typeof FeedMultiSelect> | null>(null)

const selectedCount = computed(() => {
  const list: any[] = Array.isArray(formModel.value.mps_id) ? (formModel.value.mps_id as any[]) : []
  return list.length
})

const selectedSummary = computed(() => {
  const list: any[] = Array.isArray(formModel.value.mps_id) ? (formModel.value.mps_id as any[]) : []
  return list.map((x: any) => String(x?.mp_name || x?.name || x?.id || '')).filter(Boolean).slice(0, 3).join('、')
})

const handleImageError = (e: Event) => {
  const img = e.target as HTMLImageElement
  img.src = '/default-cover.png'
}

const applyLogoPreset = (cover: string) => {
  formModel.value.cover = cover
}

const quickSelectAllSubscribed = () => {
  showFeedSelector.value = true
  nextTick(() => {
    feedSelectorRef.value?.selectAllSubscribed?.()
  })
}

const handleSubmit = async () => {
  try {
    formLoading.value = true
    const list: any[] = Array.isArray(formModel.value.mps_id) ? (formModel.value.mps_id as any[]) : []
    if (!list.length) {
      notifyWarning('请至少选择一个订阅项')
      return
    }
    if (!String(formModel.value.cover || '').trim()) {
      formModel.value.cover = pickDefaultChannelLogo(String(formModel.value.name || ''))
    }
    // 将mps_id转换为字符串
    const submitData = {
      ...formModel.value,
      mps_id: JSON.stringify(formModel.value.mps_id)
    }
    
    if (isEdit.value) {
      await updateTag(route.params.id as string,submitData)
      notifySuccess('更新成功')
    } else {
      await createTag(submitData)
      notifySuccess('创建成功')
    }
    router.push('/manage/topics')
  } catch (error) {
    notifyError(isEdit.value ? '更新失败' : '创建失败')
  } finally {
    formLoading.value = false
  }
}

onMounted(() => {
  if (route.params.id) {
    isEdit.value = true
    fetchTag(route.params.id as string)
  }
})
</script>

<template>
  <div class="tag-form">
    <a-page-header
      :title="isEdit ? '编辑频道' : '添加频道'"
      subtitle="频道信息"
      @back="router.go(-1)"
    />

    <a-card :loading="loading">
      <a-form
        :model="formModel"
        :rules="rules"
        layout="vertical"
        @submit="handleSubmit"
      >
        <a-form-item label="频道名称" field="name">
          <a-input v-model="formModel.name" placeholder="请输入频道名称" />
        </a-form-item>

        <a-form-item label="封面图" field="cover">
          <a-upload
            :custom-request="handleUploadChange"
            :show-file-list="false"
            accept="image/*"
            :limit="1"
            :max-size="2048"
            @exceed="handleExceed"
            @error="handleUploadError"
          >
            <template #upload-button>
              <div class="cover-upload">
                <img 
                  v-if="formModel.cover" 
                  :src="formModel.cover" 
                  alt="cover"
                  @error="handleImageError"
                />
                <icon-image v-else />
                <div class="upload-mask">
                  <icon-edit />
                </div>
              </div>
            </template>
          </a-upload>
          <div class="logo-presets">
            <div class="logo-presets-title">默认 Logo（点击套用）</div>
            <div class="logo-presets-grid">
              <button
                v-for="logo in CHANNEL_LOGO_PRESETS"
                :key="logo.id"
                class="logo-item"
                type="button"
                @click="applyLogoPreset(logo.cover)"
              >
                <img :src="logo.cover" :alt="logo.name" />
                <span>{{ logo.name }}</span>
              </button>
            </div>
          </div>
        </a-form-item>

        <a-form-item label="简介" field="intro">
          <a-textarea
            v-model="formModel.intro"
            placeholder="请输入频道简介"
            :auto-size="{ minRows: 3 }"
          />
        </a-form-item>

        <a-form-item label="状态" field="status">
          <a-switch
            v-model="formModel.status"
            :checked-value="1"
            :unchecked-value="0"
          />
        </a-form-item>

        <a-form-item label="订阅项" field="mps_id">
          <a-space>
            <a-input
              :model-value="selectedCount ? `已选 ${selectedCount} 项${selectedSummary ? `（${selectedSummary}${selectedCount > 3 ? '…' : ''}）` : ''}` : ''"
              placeholder="请选择订阅项"
              readonly
              style="width: 420px"
            />
            <a-button @click="showFeedSelector = true">选择</a-button>
            <a-button type="outline" @click="quickSelectAllSubscribed">
              全选已添加订阅
            </a-button>
          </a-space>
        </a-form-item>

        <a-form-item>
          <a-space>
            <a-button type="primary" html-type="submit" :loading="formLoading">
              提交
            </a-button>
            <a-button @click="router.go(-1)">取消</a-button>
          </a-space>
        </a-form-item>
      </a-form>
    </a-card>
  </div>
  <!-- 订阅项选择器模态框 -->
<a-modal
  v-model:visible="showFeedSelector"
  title="选择订阅项"
  :footer="false"
  width="960px"
>
  <FeedMultiSelect
    ref="feedSelectorRef"
    v-model="formModel.mps_id"
  />
  <template #footer>
    <a-button type="primary" @click="showFeedSelector = false">确定</a-button>
  </template>
</a-modal>
</template>



<style scoped>
.tag-form {
  padding: 20px;
  max-width: 800px;
  margin: 0 auto;
}

.cover-upload {
  position: relative;
  width: 120px;
  height: 120px;
  cursor: pointer;
  border: 1px dashed var(--color-border-2);
  border-radius: 4px;
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
}

.cover-upload img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.upload-mask {
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  background-color: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  opacity: 0;
  transition: opacity 0.3s;
}

.cover-upload:hover .upload-mask {
  opacity: 1;
}
.logo-presets {
  margin-top: 14px;
}
.logo-presets-title {
  font-size: 12px;
  color: var(--color-text-3);
  margin-bottom: 8px;
}
.logo-presets-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 8px;
}
.logo-item {
  border: 1px solid var(--color-border-2);
  border-radius: 8px;
  padding: 6px;
  background: var(--color-bg-2);
  cursor: pointer;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
}
.logo-item:hover {
  border-color: rgb(var(--warning-6));
}
.logo-item img {
  width: 32px;
  height: 32px;
}
.logo-item span {
  font-size: 11px;
  color: var(--color-text-2);
}
</style>
