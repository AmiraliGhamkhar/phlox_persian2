/// <reference types="vitest/config" />
import { defineConfig, normalizePath } from "vite";
import react from "@vitejs/plugin-react";
import { readFileSync } from "fs";
import { fileURLToPath, URL } from "node:url";
import path from "node:path";
import { createRequire } from "node:module";
import { viteStaticCopy } from "vite-plugin-static-copy";

// Read version from package.json at build time
const pkg = JSON.parse(readFileSync("./package.json", "utf-8"));

const require = createRequire(import.meta.url);
const pdfjsDistPath = path.dirname(require.resolve("pdfjs-dist/package.json"));
const wasmDir = normalizePath(path.relative(process.cwd(), path.join(pdfjsDistPath, "wasm")));
const cmapsDir = normalizePath(path.relative(process.cwd(), path.join(pdfjsDistPath, "cmaps")));
const standardFontsDir = normalizePath(
  path.relative(process.cwd(), path.join(pdfjsDistPath, "standard_fonts")),
);

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [
    react(),
    viteStaticCopy({
      targets: [
        { src: `${wasmDir}/*`, dest: "wasm", rename: { stripBase: true } },
        { src: `${cmapsDir}/*`, dest: "cmaps", rename: { stripBase: true } },
        {
          src: `${standardFontsDir}/*`,
          dest: "standard_fonts",
          rename: { stripBase: true },
        },
      ],
    }),
  ],

  define: {
    __APP_VERSION__: JSON.stringify(pkg.version),
  },

  resolve: {
    alias: {
      "@": fileURLToPath(new URL("./src", import.meta.url)),
    },
  },

  build: {
    // Build output directory must be 'build' for Tauri compatibility
    outDir: "build",
    emptyOutDir: true,
    rollupOptions: {
      output: {
        // Extract the React runtime into its own long-lived chunk. React,
        // react-dom and react-router change far less often than app code, so
        // this chunk stays cached in users' browsers/Tauri webview across app
        // releases instead of being re-downloaded inside the hashed `index`
        // chunk on every deploy.
        //
        // Deliberately SCOPED to React only:
        //  - Match on node_modules/<pkg>/ path *boundaries* with a regex; a loose
        //    substring like "/react/" also matches @tauri-apps/plugin-http and
        //    react-markdown, silently ballooning the chunk.
        //  - Chakra UI / @emotion / react-icons are intentionally left in the
        //    app chunks: splitting them into a separate vendor chunk measured
        //    *larger* initial JS (extra wrapper/runtime duplication) and merely
        //    moved the >500 kB warning to a different file - they also track
        //    app-code versions, so a vendor split gave no caching benefit.
        //  - Libraries the app loads lazily via dynamic import (pdfjs-dist) or
        //    that are reachable only from lazy routes (pdf-lib, react-markdown)
        //    are left undefined so rolldown keeps them in on-demand chunks.
        manualChunks(id) {
          if (!id.includes("node_modules")) return undefined;
          if (/node_modules\/(react|react-dom|react-router|scheduler)\//.test(id)) {
            return "vendor-react";
          }
          return undefined;
        },
      },
    },
  },

  test: {
    environment: "jsdom",
    setupFiles: ["./src/test/setup.js"],
  },


  optimizeDeps: {
    entries: ["index.html"],
  },

  server: {
    host: "0.0.0.0",
    port: 3000,
    strictPort: true,
    // Arena's proxied preview hostname is dynamic; let Vite accept it.
    allowedHosts: true,
    // Proxy API calls to the backend
    proxy: {
      "/api": {
        target: "http://localhost:5000",
        changeOrigin: true,
      },
    },

    watch: {
      ignored: [
        "**/build-dir/**",
        "**/.flatpak-builder/**",
        "**/src-tauri/llama.cpp/**",
        "**/src-tauri/whisper.cpp/**",
        "**/src-tauri/target/**",
      ],
    },
  },
});
