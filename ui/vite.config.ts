import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  build: {
    outDir: "../src/agent_data_workbench/web",
    emptyOutDir: true,
    sourcemap: false,
  },
});
