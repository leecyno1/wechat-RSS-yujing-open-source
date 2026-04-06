const TOKEN_KEY = 'token'
const TOKEN_EXPIRE_KEY = 'token_expire'
const USER_ROLE_KEY = 'current_user_role'

const decodeJwtPayload = (token: string): Record<string, any> | null => {
  const raw = String(token || '').trim()
  if (!raw) return null
  const parts = raw.split('.')
  if (parts.length < 2) return null
  try {
    const b64 = parts[1].replace(/-/g, '+').replace(/_/g, '/')
    const padded = b64 + '==='.slice((b64.length + 3) % 4)
    const text = decodeURIComponent(
      atob(padded)
        .split('')
        .map((c) => `%${(`00${c.charCodeAt(0).toString(16)}`).slice(-2)}`)
        .join('')
    )
    return JSON.parse(text)
  } catch {
    return null
  }
}

export const getToken = (): string | null => localStorage.getItem(TOKEN_KEY)

export const setToken = (token: string) => {
  localStorage.setItem(TOKEN_KEY, String(token || '').trim())
}

export const getTokenExpire = (): number => {
  const raw = localStorage.getItem(TOKEN_EXPIRE_KEY)
  if (!raw) return 0
  const n = Number(raw)
  return Number.isFinite(n) ? n : 0
}

export const setTokenExpire = (expireAtMs: number) => {
  const n = Number(expireAtMs || 0)
  if (Number.isFinite(n) && n > 0) localStorage.setItem(TOKEN_EXPIRE_KEY, String(Math.floor(n)))
  else localStorage.removeItem(TOKEN_EXPIRE_KEY)
}

export const inferTokenExpire = (token?: string | null): number => {
  const t = String(token || getToken() || '').trim()
  if (!t) return 0
  const payload = decodeJwtPayload(t)
  const exp = Number(payload?.exp || 0)
  if (!Number.isFinite(exp) || exp <= 0) return 0
  return Math.floor(exp * 1000)
}

export const ensureTokenExpire = (token?: string | null): number => {
  const exists = getTokenExpire()
  if (exists > 0) return exists
  const inferred = inferTokenExpire(token)
  if (inferred > 0) setTokenExpire(inferred)
  return inferred
}

export const setAuthSession = (token: string, expiresInSec?: number) => {
  setToken(token)
  const sec = Number(expiresInSec || 0)
  if (Number.isFinite(sec) && sec > 0) {
    setTokenExpire(Date.now() + sec * 1000)
  } else {
    const inferred = inferTokenExpire(token)
    if (inferred > 0) setTokenExpire(inferred)
    else localStorage.removeItem(TOKEN_EXPIRE_KEY)
  }
}

export const clearAuthSession = () => {
  localStorage.removeItem(TOKEN_KEY)
  localStorage.removeItem(TOKEN_EXPIRE_KEY)
  localStorage.removeItem(USER_ROLE_KEY)
}

export const isTokenExpiringSoon = (thresholdMs = 10 * 60 * 1000): boolean => {
  const token = getToken()
  if (!token) return false
  let expireAt = getTokenExpire()
  if (expireAt <= 0) expireAt = ensureTokenExpire(token)
  if (expireAt <= 0) return false
  return expireAt - Date.now() <= Math.max(1000, Number(thresholdMs || 0))
}
