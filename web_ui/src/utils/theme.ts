export type ThemeMode = 'system' | 'light' | 'dark'

const THEME_MODE_KEY = 'theme_mode'

let media: MediaQueryList | null = null
let mediaListener: ((e: MediaQueryListEvent) => void) | null = null

const setArcoThemeAttr = (isDark: boolean) => {
  if (!document?.body) return
  if (isDark) document.body.setAttribute('arco-theme', 'dark')
  else document.body.removeAttribute('arco-theme')
}

export const getThemeMode = (): ThemeMode => {
  try {
    const raw = String(localStorage.getItem(THEME_MODE_KEY) || '').trim()
    if (raw === 'light' || raw === 'dark' || raw === 'system') return raw
  } catch {
    // ignore
  }
  return 'system'
}

export const applyThemeMode = (mode: ThemeMode) => {
  if (typeof window === 'undefined') return

  if (media && mediaListener) {
    try {
      if (typeof media.removeEventListener === 'function') media.removeEventListener('change', mediaListener)
      else if (typeof (media as any).removeListener === 'function') (media as any).removeListener(mediaListener)
    } catch {
      // ignore
    }
  }
  media = null
  mediaListener = null

  if (mode === 'dark') {
    setArcoThemeAttr(true)
    return
  }

  if (mode === 'light') {
    setArcoThemeAttr(false)
    return
  }

  media = window.matchMedia?.('(prefers-color-scheme: dark)') || null
  if (!media) return

  const apply = (isDark: boolean) => setArcoThemeAttr(isDark)
  mediaListener = (e: MediaQueryListEvent) => apply(e.matches)

  if (document.body) apply(media.matches)
  else window.addEventListener('DOMContentLoaded', () => apply(media?.matches || false), { once: true })

  if (typeof media.addEventListener === 'function') media.addEventListener('change', mediaListener)
  else if (typeof (media as any).addListener === 'function') (media as any).addListener(mediaListener)
}

export const setThemeMode = (mode: ThemeMode) => {
  try {
    localStorage.setItem(THEME_MODE_KEY, mode)
  } catch {
    // ignore
  }
  applyThemeMode(mode)
}

export const initTheme = () => {
  applyThemeMode(getThemeMode())
}

