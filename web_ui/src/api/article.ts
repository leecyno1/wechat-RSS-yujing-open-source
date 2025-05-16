import http from './http'

export interface Article {
  id: number
  title: string
  content: string
  mp_name: string
  publish_time: string
  status: number
  link: string
  created_at: string
}

export interface ArticleListParams {
  offset?: number
  limit?: number
  search?: string
  status?: number
  mp_id?: string
}

export interface ArticleListResult {
  code: number
  data: Article[]
}

export const getArticles = (params: ArticleListParams) => {
  return http.get<ArticleListResult>('/wx/articles', { params })
}

export const getArticleDetail = (id: number) => {
  return http.get<{code: number, data: Article}>(`/wx/articles/${id}`)
}

export const deleteArticle = (id: number) => {
  return http.delete<{code: number, message: string}>(`/wx/articles/${id}`)
}