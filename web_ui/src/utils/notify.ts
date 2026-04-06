import { Notification } from '@arco-design/web-vue'

type NotifyKind = 'info' | 'success' | 'warning' | 'error'

type NotifyOptions = {
  title?: string
  duration?: number
  dedupeKey?: string
  throttleMs?: number
}

const LAST_NOTIFY_TS = new Map<string, number>()
const SUPPRESS_PATTERNS = [
  /Input should be less than or equal to \d+/i,
  /Input should be greater than or equal to \d+/i,
  /String should have at most \d+ characters?/i,
  /String should have at least \d+ characters?/i,
]

const normalizeValidationText = (msg: string): string => {
  const text = String(msg || '').trim()
  if (!text) return ''
  let m = text.match(/Input should be less than or equal to (\d+)/i)
  if (m) return `输入值不能大于 ${m[1]}`
  m = text.match(/Input should be greater than or equal to (\d+)/i)
  if (m) return `输入值不能小于 ${m[1]}`
  m = text.match(/String should have at most (\d+) characters?/i)
  if (m) return `文本长度不能超过 ${m[1]} 个字符`
  m = text.match(/String should have at least (\d+) characters?/i)
  if (m) return `文本长度不能少于 ${m[1]} 个字符`
  if (/Field required/i.test(text)) return '缺少必填字段'
  return text
}

const toText = (v: any) => {
  if (typeof v === 'string') return v
  if (v == null) return ''
  if (typeof v === 'number' || typeof v === 'boolean') return String(v)
  if (Array.isArray(v)) {
    const out = v.map((x) => toText(x)).filter(Boolean).join('；')
    return out || ''
  }
  if (typeof v === 'object') {
    const direct = toText(v.message || v.msg || v.error || v.detail || '')
    if (direct) return direct
    if (Array.isArray(v.errors)) {
      const merged = v.errors
        .map((e: any) => toText(e?.message || e?.msg || e))
        .filter(Boolean)
        .join('；')
      if (merged) return merged
    }
    return ''
  }
  return String(v)
}

const notify = (kind: NotifyKind, content: any, opts?: NotifyOptions) => {
  const text = normalizeValidationText(toText(content)).trim() || '操作失败'
  if (SUPPRESS_PATTERNS.some((re) => re.test(text))) return
  const dedupeKey = String(opts?.dedupeKey || `${kind}:${text}`)
  const throttleMs = Math.max(200, Number(opts?.throttleMs || 1500))
  const now = Date.now()
  const prev = LAST_NOTIFY_TS.get(dedupeKey) || 0
  if (now - prev < throttleMs) return
  LAST_NOTIFY_TS.set(dedupeKey, now)

  const payload = {
    title: opts?.title || (kind === 'error' ? '提示' : ''),
    content: text,
    position: 'topRight' as const,
    duration: Number(opts?.duration || 2200),
    closable: true
  }

  if (kind === 'error') Notification.error(payload)
  else if (kind === 'warning') Notification.warning(payload)
  else if (kind === 'success') Notification.success(payload)
  else Notification.info(payload)
}

export const notifyInfo = (content: any, opts?: NotifyOptions) => notify('info', content, opts)
export const notifySuccess = (content: any, opts?: NotifyOptions) => notify('success', content, opts)
export const notifyWarning = (content: any, opts?: NotifyOptions) => notify('warning', content, opts)
export const notifyError = (content: any, opts?: NotifyOptions) => notify('error', content, opts)
