import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  build: {
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (id.includes("node_modules")) {
            if (id.includes("recharts")) return "charts";
            if (id.includes("lucide-react")) return "icons";
            if (id.includes("react")) return "vendor";
            return "vendor";
          }
          if (id.includes("/src/planningGoals")) return "planning-goals";
          if (id.includes("/src/visualizationSeries")) return "visualization-series";
          if (id.includes("/src/coreObjects")) return "core-objects";
          if (id.includes("/src/generatedStrategies")) return "generated-strategies";
          if (id.includes("/src/api")) return "api";
        }
      }
    }
  },
  server: {
    host: "127.0.0.1",
    port: 5173
  }
});
