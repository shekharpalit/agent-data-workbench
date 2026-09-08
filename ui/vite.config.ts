import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig(({ mode }) => {
  const development = mode === "development";
  return {
    plugins: [react()],
    build: {
      outDir: "dist",
      // FastAPI serves the previous build while the watcher writes the next one.
      emptyOutDir: !development,
      sourcemap: false,
      watch: development
        ? {
            exclude: ["**/node_modules/**", "**/dist/**"],
            buildDelay: 100,
            // Vite adapts these options to Rolldown's filesystem watcher.
            chokidar: { usePolling: true, interval: 300 },
          }
        : null,
    },
  };
});
