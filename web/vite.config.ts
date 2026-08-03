import react from "@vitejs/plugin-react";
import process from "node:process";
import type { Plugin } from "vite";
import { defineConfig } from "vitest/config";
import { CONTENT_SECURITY_POLICY } from "./src/csp";

/** Where `npm run dev` sends `/api` and `/mcp`, so the SPA is same-origin in development too. */
const HUB = process.env.HUB_ORIGIN ?? "http://127.0.0.1:8000";

/**
 * Injects the CSP into the built `index.html` only.
 *
 * The dev server serves inline module scripts, so a policy strict enough to be worth having
 * cannot also apply in development.
 */
function contentSecurityPolicy(): Plugin {
  return {
    name: "hub-csp",
    apply: "build",
    transformIndexHtml(html) {
      return {
        html,
        tags: [
          {
            tag: "meta",
            attrs: {
              "http-equiv": "Content-Security-Policy",
              content: CONTENT_SECURITY_POLICY,
            },
            injectTo: "head-prepend",
          },
        ],
      };
    },
  };
}

export default defineConfig({
  plugins: [react(), contentSecurityPolicy()],
  server: {
    proxy: {
      "/api": { target: HUB, changeOrigin: true },
      "/mcp": { target: HUB, changeOrigin: true },
    },
  },
  build: { outDir: "dist", sourcemap: true },
  test: {
    environment: "jsdom",
    setupFiles: ["./src/test-setup.ts"],
    css: false,
  },
});
