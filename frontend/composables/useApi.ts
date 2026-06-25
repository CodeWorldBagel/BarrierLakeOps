// 統一的後端 REST 取用(base = NUXT_PUBLIC_API_BASE)
export const useApi = () => {
  const base = useRuntimeConfig().public.apiBase as string;

  const get = <T = any>(path: string) => $fetch<T>(base + path);
  const post = <T = any>(path: string, body: any) =>
    $fetch<T>(base + path, { method: "POST", body });
  const patch = <T = any>(path: string, body: any) =>
    $fetch<T>(base + path, { method: "PATCH", body });

  return {
    base,
    health: () => get("/health"),
    // 資料同步
    dataStatus: () => get("/data/status"),
    triggerSync: () => post("/data/sync", {}),
    patchLakeState: (id: string, body: any) => patch(`/data/lake-state/${id}`, body),
    patchLakeThreshold: (id: string, body: any) => patch(`/data/lake-threshold/${id}`, body),
    uploadLakes: (file: File) => {
      const fd = new FormData();
      fd.append("file", file);
      return $fetch(base + "/data/lakes/upload", { method: "POST", body: fd });
    },
    listLakes: (filter = "all") => get(`/lakes?status_filter=${filter}`),
    lakeStatus: (id: string) => get(`/lakes/${id}/status`),
    lakeWeather: (id: string) => get(`/lakes/${id}/weather`),
    inundation: (id: string, breach_scenario = "full") =>
      post(`/lakes/${id}/inundation`, { breach_scenario }),
    population: (polygon: any) => post(`/population`, { polygon }),
    briefing: (context: any, audience = "command_center", lake_id?: string) =>
      post(`/briefing`, { context, audience, lake_id }),
    listBriefings: (id: string) => get(`/lakes/${id}/briefings`),
    getBriefing: (bid: string) => get(`/briefings/${bid}`),
    chatHistory: (sid: string) => get(`/chat/sessions/${sid}`),
  };
};

export const alertText: Record<string, string> = {
  red: "紅色警戒",
  orange: "橙色警戒",
  yellow: "黃色警戒",
  green: "綠色",
  unknown: "未知",
};
