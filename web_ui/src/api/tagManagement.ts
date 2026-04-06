import http from './http'
import type { Tag, TagCreate } from '@/types/tagManagement'

export const listTags = (params?: { offset?: number; limit?: number }) => {
  return http.get<Tag[]>('/wx/tags', { 
    params: {
      offset: params?.offset || 0,
      limit: params?.limit || 100
    }
  })
}

export const getTag = (id: string) => {
  return http.get<Tag>(`/wx/tags/${id}`)
}

export const createTag = (data: TagCreate) => {
  return http.post('/wx/tags', data)
}

export const updateTag = (id: string, data: TagCreate) => {
  return http.put(`/wx/tags/${id}`, data)
}

export const deleteTag = (id: string) => {
  return http.delete(`/wx/tags/${id}`)
}

export interface TagPlazaItem extends Tag {
  user_id?: string | null
  creator_username?: string
  creator_nickname?: string
  creator_display?: string
  mp_count?: number
  is_mine?: boolean
}

export const listTagPlaza = (params?: { offset?: number; limit?: number; keyword?: string }) => {
  return http.get<{ list: TagPlazaItem[]; total: number }>('/wx/tags/plaza', {
    params: {
      offset: params?.offset || 0,
      limit: params?.limit || 20,
      keyword: params?.keyword || ''
    }
  })
}

export const useTagFromPlaza = (tagId: string) => {
  return http.post(`/wx/tags/plaza/${tagId}/use`)
}
