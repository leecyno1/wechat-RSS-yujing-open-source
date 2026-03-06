import http from './http'

export interface SourceFeedItem {
  id: string
  name: string
  source_type: 'rss' | 'rsshub'
  source_platform: string
  source_url: string
  updated_at?: string | null
}

export interface SourcePresetItem {
  platform: string
  name: string
  source_type: 'rss' | 'rsshub'
  source_url?: string
  rsshub_route_template?: string
  description?: string
}

export const listSourceFeeds = (params?: { limit?: number; offset?: number; source_platform?: string }) => {
  return http.get<{ list: SourceFeedItem[]; total: number }>('/wx/sources/feeds', {
    params: {
      limit: params?.limit ?? 300,
      offset: params?.offset ?? 0,
      source_platform: params?.source_platform ?? ''
    }
  })
}

export const addSourceFeed = (payload: {
  source_type: 'rss' | 'rsshub'
  source_platform?: string
  source_url?: string
  rsshub_base_url?: string
  rsshub_route?: string
  name?: string
  auto_subscribe?: boolean
}) => {
  return http.post<{
    created: boolean
    feed: {
      id: string
      name: string
      source_type: 'rss' | 'rsshub'
      source_platform: string
      source_url: string
      items_preview: number
    }
  }>('/wx/sources/feeds', payload)
}

export const refreshSourceFeed = (feedId: string) => {
  return http.post<{ feed_id: string; total_items: number; changed: number }>(`/wx/sources/feeds/${encodeURIComponent(feedId)}/refresh`)
}

export const refreshAllSourceFeeds = (params?: { limit?: number }) => {
  return http.post<{
    total_feeds: number
    refreshed: number
    failed: number
    total_items: number
    changed_items: number
    failures: Array<{ feed_id: string; name: string; error: string }>
  }>('/wx/sources/refresh_all', null, {
    params: {
      limit: params?.limit ?? 300
    }
  })
}

export const listSourcePlatformPresets = () => {
  return http.get<{ list: SourcePresetItem[] }>('/wx/sources/platform_presets')
}
