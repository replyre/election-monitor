/// <reference types="vitest" />
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { fileURLToPath, URL } from "node:url";

// `npm run dev` proxies the API to a running `python -m scripts.demo` (port 8787 by default).
const api = process.env.PULSE_API ?? "http://127.0.0.1:8787";

export default defineConfig(({ command }) => ({
  // Served at /field/ beside the core app, whose own assets sit at /assets/.
  base: command === "build" ? "/field/" : "/",
  plugins: [react()],
  resolve: { alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) } },
  server: {
    port: 5173,
    proxy: { "/acs": api, "/demo/api": api },
  },
  // No source maps in the built app: they would publish the source.
  build: { outDir: "dist", sourcemap: false, chunkSizeWarningLimit: 1500 },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test/setup.ts"],
    include: ["src/**/*.test.{ts,tsx}"],
    css: false,
  },
}));
