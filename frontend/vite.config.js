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
      // All backend routes under /api — SPA owns /auth/callback, /projects, /documents, etc.
      "/api": "http://localhost:8000",
    },
  },
  define: {
    // amazon-cognito-identity-js uses Node.js globals — polyfill for browser
    global: "globalThis",
  },
});
