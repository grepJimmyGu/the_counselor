import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import { fileURLToPath } from "node:url";

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": fileURLToPath(new URL("./src", import.meta.url)),
    },
  },
  test: {
    environment: "jsdom",
    globals: false,
    include: ["src/**/*.{test,spec}.{ts,tsx}"],
    // Pre-existing `node --experimental-strip-types` scripts that use
    // node:assert rather than vitest suites. Out of PRD-13a scope to
    // migrate; revisit when the surrounding modules see real changes.
    exclude: [
      "**/node_modules/**",
      "src/lib/strategy-picker/risk-presets.test.ts",
      "src/components/market-pulse/top-movers-selection.test.ts",
      "src/components/strategy-builder/wizard/strategy-wizard-recommend.test.ts",
    ],
    setupFiles: ["./vitest.setup.ts"],
  },
});
