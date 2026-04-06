export interface SubscriptionFeedPatch {
  id: string
  name: string
  cover?: string
  intro?: string
  source_type?: string
  source_platform?: string
  source_url?: string
  unread_count?: number
  article_count?: number
  latest_publish_time?: number
}

export interface SubscriptionFeedChangedDetail {
  action: 'added' | 'removed'
  feed: SubscriptionFeedPatch
}

const CHANNEL_FEEDS_CHANGED_EVENT = 'channel-feeds-changed'

export const emitChannelFeedChanged = (detail: SubscriptionFeedChangedDetail) => {
  if (typeof window === 'undefined') return
  window.dispatchEvent(new CustomEvent<SubscriptionFeedChangedDetail>(CHANNEL_FEEDS_CHANGED_EVENT, { detail }))
}

export const onChannelFeedChanged = (listener: (detail: SubscriptionFeedChangedDetail) => void) => {
  if (typeof window === 'undefined') return () => {}
  const handler = (event: Event) => {
    const custom = event as CustomEvent<SubscriptionFeedChangedDetail>
    if (!custom?.detail) return
    listener(custom.detail)
  }
  window.addEventListener(CHANNEL_FEEDS_CHANGED_EVENT, handler as EventListener)
  return () => window.removeEventListener(CHANNEL_FEEDS_CHANGED_EVENT, handler as EventListener)
}
