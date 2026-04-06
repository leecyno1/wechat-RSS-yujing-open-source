import http from './http'

export const getInsights = (articleId: string, includeLlm = true) => {
  const id = encodeURIComponent(String(articleId || ''))
  return http.get(`/wx/insights/${id}`, { params: { include_llm: includeLlm } })
}

export const refreshBasicInsights = (articleId: string) => {
  const id = encodeURIComponent(String(articleId || ''))
  return http.post(`/wx/insights/${id}/basic`)
}

export const generateAiSummary = (articleId: string, force = false) => {
  const id = encodeURIComponent(String(articleId || ''))
  return http.post(`/wx/insights/${id}/summary`, null, {
    params: { force }
  })
}

export const generateKeyPoints = (articleId: string, force = false) => {
  const id = encodeURIComponent(String(articleId || ''))
  return http.post(`/wx/insights/${id}/key_points`, null, {
    params: { force }
  })
}

export const generateLlmBreakdown = (articleId: string) => {
  const id = encodeURIComponent(String(articleId || ''))
  return http.post(`/wx/insights/${id}/breakdown`)
}

export const batchCacheInsights = (params?: { limit?: number }) => {
  return http.post('/wx/insights/batch/cache', null, {
    params: {
      limit: params?.limit ?? 120
    }
  })
}

export const warmupInsights = (articleId: string) => {
  const id = encodeURIComponent(String(articleId || ''))
  return http.post(`/wx/insights/${id}/warmup`)
}
