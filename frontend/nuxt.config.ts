// https://nuxt.com/docs/api/configuration/nuxt-config
export default defineNuxtConfig({
  compatibilityDate: "2025-06-01",
  devtools: { enabled: false },
  css: ["leaflet/dist/leaflet.css", "~/assets/css/main.css"],
  runtimeConfig: {
    public: {
      apiBase: process.env.NUXT_PUBLIC_API_BASE || "http://localhost:8000",
      mapTileUrl:
        process.env.NUXT_PUBLIC_MAP_TILE_URL ||
        "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
      mapAttribution:
        process.env.NUXT_PUBLIC_MAP_ATTRIBUTION || "© OpenStreetMap contributors",
    },
  },
  app: {
    head: {
      title: "BarrierLakeOps — 堰湖態勢跨部會研判",
      htmlAttrs: { lang: "zh-Hant" },
      meta: [
        { charset: "utf-8" },
        { name: "viewport", content: "width=device-width, initial-scale=1" },
        {
          name: "description",
          content: "堰塞湖跨部會即時態勢研判 — 湖清單、地圖、潰壩淹水推估與 AI 作戰助手。",
        },
      ],
      link: [
        { rel: "preconnect", href: "https://fonts.googleapis.com" },
        { rel: "preconnect", href: "https://fonts.gstatic.com", crossorigin: "" },
        {
          rel: "stylesheet",
          href: "https://fonts.googleapis.com/css2?family=Noto+Sans+TC:wght@400;500;600;700&family=Noto+Serif+TC:wght@500;600;700&display=swap",
        },
      ],
    },
  },
});
