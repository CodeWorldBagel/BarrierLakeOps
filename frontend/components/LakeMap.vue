<template>
  <div ref="el" class="map" />
</template>

<script setup lang="ts">
const props = defineProps<{
  lakes?: any[];
  inundation?: any;
  envelope?: any;
  lakeId?: string;
  selectedId?: string;
  center?: [number, number];
  zoom?: number;
}>();
const emit = defineEmits<{ select: [id: string] }>();

const el = ref<HTMLElement | null>(null);
let map: any = null;
let L: any = null;
let markerLayer: any = null;
let floodLayer: any = null;
let envelopeLayer: any = null;
let ro: any = null;
let floodCellClick: { cleanup: () => void } | null = null;

// 與清單徽章一致(文青霧霾調)
const alertColors: Record<string, string> = {
  red: "#c0584f",
  orange: "#cf8a4e",
  yellow: "#c2a13a",
  green: "#6f9669",
};
const statusColors: Record<string, string> = {
  active: "#5f8a7d",
  monitoring: "#5878a0", // 觀察中 → 霧霾藍
  archived: "#b6ab93", // 已解除 → 暖灰
};
function markerColor(lk: any): string {
  if (lk.alert_level && lk.alert_level !== "unknown")
    return alertColors[lk.alert_level] || "#938a78";
  return statusColors[lk.status] || "#938a78";
}

const cfg = useRuntimeConfig().public;

onMounted(async () => {
  L = (await import("leaflet")).default;
  map = L.map(el.value!, { zoomControl: true }).setView(
    props.center || [23.7, 121.3],
    props.zoom || 8,
  );
  L.tileLayer(cfg.mapTileUrl as string, {
    attribution: cfg.mapAttribution as string,
    maxZoom: 18,
  }).addTo(map);
  markerLayer = L.layerGroup().addTo(map);
  floodLayer = L.layerGroup().addTo(map);
  envelopeLayer = L.layerGroup().addTo(map);
  renderMarkers();
  renderFlood();
  renderEnvelope();

  floodCellClick = setupFloodCellClick({
    L,
    map,
    api: useApi(),
    getLakeId: () => props.lakeId,
  });
  // grid/flex 容器在 mount 後才定尺寸,Leaflet 需重新計算避免灰底
  setTimeout(() => map && map.invalidateSize(), 200);
  if (typeof ResizeObserver !== "undefined" && el.value) {
    ro = new ResizeObserver(() => map && map.invalidateSize());
    ro.observe(el.value);
  }
});

function renderMarkers() {
  if (!map || !markerLayer) return;
  markerLayer.clearLayers();
  (props.lakes || []).forEach((lk) => {
    if (lk.lat == null || lk.lon == null) return;
    const c = markerColor(lk);
    const m = L.circleMarker([lk.lat, lk.lon], {
      radius: lk.id === props.selectedId ? 10 : 7,
      color: "#fffdf8",
      weight: 2,
      fillColor: c,
      fillOpacity: 0.95,
    }).addTo(markerLayer);
    m.bindTooltip(
      `${lk.name}${lk.headroom_m != null ? " · headroom " + lk.headroom_m + "m" : ""}`,
    );
    m.on("click", () => emit("select", lk.id));
  });
}

function renderFlood() {
  if (!map || !floodLayer) return;
  floodLayer.clearLayers();
  if (!props.inundation || !props.inundation.geometry) return;
  const layer = L.geoJSON(props.inundation, {
    style: { color: "#3d7d9a", weight: 1, fillColor: "#5a9bbd", fillOpacity: 0.38 },
  }).addTo(floodLayer);
  try {
    map.fitBounds(layer.getBounds(), { padding: [30, 30], maxZoom: 13 });
  } catch {
    /* empty geometry */
  }
}

function renderEnvelope() {
  if (!map || !envelopeLayer) return;
  envelopeLayer.clearLayers();
  if (!props.envelope || !props.envelope.geometry) return;
  L.geoJSON(props.envelope, {
    style: {
      color: "#3d7d9a", weight: 1, dashArray: "5,5",
      fillColor: "#5a9bbd", fillOpacity: 0.10,
    },
  }).addTo(envelopeLayer);
}

watch(() => props.lakes, renderMarkers, { deep: true });
watch(() => props.selectedId, renderMarkers);
watch(() => props.inundation, renderFlood, { deep: true });
watch(() => props.envelope, renderEnvelope, { deep: true });
watch(
  () => props.center,
  (c) => {
    if (map && c) map.flyTo(c, 12, { duration: 0.8 });
  },
);

onBeforeUnmount(() => {
  if (floodCellClick) {
    floodCellClick.cleanup();
    floodCellClick = null;
  }
  if (ro) ro.disconnect();
  if (map) map.remove();
});
</script>

<style scoped>
.map {
  width: 100%;
  height: 100%;
  min-height: 320px;
  border-radius: 12px;
  z-index: 1;
}
</style>
