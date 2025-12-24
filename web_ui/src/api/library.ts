import http from './http'

export const getLibraryArticle = (articleId: string) => {
  return http.get(`/wx/library/articles/${articleId}`)
}

