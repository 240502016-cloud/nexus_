import react from "@vitejs/plugin-react";
import { defineConfig, loadEnv } from "vite";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, ".", "");
  return {
    // Web production keeps root-relative assets; the packaged nexus:// origin needs relative assets.
    base: mode === "desktop" ? "./" : "/",
    plugins: [
      react(),
      {
        // Production'da /lab yolunu nginx lab.html'e yönlendirir (frontend/nginx.conf).
        // Dev sunucusunda aynı adresin çalışması için eşdeğer yönlendirme burada yapılır;
        // böylece "Lab" düğmesi geliştirmede de üretimdeki adresi açar.
        name: "nexus-lab-dev-route",
        configureServer(server) {
          server.middlewares.use((req, _res, next) => {
            // Bu projede @types/node bağımlılığı yok; istek nesnesi yalnız `url` için daraltılır.
            const request = req as unknown as { url?: string };
            const [path, query] = (request.url ?? "").split("?");
            if (path === "/lab" || path === "/lab/") {
              request.url = query ? `/lab.html?${query}` : "/lab.html";
            }
            next();
          });
        },
      },
    ],
    build: {
      rollupOptions: {
        input: {
          // Ana istemci ve Nexus Lab ayrı belgelerdir: Lab kendi penceresinde açılır ve
          // ana uygulamanın paketini büyütmez. Aynı origin oldukları için oturum ortaktır.
          main: "index.html",
          lab: "lab.html",
        },
      },
    },
    server: {
      // Allow other devices on the LAN to open the dev client.
      host: "0.0.0.0",
      port: 5173,
      proxy: {
        "/api": {
          target: env.NEXUS_DEV_API_TARGET ?? "http://localhost:8000",
          changeOrigin: true,
          ws: true,
          rewrite: (path) => path.replace(/^\/api/, ""),
        },
      },
    },
  };
});
