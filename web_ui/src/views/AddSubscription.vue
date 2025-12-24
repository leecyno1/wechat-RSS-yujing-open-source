<template>
  <div class="add-subscription">
    <a-page-header
      title="添加订阅"
      subtitle="通过订阅广场一键添加，或搜索/文章链接添加"
      :show-back="true"
      @back="goBack"
    />
    
    <a-card>
      <a-tabs type="rounded" default-active-key="plaza">
        <a-tab-pane key="plaza" title="订阅广场">
          <div class="plaza-top">
            <a-input v-model="plazaKw" allow-clear placeholder="在广场中搜索（名称/关键词/标签）" style="max-width: 360px" />
            <a-button type="outline" :loading="plazaLoading" @click="loadPlaza">搜索</a-button>
          </div>

          <a-spin :loading="plazaLoading">
            <a-tabs v-if="plazaCategories.length" type="line" size="small">
              <a-tab-pane v-for="c in plazaCategories" :key="c.id" :title="c.name">
                <div class="plaza-grid">
                  <div v-for="it in c.items" :key="it.name" class="plaza-card">
                    <div class="plaza-card-main">
                      <div class="plaza-title">{{ it.name }}</div>
                      <div v-if="it.desc" class="plaza-desc">{{ it.desc }}</div>
                      <div v-if="it.tags?.length" class="plaza-tags">
                        <a-tag v-for="t in it.tags" :key="t" size="small">{{ t }}</a-tag>
                      </div>
                    </div>
                    <div class="plaza-actions">
                      <a-button
                        size="small"
                        type="primary"
                        :loading="!!addingMap[it.name]"
                        :disabled="isSubscribed(it)"
                        @click="subscribeFromPlaza(it)"
                      >
                        {{ isSubscribed(it) ? '已订阅' : '添加' }}
                      </a-button>
                    </div>
                  </div>
                </div>
              </a-tab-pane>
            </a-tabs>
            <div v-else class="muted">暂无广场数据，可编辑 `data/plaza_mps.json` 自定义推荐列表。</div>
          </a-spin>
        </a-tab-pane>

        <a-tab-pane key="search" title="搜索添加">
          <div class="inline-row">
            <a-select
              v-model="form.name"
              placeholder="输入公众号名称并选择"
              allow-clear
              allow-search
              style="min-width: 320px"
              @search="handleSearch"
            >
              <a-option
                v-for="item of searchResults"
                :key="item.fakeid || item.nickname"
                :value="item.nickname"
                :label="item.nickname"
                @click="handleSelect(item)"
              />
            </a-select>
            <a-button type="primary" :loading="loading" @click="handleSubmit">添加订阅</a-button>
          </div>

          <div class="meta-preview" v-if="form.wx_id">
            <a-avatar :size="40" :src="avatar_url"><img :src="avatar_url" width="40" /></a-avatar>
            <div class="meta-text">
              <div class="meta-title">{{ form.name }}</div>
              <div class="meta-sub">{{ form.description || ' ' }}</div>
            </div>
          </div>

          <a-divider />

          <a-link @click="openDialog()">通过文章链接获取公众号信息</a-link>
          <div v-if="modalVisible" class="inline-row" style="margin-top: 8px">
            <a-input v-model="articleLink" placeholder="粘贴公众号文章链接" style="min-width: 360px" />
            <a-button @click="handleGetMpInfo" :loading="isFetching">获取</a-button>
          </div>
        </a-tab-pane>
      </a-tabs>
    </a-card>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { Message, Modal } from '@arco-design/web-vue'
import { addSubscription, getPlaza, getSubscriptions, searchBiz, getSubscriptionInfo } from '@/api/subscription'
import {Avatar} from '@/utils/constants'
const router = useRouter()
const loading = ref(false)
const isFetching = ref(false)
const searchResults = ref([])
const avatar_url = ref('/static/default-avatar.png')
const formRef = ref(null)
const form = ref({
  name: '',
  wx_id: '',
  avatar:'',
  description: ''
})

// 监听 form.avatar 的变化
watch(() => form.value.avatar, (newValue, oldValue) => {
  console.log('头像地址已更新:', newValue);
  // 这里可以添加更多处理逻辑
  avatar_url.value=Avatar(newValue)
}, { deep: true });

const rules = {
  name: [
    { required: true, message: '请输入公众号名称' },
    { min: 2, max: 30, message: '公众号名称长度应在2-30个字符之间' }
  ],
  wx_id: [
    { required: true, message: '请输入公众号ID' },
    { pattern: /^[a-zA-Z0-9_-]+$/, message: '公众号ID只能包含字母、数字、下划线和横线' }
  ],
  avatar: [
    { 
      required: true, 
      message: '请选择公众号头像',
      validator: (value: string) => {
        return value && value.startsWith('http')
      },
      message: '请选择有效的头像URL'
    }
  ],
  description: [
    { max: 200, message: '描述不能超过200个字符' }
  ]
}

const handleSearch = async (value: string) => {
  if (!value) {
    searchResults.value = []
    return
  }
  try {
    const res = await searchBiz(value, {
      page: 0,
      pageSize: 10
    })
    searchResults.value = res.list || []
  } catch (error) {
    // Message.error('搜索公众号失败')
    searchResults.value = []
  }
}

const handleGetMpInfo = async () => {
  if (isFetching.value) return false;
  if (!articleLink.value) {
    Message.error('请提供一个公众号文章链接');
    return false;
  }
  isFetching.value = true;
  try {
    const res = await getSubscriptionInfo(articleLink.value.trim()); // 确保去除空格
    console.log('获取公众号信息:', res);
    const info=res?.mp_info||false
    if (info) {
      form.value.name = info.mp_name || '';
      form.value.description = info.mp_name || '';
      form.value.wx_id = info.biz || '';
      form.value.avatar = info.logo || '';
    }
  } catch (error) {
    console.error('获取公众号信息失败:', error);
    Message.error('获取公众号信息失败');
    return false;
  } finally {
    isFetching.value = false;
  }
  modalVisible.value = false;
  return true;
}

const handleSelect = (item: any) => {
  console.log(item)
  form.value.name = item.nickname
  form.value.wx_id = item.fakeid // 修正拼写错误：fackid → fakeid
  form.value.description = item.signature
  form.value.avatar = item.round_head_img
}

const handleSubmit = async () => {
  
  loading.value = true
  if (!form.value.name || !form.value.wx_id) {
    Message.error('请先选择一个公众号')
    loading.value = false
    return
  }

  // 表单提交
  try {
    await addSubscription({
      mp_name: form.value.name,
      mp_id: form.value.wx_id,
      avatar: form.value.avatar,
      mp_intro: form.value.description,
    })
    
    Message.success('订阅添加成功')
    router.push('/')
  } catch (error) {
    console.error('订阅添加失败:', error)
    Message.error(error.message || '订阅添加失败，请稍后重试')
  } finally {
    loading.value = false
  }
}

const modalVisible = ref(false);
const articleLink = ref('');

const openDialog = () => {
  modalVisible.value = true;
};

type PlazaItem = { name: string; kw?: string; desc?: string; tags?: string[] }
type PlazaCategory = { id: string; name: string; items: PlazaItem[] }

const plazaLoading = ref(false)
const plazaKw = ref('')
const plazaData = ref<{ categories: PlazaCategory[] }>({ categories: [] })
const plazaCategories = computed(() => plazaData.value.categories || [])

const subscribedFeedIds = ref<Set<string>>(new Set())
const subscribedNames = ref<Set<string>>(new Set())
const addingMap = ref<Record<string, boolean>>({})

const loadSubscribed = async () => {
  try {
    const res: any = await getSubscriptions({ page: 0, pageSize: 1000 })
    const list = res?.list || res?.data?.list || []
    const ids = new Set<string>()
    const names = new Set<string>()
    for (const x of list) {
      if (x?.id) ids.add(String(x.id))
      if (x?.mp_name) names.add(String(x.mp_name).trim().toLowerCase())
    }
    subscribedFeedIds.value = ids
    subscribedNames.value = names
  } catch {
    subscribedFeedIds.value = new Set()
    subscribedNames.value = new Set()
  }
}

const loadPlaza = async () => {
  plazaLoading.value = true
  try {
    const res: any = await getPlaza({ kw: plazaKw.value })
    plazaData.value = res || { categories: [] }
  } catch (e) {
    plazaData.value = { categories: [] }
  } finally {
    plazaLoading.value = false
  }
}

const isSubscribed = (it: PlazaItem) => {
  const n = String(it.name || '').trim().toLowerCase()
  if (!n) return false
  return subscribedNames.value.has(n)
}

const subscribeFromPlaza = async (it: PlazaItem) => {
  const key = it.name
  if (addingMap.value[key]) return
  addingMap.value[key] = true
  try {
    // If plaza already provides mp_id, subscribe directly; otherwise resolve via backend search.
    const directMpId = String((it as any).mp_id || '').trim()
    if (directMpId) {
      await addSubscription({
        mp_name: it.name,
        mp_id: directMpId,
        avatar: String((it as any).cover || (it as any).avatar || ''),
        mp_intro: it.desc || ''
      })
      Message.success(`已订阅：${it.name}`)
      await loadSubscribed()
      return
    }
    const kw = (it.kw || it.name || '').trim()
    if (!kw) throw new Error('缺少关键词')
    const r: any = await searchBiz(kw, { page: 0, pageSize: 5 })
    const list = r?.list || []
    if (!list.length) {
      Message.error(`未找到公众号：${kw}`)
      return
    }
    const picked = list[0]
    await addSubscription({
      mp_name: picked.nickname,
      mp_id: picked.fakeid,
      avatar: picked.round_head_img,
      mp_intro: picked.signature
    })
    Message.success(`已订阅：${picked.nickname}`)
    await loadSubscribed()
  } catch (e: any) {
    Message.error(e?.message || '订阅失败')
  } finally {
    addingMap.value[key] = false
  }
}

const goBack = () => {
  router.go(-1)
}

onMounted(async () => {
  await loadSubscribed()
  await loadPlaza()
})
</script>

<style scoped>
.add-subscription {
  padding: 20px;
  max-width: 980px;
  margin: 0 auto;
}

.arco-form-item {
  margin-bottom: 20px;
}
.plaza-top {
  display: flex;
  gap: 8px;
  align-items: center;
  margin-bottom: 12px;
}
.plaza-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
}
.plaza-card {
  border: 1px solid var(--color-neutral-3);
  border-radius: 12px;
  padding: 10px 12px;
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: center;
  background: var(--color-bg-1);
}
.plaza-title {
  font-weight: 700;
  line-height: 1.2;
}
.plaza-desc {
  color: var(--color-text-3);
  font-size: 12px;
  margin-top: 2px;
}
.plaza-tags {
  margin-top: 6px;
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
}
.plaza-actions {
  flex: 0 0 auto;
}
.inline-row {
  display: flex;
  gap: 8px;
  align-items: center;
  flex-wrap: wrap;
}
.meta-preview {
  margin-top: 12px;
  display: flex;
  gap: 10px;
  align-items: center;
}
.meta-text {
  min-width: 0;
}
.meta-title {
  font-weight: 700;
}
.meta-sub {
  color: var(--color-text-3);
  font-size: 12px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 640px;
}
.muted {
  color: var(--color-text-3);
  padding: 8px 0;
}
</style>
