import http from './http'

export interface ChannelFeedItem {
  id: string
  name: string
  cover: string
  intro: string
  created_at?: string | null
  unread_count: number
  article_count: number
  latest_publish_time: number
}

export interface ChannelFeedsResult {
  list: ChannelFeedItem[]
  total: number
  stats: { unread_total: number; article_total: number; feed_total: number }
}

export const getChannelFeeds = (params?: { kw?: string; limit?: number; offset?: number; sort?: string }) => {
  return http.get<ChannelFeedsResult>('/wx/channels/feeds', {
    params: {
      kw: params?.kw ?? '',
      limit: params?.limit ?? 200,
      offset: params?.offset ?? 0,
      sort: params?.sort ?? 'recent'
    }
  })
}

export const markAllRead = (params?: { mp_id?: string; kw?: string }) => {
  return http.post<{ updated: number }>('/wx/channels/read_all', null, {
    params: {
      mp_id: params?.mp_id ?? null,
      mp_ids: null,
      kw: params?.kw ?? ''
    }
  })
}

export const markAllReadMulti = (params: { mp_ids: string[]; kw?: string }) => {
  return http.post<{ updated: number }>('/wx/channels/read_all', null, {
    params: {
      mp_id: null,
      mp_ids: (params?.mp_ids || []).join(','),
      kw: params?.kw ?? ''
    }
  })
}

export const setArticleRead = (articleId: string, isRead: boolean) => {
  return http.put('/wx/articles/' + encodeURIComponent(articleId) + '/read', null, {
    params: { is_read: isRead }
  })
}

export const getChannelArticles = (params: {
  mp_id?: string
  mp_ids?: string[]
  search?: string
  limit?: number
  offset?: number
  unread_only?: boolean
}) => {
  return http.get<{ list: any[]; total: number }>('/wx/articles', {
    params: {
      mp_id: params.mp_id || null,
      mp_ids: params.mp_ids?.length ? params.mp_ids.join(',') : null,
      search: params.search || null,
      limit: params.limit ?? 30,
      offset: params.offset ?? 0,
      unread_only: params.unread_only ?? false
    }
  })
}

export const backfillArticle = (articleId: string, params?: { max_pages?: number }) => {
  return http.post<{ ok: boolean; updated: boolean; page?: number; matched_by?: string; reason?: string }>(
    `/wx/channels/articles/${encodeURIComponent(articleId)}/backfill`,
    null,
    {
      params: {
        max_pages: params?.max_pages ?? 25
      }
    }
  )
}

export const backfillMp = (mpId: string, params?: { max_pages?: number; only_missing?: boolean }) => {
  return http.post<{
    ok: boolean
    mp_id: string
    max_pages: number
    only_missing: boolean
    scanned_items: number
    matched_existing: number
    updated: number
  }>(`/wx/channels/mps/${encodeURIComponent(mpId)}/backfill`, null, {
    params: {
      max_pages: params?.max_pages ?? 20,
      only_missing: params?.only_missing ?? true
    }
  })
}

export const fetchArticleContent = (articleId: string, params?: { force?: boolean }) => {
  return http.post<{
    ok: boolean
    fetched: boolean
    changed?: boolean
    content_len: number
    desc_len: number
    pic_url?: string
    summary_len?: number
  }>(`/wx/articles/${encodeURIComponent(articleId)}/content/fetch`, null, {
    params: {
      force: params?.force ?? false
    }
  })
}

export const getAuthedInsights = (articleId: string, params?: { include_llm?: boolean }) => {
  return http.get<any>(`/wx/insights/${encodeURIComponent(articleId)}`, {
    params: {
      include_llm: params?.include_llm ?? true
    }
  })
}
