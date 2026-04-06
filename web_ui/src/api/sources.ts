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
  quick_add?: boolean
  tags?: string[]
  add_count?: number
  avatar?: string
  community?: boolean
}

export interface RsshubStatus {
  ok: boolean
  status_code: number
  latency_ms: number
  internal_url: string
  public_url: string
  routes_total: number
  routes_source?: string
  routes_error?: string
  error?: string
}

export interface RsshubRouteItem {
  path: string
  title: string
  maintainers?: string[]
}

export interface RsshubPreviewItem {
  id: string
  title: string
  link: string
  description: string
  publish_time: number
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
  validate_on_add?: boolean
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
    queued_refresh?: boolean
    validated_on_add?: boolean
    warning?: string | null
  }>('/wx/sources/feeds', payload)
}

export const deleteSourceFeed = (feedId: string, params?: { hard?: boolean }) => {
  return http.delete<{ feed_id: string; removed_subscription: number; deleted_feed: boolean }>(
    `/wx/sources/feeds/${encodeURIComponent(feedId)}`,
    {
      params: { hard: params?.hard ?? false }
    }
  )
}

export const refreshSourceFeed = (
  feedId: string,
  params?: { async_mode?: boolean; min_interval_seconds?: number }
) => {
  return http.post<{
    feed_id: string
    total_items?: number
    changed?: number
    queued?: boolean
    skipped?: boolean
    reason?: string
    age_seconds?: number
    min_interval_seconds?: number
  }>(`/wx/sources/feeds/${encodeURIComponent(feedId)}/refresh`, null, {
    params: {
      async_mode: params && typeof params.async_mode === 'boolean' ? params.async_mode : false,
      min_interval_seconds:
        params && typeof params.min_interval_seconds === 'number'
          ? params.min_interval_seconds
          : 0
    },
    silentError: true
  } as any)
}

export const refreshAllSourceFeeds = (params?: { limit?: number; async_mode?: boolean }) => {
  return http.post<{
    mode?: 'async' | 'sync'
    total_feeds: number
    queued?: number
    workers?: number
    refreshed: number
    failed: number
    total_items: number
    changed_items: number
    failures: Array<{ feed_id: string; name: string; error: string }>
  }>('/wx/sources/refresh_all', null, {
    params: {
      limit: params?.limit ?? 300,
      async_mode: params?.async_mode ?? true
    }
  })
}

export const listSourcePlatformPresets = () => {
  return http.get<{ list: SourcePresetItem[] }>('/wx/sources/platform_presets')
}

export const getRsshubStatus = () => {
  return http.get<RsshubStatus>('/wx/sources/rsshub/status')
}

export const listRsshubRoutes = (params?: { kw?: string; limit?: number; offset?: number; base_url?: string }) => {
  return http.get<{
    list: RsshubRouteItem[]
    total: number
    page: { limit: number; offset: number; total: number }
    source?: string
    source_error?: string
  }>(
    '/wx/sources/rsshub/routes',
    {
      params: {
        kw: params?.kw ?? '',
        limit: params?.limit ?? 120,
        offset: params?.offset ?? 0,
        base_url: params?.base_url ?? ''
      }
    }
  )
}

export const previewRsshubRoute = (payload: {
  route: string
  source_platform?: string
  base_url?: string
  limit?: number
}) => {
  return http.post<{
    route: string
    base_url: string
    source_url: string
    feed_title: string
    source_platform: string
    total_items: number
    items: RsshubPreviewItem[]
  }>('/wx/sources/rsshub/preview', payload)
}

export const subscribeRsshubRoute = (payload: {
  route: string
  source_platform?: string
  base_url?: string
  name?: string
  auto_subscribe?: boolean
}) => {
  return http.post<{
    created: boolean
    route: string
    base_url: string
    feed: SourceFeedItem & { items_preview?: number }
  }>('/wx/sources/rsshub/subscribe', payload)
}
