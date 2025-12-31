import { createApp } from 'vue'
import App from './App.vue'
import router from './router'

import ArcoVue from '@arco-design/web-vue'
import ArcoVueIcon from '@arco-design/web-vue/es/icon'

import '@arco-design/web-vue/dist/arco.css'
import './style.css'

const applySystemTheme = () => {
  if (typeof window === 'undefined') return

  const set = (isDark: boolean) => {
    if (!document.body) return
    if (isDark) {
      document.body.setAttribute('arco-theme', 'dark')
    } else {
      document.body.removeAttribute('arco-theme')
    }
  }

  const media = window.matchMedia?.('(prefers-color-scheme: dark)')
  if (!media) return

  if (document.body) {
    set(media.matches)
  } else {
    window.addEventListener('DOMContentLoaded', () => set(media.matches), { once: true })
  }
  if (typeof media.addEventListener === 'function') {
    media.addEventListener('change', (e) => set((e as MediaQueryListEvent).matches))
  } else if (typeof (media as any).addListener === 'function') {
    ;(media as any).addListener((e: MediaQueryListEvent) => set(e.matches))
  }
}

applySystemTheme()

const app = createApp(App)
app.use(ArcoVue)
app.use(ArcoVueIcon)
app.use(router)
app.mount('#app')
