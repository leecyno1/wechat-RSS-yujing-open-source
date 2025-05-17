import { defineConfig, loadEnv } from 'vite'
import vue from '@vitejs/plugin-vue'
import { fileURLToPath, URL } from 'node:url'

export default defineConfig(({ command, mode }) => {
  // 加载环境变量
  const env = loadEnv(mode, process.cwd(), '')

  return {
    plugins: [vue()],
    resolve: {
      alias: {
        '@': fileURLToPath(new URL('./src', import.meta.url))
      }
    },
    // 基础路径配置
    base: command === 'serve' ? '/' : '/',
    // 开发服务器配置
    // 构建配置
    build: {
      outDir: '../static',
      emptyOutDir: true,
      assetsDir: 'assets'
    }
  }
})