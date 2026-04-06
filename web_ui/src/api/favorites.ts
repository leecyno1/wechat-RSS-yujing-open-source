import http from './http'

export interface FavoriteMetaItem {
  article_id: string
  category: string
  tags: string[]
  open_count: number
  updated_at?: string
}

export const favoriteArticle = (articleId: string) => {
  return http.post(`/wx/favorites/article/${articleId}`)
}

export const unfavoriteArticle = (articleId: string) => {
  return http.delete(`/wx/favorites/article/${articleId}`)
}

export const listFavorites = (params: { offset?: number; limit?: number } = {}) => {
  return http.get(`/wx/favorites`, { params })
}

export const listPublicFavorites = (params: { offset?: number; limit?: number; days?: number } = {}) => {
  return http.get(`/wx/favorites/public`, { params })
}

export const listFavoriteMeta = (params: { only_favorited?: boolean } = {}) => {
  return http.get<{ list: FavoriteMetaItem[]; categories: string[] }>(`/wx/favorites/meta`, { params })
}

export const updateFavoriteMeta = (
  articleId: string,
  payload: { category?: string | null; tags?: string[]; open_count_inc?: number }
) => {
  return http.put<FavoriteMetaItem>(`/wx/favorites/meta/${encodeURIComponent(articleId)}`, payload)
}

export const listFavoriteCategories = () => {
  return http.get<{ list: string[] }>(`/wx/favorites/categories`)
}

export const createFavoriteCategory = (name: string) => {
  return http.post<{ name: string }>(`/wx/favorites/categories`, { name })
}
