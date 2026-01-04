export type ThemeMode = 'system' | 'light' | 'dark'

const THEME_MODE_KEY = 'theme_mode'

let media: MediaQueryList | null = null
let mediaListener: ((e: MediaQueryListEvent) => void) | null = null

const setArcoThemeAttr = (isDark: boolean) => {
  if (!document?.body) return
  if (isDark) document.body.setAttribute('arco-theme', 'dark')
  else document.body.removeAttribute('arco-theme')
}

const setColorScheme = (isDark: boolean) => {
  const scheme = isDark ? 'dark' : 'light'
  try {
    document.documentElement.style.colorScheme = scheme
  } catch {
    // ignore
  }

  const applyBody = () => {
    try {
      document.body.style.colorScheme = scheme
    } catch {
      // ignore
    }
  }

  if (document.body) applyBody()
  else {
    let tries = 0
    const tick = () => {
      tries += 1
      if (document.body) return applyBody()
      if (tries < 60) setTimeout(tick, 16)
    }
    tick()
  }
}

const applyTheme = (isDark: boolean) => {
  setColorScheme(isDark)
  if (document.body) setArcoThemeAttr(isDark)
  else {
    // If body isn't ready (e.g. script in <head>), retry until it exists.
    let tries = 0
    const tick = () => {
      tries += 1
      if (document.body) return setArcoThemeAttr(isDark)
      if (tries < 60) setTimeout(tick, 16)
    }
    tick()
  }
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
    applyTheme(true)
    return
  }

  if (mode === 'light') {
    applyTheme(false)
    return
  }

  media = window.matchMedia?.('(prefers-color-scheme: dark)') || null
  if (!media) return

  mediaListener = (e: MediaQueryListEvent) => applyTheme(e.matches)

  applyTheme(media.matches)

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
