import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// O build sai direto em `extensao/painel/`, que é o que o manifest carrega.
// Sem isso seria preciso copiar a pasta a cada build, e a cópia esquecida é
// exatamente o tipo de passo que se perde.
export default defineConfig({
  plugins: [react()],
  base: "./", // a página roda em chrome-extension://, onde caminho absoluto quebra
  build: {
    outDir: "../extensao/painel",
    emptyOutDir: true,
    // Um arquivo por tipo, com nome fixo: o manifest referencia o HTML, e
    // hash no nome obrigaria reescrevê-lo a cada build.
    rollupOptions: {
      output: {
        entryFileNames: "painel.js",
        chunkFileNames: "painel-[name].js",
        assetFileNames: "painel.[ext]",
      },
    },
  },
});
