<script setup lang="ts">
import { ref, computed } from 'vue'

const props = defineProps({
  modelValue: {
    type: String,
    default: '* * * * *'
  }
})

const emit = defineEmits(['update:modelValue'])

const minutes = ref('*')
const hours = ref('*')
const days = ref('*')
const months = ref('*')
const weekdays = ref('*')

const parseCronDescription = (part: string, type: string) => {
  if (part === '*') return `每${type}`
  if (part.startsWith('*/')) {
    const num = part.substring(2)
    return `每${num}${type}`
  }
  if (part.includes('-')) {
    const [start, end] = part.split('-')
    return `${start}到${end}${type}`
  }
  if (part.includes(',')) {
    return `在${part.split(',').join('、')}${type}`
  }
  return `在${part}${type}`
}

const cronExpression = computed(() => {
  return `${minutes.value} ${hours.value} ${days.value} ${months.value} ${weekdays.value}`
})

const cornDescription = computed(() => {
  const monthDesc = parseCronDescription(months.value, '月')
  const dayDesc = parseCronDescription(days.value, '日')
  const hourDesc = parseCronDescription(hours.value, '小时')
  const minuteDesc = parseCronDescription(minutes.value, '分钟')
  
  let weekdayDesc = ''
  if (weekdays.value === '*') {
    weekdayDesc = '每天'
  } else if (weekdays.value === '1-5') {
    weekdayDesc = '工作日'
  } else if (weekdays.value === '0,6') {
    weekdayDesc = '周末'
  } else if (weekdays.value.includes(',')) {
    const days = weekdays.value.split(',').map(d => 
      ['周日','周一','周二','周三','周四','周五','周六'][parseInt(d)]
    )
    weekdayDesc = `在${days.join('、')}`
  } else if (weekdays.value.includes('-')) {
    const [start, end] = weekdays.value.split('-').map(d => 
      ['周日','周一','周二','周三','周四','周五','周六'][parseInt(d)]
    )
    weekdayDesc = `${start}到${end}`
  } else {
    weekdayDesc = `在${['周日','周一','周二','周三','周四','周五','周六'][parseInt(weekdays.value)]}`
  }
  
  return `${monthDesc} ${dayDesc} ${weekdayDesc} ${hourDesc} ${minuteDesc}`
})

const updateExpression = () => {
  emit('update:modelValue', cronExpression.value)
}

const parseExpression = (expr: string) => {
  const parts = expr.split(' ')
  if (parts.length === 5) {
    minutes.value = parts[0]
    hours.value = parts[1]
    days.value = parts[2]
    months.value = parts[3]
    weekdays.value = parts[4]
  }
}

defineExpose({
  parseExpression
})
</script>

<template>
  <a-card class="cron-picker" :bordered="false">
    <a-form>
      <a-form-item label="分钟">
        <a-select v-model="minutes" @change="updateExpression" style="width: 180px">
          <a-option v-for="m in 60" :key="m-1" :value="(m-1).toString()">{{ m-1 }}</a-option>
          <a-option value="*">*</a-option>
          <a-option value="*/5">每5分钟</a-option>
          <a-option value="*/15">每15分钟</a-option>
          <a-option value="*/30">每30分钟</a-option>
          <a-option value="0-30">0-30分钟</a-option>
          <a-option value="30-59">30-59分钟</a-option>
        </a-select>
      </a-form-item>
      <a-form-item label="小时">
        <a-select v-model="hours" @change="updateExpression" style="width: 180px">
          <a-option v-for="h in 24" :key="h-1" :value="(h-1).toString()">{{ h-1 }}</a-option>
          <a-option value="*">*</a-option>
          <a-option value="*/6">每6小时</a-option>
          <a-option value="*/12">每12小时</a-option>
          <a-option value="0-12">0-12点</a-option>
          <a-option value="12-23">12-23点</a-option>
        </a-select>
      </a-form-item>
      <a-form-item label="日">
        <a-select v-model="days" @change="updateExpression" style="width: 180px">
          <a-option v-for="d in 31" :key="d" :value="d.toString()">{{ d }}</a-option>
          <a-option value="*">*</a-option>
          <a-option value="*/5">每5天</a-option>
          <a-option value="*/10">每10天</a-option>
          <a-option value="1-15">1-15日</a-option>
          <a-option value="16-31">16-31日</a-option>
        </a-select>
      </a-form-item>
      <a-form-item label="月">
        <a-select v-model="months" @change="updateExpression" style="width: 180px">
          <a-option v-for="m in 12" :key="m" :value="m.toString()">{{ m }}</a-option>
          <a-option value="*">*</a-option>
          <a-option value="*/3">每3个月</a-option>
          <a-option value="*/6">每6个月</a-option>
          <a-option value="1-6">1-6月</a-option>
          <a-option value="7-12">7-12月</a-option>
        </a-select>
      </a-form-item>
      <a-form-item label="星期">
        <a-select v-model="weekdays" @change="updateExpression" style="width: 180px">
          <a-option value="0">周日</a-option>
          <a-option value="1">周一</a-option>
          <a-option value="2">周二</a-option>
          <a-option value="3">周三</a-option>
          <a-option value="4">周四</a-option>
          <a-option value="5">周五</a-option>
          <a-option value="6">周六</a-option>
          <a-option value="*">*</a-option>
          <a-option value="1-5">工作日</a-option>
          <a-option value="0,6">周末</a-option>
          <a-option value="*/2">每隔一天</a-option>
        </a-select>
      </a-form-item>
    </a-form>

    <a-space direction="vertical" fill>
      <a-typography-text strong>表达式预览: {{ cronExpression }}</a-typography-text>
      <a-typography-text type="secondary">解释: {{ cornDescription }}</a-typography-text>

      <div class="examples">
        <a-typography-text strong>常用示例:</a-typography-text>
        <a-list :bordered="false">
          <a-list-item 
            @click="minutes='0';hours='0';days='*';months='*';weekdays='*';updateExpression()"
          >
            每天午夜 (0 0 * * *)
          </a-list-item>
          <a-list-item 
            @click="minutes='0';hours='12';days='*';months='*';weekdays='*';updateExpression()"
          >
            每天中午 (0 12 * * *)
          </a-list-item>
          <a-list-item 
            @click="minutes='0';hours='9';days='*';months='*';weekdays='1-5';updateExpression()"
          >
            工作日早上9点 (0 9 * * 1-5)
          </a-list-item>
          <a-list-item 
            @click="minutes='*/5';hours='*';days='*';months='*';weekdays='*';updateExpression()"
          >
            每5分钟 (*/5 * * * *)
          </a-list-item>
          <a-list-item 
            @click="minutes='0';hours='*/6';days='*';months='*';weekdays='*';updateExpression()"
          >
            每6小时 (0 */6 * * *)
          </a-list-item>
          <a-list-item 
            @click="minutes='0';hours='0';days='*/10';months='*';weekdays='*';updateExpression()"
          >
            每10天 (0 0 */10 * *)
          </a-list-item>
        </a-list>
      </div>
    </a-space>
  </a-card>
</template>

<style scoped>
.cron-picker {
  padding: 10px;
  max-width: 600px;
}

.arco-form-item {
  margin-bottom: 12px;
}

.examples {
  margin-top: 15px;
}

:deep(.arco-list-item) {
  padding: 8px 0;
  cursor: pointer;
  color: rgb(var(--primary-6));
}

:deep(.arco-list-item:hover) {
  background-color: var(--color-fill-2);
}
</style>