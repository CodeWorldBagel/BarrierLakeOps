import { buildFloodCellPopupHtml } from "~/utils/floodCellPopup";

type FloodCellClickOptions = {
  L: any;
  map: any;
  api: ReturnType<typeof useApi>;
  getLakeId: () => string | undefined;
  debounceMs?: number;
};

export function setupFloodCellClick({
  L,
  map,
  api,
  getLakeId,
  debounceMs = 300,
}: FloodCellClickOptions): { cleanup: () => void } {
  let clickTimer: ReturnType<typeof setTimeout> | null = null;
  let clickAbort: AbortController | null = null;

  const cancelPending = () => {
    if (clickAbort) {
      clickAbort.abort();
      clickAbort = null;
    }
    if (clickTimer) {
      clearTimeout(clickTimer);
      clickTimer = null;
    }
  };

  const onClick = (e: any) => {
    const lakeId = getLakeId();
    if (!lakeId) return;

    cancelPending();
    clickTimer = setTimeout(async () => {
      const { lat, lng } = e.latlng;
      const controller = new AbortController();
      clickAbort = controller;
      try {
        const result = await api.explainFloodCell(lakeId, lng, lat, controller.signal);
        if (controller.signal.aborted) return;
        L.popup({ maxWidth: 300 })
          .setLatLng(e.latlng)
          .setContent(buildFloodCellPopupHtml(result))
          .openOn(map);
      } catch (err: any) {
        if (err?.name === "AbortError") return;
      } finally {
        if (clickAbort === controller) clickAbort = null;
      }
    }, debounceMs);
  };

  map.on("click", onClick);

  return {
    cleanup: () => {
      cancelPending();
      map.off("click", onClick);
    },
  };
}
