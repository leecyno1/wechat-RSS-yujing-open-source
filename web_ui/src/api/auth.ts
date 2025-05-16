import http from './http'

export interface LoginParams {
  username: string
  password: string
}

export interface LoginResult {
  access_token: string
  token_type: string
}

export const login = (data: LoginParams) => {
  const formData = new URLSearchParams()
  formData.append('username', data.username)
  formData.append('password', data.password)
  return http.post<LoginResult>('/wx/auth/login', formData, {
    headers: {
      'Content-Type': 'application/x-www-form-urlencoded'
    }
  })
}

export const verifyToken = () => {
  return http.get('/wx/auth/verify')
}

export const refreshToken = () => {
  return http.post<LoginResult>('/wx/auth/refresh')
}

export const logout = () => {
  return http.post('/wx/auth/logout')
}

export const getCurrentUser = () => {
  return http.get('/wx/user')
}