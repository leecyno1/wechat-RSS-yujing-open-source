import http from './http'

export interface Subscription {
  mp_id: string
  mp_name: string
  mp_cover: string
  mp_intro: string
  status: number
  sync_time: string
  rss_url: string
}

export interface SubscriptionListResult {
  code: number
  data: Subscription[]
}

export interface AddSubscriptionParams {
  mp_name: string
  mp_id: string
  rss_url: string
  mp_intro?: string
}

export const getSubscriptions = (params?: { offset?: number; limit?: number }) => {
  return http.get<SubscriptionListResult>('/wx/mps', { params })
}

export const getSubscriptionDetail = (mp_id: string) => {
  return http.get<{code: number, data: Subscription}>(`/wx/mps/${mp_id}`)
}

export const addSubscription = (data: AddSubscriptionParams) => {
  return http.post<{code: number, message: string}>('/wx/mps', data)
}

export const deleteSubscription = (mp_id: string) => {
  return http.delete<{code: number, message: string}>(`/wx/mps/${mp_id}`)
}

export const updateSubscription = (mp_id: string, data: Partial<Subscription>) => {
  return http.put<{code: number, message: string}>(`/wx/mps/${mp_id}`, data)
}