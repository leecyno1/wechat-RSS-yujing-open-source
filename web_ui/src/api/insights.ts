import http from './http'

export const getInsights = (articleId: string, includeLlm = true) => {
  return http.get(`/wx/insights/${articleId}`, { params: { include_llm: includeLlm } })
}

export const refreshBasicInsights = (articleId: string) => {
  return http.post(`/wx/insights/${articleId}/basic`)
}

export const generateLlmBreakdown = (articleId: string) => {
  return http.post(`/wx/insights/${articleId}/breakdown`)
}

