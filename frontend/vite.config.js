import path from "path";
import { defineConfig } from "vite";

export default defineConfig({
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  server: {
    port: 5173,
    proxy: {
      // Proxy only specific backend API routes — NOT /auth/callback (React Router owns that)
      "/auth/me": "http://localhost:8000",
      "/query": "http://localhost:8000",
      "/documents": "http://localhost:8000",
      "/projects": "http://localhost:8000",
      "/health": "http://localhost:8000",
      "/upload": "http://localhost:8000",
      "/admin": "http://localhost:8000",
    },
  },
  define: {
    // amazon-cognito-identity-js uses Node.js globals — polyfill for browser
    global: "globalThis",
  },
});
