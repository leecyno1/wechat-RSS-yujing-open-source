import http from './http'

export const listNotes = (params: { article_id?: string; offset?: number; limit?: number } = {}) => {
  return http.get(`/wx/notes`, { params })
}

export const createNote = (payload: { article_id: string; content: string }) => {
  return http.post(`/wx/notes`, payload)
}

export const updateNote = (noteId: number, payload: { content: string }) => {
  return http.put(`/wx/notes/${noteId}`, payload)
}

export const deleteNote = (noteId: number) => {
  return http.delete(`/wx/notes/${noteId}`)
}

export const rewriteNote = (noteId: number, payload: { save?: boolean } = {}) => {
  return http.post(`/wx/notes/${noteId}/rewrite`, { save: !!payload.save })
}
