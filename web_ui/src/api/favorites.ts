import http from './http'

export const favoriteArticle = (articleId: string) => {
  return http.post(`/wx/favorites/${articleId}`)
}

export const unfavoriteArticle = (articleId: string) => {
  return http.delete(`/wx/favorites/${articleId}`)
}

export const listFavorites = (params: { offset?: number; limit?: number } = {}) => {
  return http.get(`/wx/favorites`, { params })
}

