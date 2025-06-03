<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { searchMps } from '@/api/subscription'

interface MpItem {
  id: string
  mp_name: string
  mp_cover: string
}

const props = defineProps({
  modelValue: {
    type: String,
    default: () => ""
  }
})

const emit = defineEmits(['update:modelValue'])

const searchKeyword = ref('')
const loading = ref(false)
const mpList = ref<MpItem[]>([])
const selectedMps = ref<MpItem[]>([])

const filteredMps = computed(() => {
  return mpList.value.filter(mp => 
    !selectedMps.value.some(selected => selected.id === mp.id)
  )
})

const fetchMps = async () => {
  loading.value = true
  try {
    const res = await searchMps(searchKeyword.value)
    mpList.value = res.list
  } finally {
    loading.value = false
  }
}

const handleSearch = () => {
  fetchMps()
}

const toggleSelect = (mp: MpItem) => {
  const index = selectedMps.value.findIndex(m => m.id === mp.id)
  if (index === -1) {
    selectedMps.value.push(mp)
  } else {
    selectedMps.value.splice(index, 1)
  }
  emitSelectedIds()
}

const removeSelected = (mp: MpItem) => {
  selectedMps.value = selectedMps.value.filter(m => m.id !== mp.id)
  emitSelectedIds()
}

const clearAll = () => {
  selectedMps.value = []
  emitSelectedIds()
}

const selectAll = () => {
  filteredMps.value.forEach(mp => {
    if (!selectedMps.value.some(m => m.id === mp.id)) {
      selectedMps.value.push(mp)
    }
  })
  emitSelectedIds()
}

const emitSelectedIds = () => {
  // emit('update:modelValue', selectedMps.value.map(mp => mp.id).join(','))
  emit('update:modelValue', selectedMps.value)
}

const parseSelected = (data:MpItem[]) => {
  selectedMps.value = data.map(item => {
    const found = mpList.value.find(mp => mp.id === item.id)
    return found || {
      id: item.id,
      mp_name: item.mp_name,
      mp_cover: item.mp_cover||''
    }
  })
}

defineExpose({
  parseSelected
})

onMounted(() => {
  fetchMps()
  if (props.modelValue.length > 0) {
    parseSelected(props.modelValue)
  }
})
</script>

<template>
  <a-card class="mp-multi-select" :bordered="false">
    <a-space direction="vertical" fill>
      <a-space>
        <a-input
          v-model="searchKeyword"
          placeholder="搜索公众号"
          allow-clear
          @press-enter="handleSearch"
        />
        <a-button type="primary" @click="handleSearch">搜索</a-button>
      </a-space>

      <a-spin :loading="loading">
        <template v-if="selectedMps.length > 0">
          <a-space align="center">
            <h4>已选公众号 ({{ selectedMps.length }})</h4>
            <a-button size="mini" type="text" @click="clearAll">清空</a-button>
          </a-space>
          <a-space wrap>
            <a-tag
              v-for="mp in selectedMps"
              :key="mp.id"
              closable
              @close="removeSelected(mp)"
            >
              <a-avatar :size="20" :image-url="mp.mp_cover">
                <img v-if="mp.avatar" :src="mp.mp_cover" :alt="mp.mp_name" />
              </a-avatar>
              {{ mp.mp_name }}
            </a-tag>
          </a-space>
        </template>

        <a-space align="center">
          <h4>可选公众号</h4>
          <a-button size="mini" type="text" @click="selectAll">全选</a-button>
        </a-space>
        <a-list :bordered="false">
          <a-list-item
            v-for="mp in filteredMps"
            :key="mp.id"
            @click="toggleSelect(mp)"
          >
            <a-space>
              <a-avatar :image-url="mp.mp_cover">
                <img v-if="mp.mp_cover" :src="mp.mp_cover" :alt="mp.mp_name" />
              </a-avatar>
              <span>{{ mp.mp_name }}</span>
            </a-space>
          </a-list-item>
        </a-list>
      </a-spin>
    </a-space>
  </a-card>
</template>

<style scoped>
.mp-multi-select {
  padding: 15px;
}

h4 {
  margin-bottom: 10px;
  font-size: 14px;
  color: var(--color-text-2);
}

:deep(.arco-list-item) {
  padding: 8px 0;
  cursor: pointer;
}

:deep(.arco-list-item:hover) {
  background-color: var(--color-fill-2);
}
</style>