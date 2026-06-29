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
    uploadLakes: (file: File, force = false, skipIds?: string[]) => {
      const form = new FormData();
      form.append("file", file);
      const params = new URLSearchParams();
      if (force) params.set("force", "true");
      if (skipIds?.length) params.set("skip", skipIds.join(","));
      return $fetch(`${base}/data/lakes/upload?${params}`, { method: "POST", body: form });
    },
    listLakes: (filter = "all") => get(`/lakes?status_filter=${filter}`),
    lakeStatus: (id: string) => get(`/lakes/${id}/status`),
    lakeWeather: (id: string) => get(`/lakes/${id}/weather`),
    inundation: (
      id: string,
      breach_scenario = "full",
      options: { model_variant?: string } = {},
    ) => post(`/lakes/${id}/inundation`, { breach_scenario, ...options }),
    population: (polygon: any) => post(`/population`, { polygon }),
    briefing: (context: any, audience = "command_center", lake_id?: string) =>
      post(`/briefing`, { context, audience, lake_id }),
    listBriefings: (id: string) => get(`/lakes/${id}/briefings`),
    getBriefing: (bid: string) => get(`/briefings/${bid}`),
    chatHistory: (sid: string) => get(`/chat/sessions/${sid}`),
    explainFloodCell: (lakeId: string, lon: number, lat: number, signal?: AbortSignal) =>
      $fetch<any>(`${base}/lakes/${lakeId}/explain_cell?lon=${lon}&lat=${lat}`, { signal }),
  };
};

export const alertText: Record<string, string> = {
  red: "紅色警戒",
  orange: "橙色警戒",
  yellow: "黃色警戒",
  green: "綠色",
  unknown: "未知",
};
