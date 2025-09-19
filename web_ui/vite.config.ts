import { defineConfig, loadEnv } from "vite";
import vue from "@vitejs/plugin-vue";
import { fileURLToPath, URL } from "node:url";

export default defineConfig(({ command, mode }) => {
  // 加载环境变量
  const env = loadEnv(mode, process.cwd(), "");

  return {
    plugins: [vue()],
    resolve: {
      alias: {
        "@": fileURLToPath(new URL("./src", import.meta.url)),
      },
    },
    // 基础路径配置
    base: command === "serve" ? "/" : "/",
    // 开发服务器配置
    // 构建配置
    build: {
      outDir: "dist",
      emptyOutDir: true,
      assetsDir: "assets",
      // 确保资源路径使用相对路径，适合 Flutter WebView 加载
      rollupOptions: {
        output: {
          manualChunks: undefined,
        },
      },
    },
    server: {
      host: "0.0.0.0",
      port: 3000,
      proxy: {
        "/static": {
          target: env.VITE_API_BASE_URL,
          changeOrigin: true,
        },
        "/files": {
          target: env.VITE_API_BASE_URL,
          changeOrigin: true,
        },
        "/rss": {
          target: env.VITE_API_BASE_URL,
          changeOrigin: true,
        },
        "/feed": {
          target: env.VITE_API_BASE_URL,
          changeOrigin: true,
        },
        "/api": {
          target: env.VITE_API_BASE_URL,
          changeOrigin: true,
        },
      },
    },
  };
});