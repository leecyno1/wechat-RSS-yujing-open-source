import http from './http'

export interface PublicChannel {
  id: string
  name: string
  cover: string
  intro: string
}

export interface PublicArticleItem {
  id: string
  title: string
  description: string
  publish_time: number
  mp_id: string
  mp_name: string
  pic_url: string
  is_read: number
  word_count: number
}

export interface PublicInsights {
  article_id: string
  summary: string
  headings: Array<{ level: number; text: string }>
  key_points?: { highlight?: string; points?: string[] } | null
  llm_breakdown?: any
  status: number
  error: string
  updated_at: string
  created_at: string
}

export const getPublicChannels = (params?: { limit?: number; offset?: number; kw?: string }) => {
  return http.get<{ code: number; data: { list: PublicChannel[]; total: number } }>('/wx/public/channels', {
    params: {
      limit: params?.limit ?? 200,
      offset: params?.offset ?? 0,
      kw: params?.kw ?? ''
    }
  })
}

export const getPublicChannelArticles = (
  channelId: string,
  params?: { limit?: number; offset?: number; kw?: string }
) => {
  return http.get<{
    code: number
    data: { channel: PublicChannel | null; list: PublicArticleItem[]; total: number }
  }>(`/wx/public/channels/${encodeURIComponent(channelId)}/articles`, {
    params: {
      limit: params?.limit ?? 30,
      offset: params?.offset ?? 0,
      kw: params?.kw ?? ''
    }
  })
}

export const getPublicInsights = (articleId: string) => {
  return http.get<{ code: number; data: PublicInsights }>(`/wx/public/insights/${encodeURIComponent(articleId)}`)
}

export const getArticleDetailPublic = (articleId: string) => {
  return http.get<{ code: number; data: any }>(`/wx/articles/${encodeURIComponent(articleId)}`)
}

export const generateKeyPointsAuthed = (articleId: string) => {
  return http.post<{ code: number; data: PublicInsights }>(`/wx/insights/${encodeURIComponent(articleId)}/key_points`)
}

export const generateBreakdownAuthed = (articleId: string) => {
  return http.post<{ code: number; data: PublicInsights }>(`/wx/insights/${encodeURIComponent(articleId)}/breakdown`)
}

