<template>
  <div class="dash">
    <div class="grid">
      <LakeListPanel
        :lakes="filtered"
        :active-filters="activeFilters"
        :selected="selectedId"
        @toggle="toggleFilter"
      />
      <div class="mapwrap panel">
        <ClientOnly>
          <LakeMap :lakes="filtered" :selected-id="selectedId" :center="center" @select="goLake" />
          <template #fallback><div class="panel-pad muted">地圖載入中…</div></template>
        </ClientOnly>
      </div>
    </div>

    <div class="statsbar muted">
      共 {{ lakes.length }} 座可查詢 · 紅色警戒 {{ counts.red }} · 橙色 {{ counts.orange }}
      · 資料來源:data.moa 國有林堰塞湖 + Lake Catalog
    </div>
  </div>
</template>

<script setup lang="ts">
const api = useApi();
const activeFilters = ref<string[]>(["alert", "monitoring"]);
const { data: lakesData } = await useAsyncData("lakes", () => api.listLakes("all"));
const lakes = computed<any[]>(() => (lakesData.value as any)?.lakes || []);

const matchers: Record<string, (l: any) => boolean> = {
  alert: (l) => l.alert_level === "red",
  monitoring: (l) => l.status === "monitoring" && l.alert_level !== "red",
  archived: (l) => l.status === "archived",
};
const filtered = computed(() =>
  activeFilters.value.length
    ? lakes.value.filter((l) => activeFilters.value.some((f) => matchers[f]?.(l)))
    : [],
);
const selectedId = computed(() => lakes.value[0]?.id);
const center = computed<[number, number] | undefined>(() => {
  const l = lakes.value[0];
  return l && l.lat != null ? [l.lat, l.lon] : undefined;
});
const counts = computed(() => ({
  red: lakes.value.filter((l) => l.alert_level === "red").length,
  orange: lakes.value.filter((l) => l.alert_level === "orange").length,
}));

const toggleFilter = (v: string) => {
  const i = activeFilters.value.indexOf(v);
  if (i === -1) activeFilters.value = [...activeFilters.value, v];
  else activeFilters.value = activeFilters.value.filter((f) => f !== v);
};
const goLake = (id: string) => navigateTo(`/lakes/${id}`);
</script>

<style scoped>
.dash { padding: 16px 24px 14px; }
.grid {
  display: grid; grid-template-columns: 340px 1fr; gap: 16px;
  height: calc(100vh - 140px); min-height: 480px;
}
.grid > * { min-height: 0; }
.mapwrap { overflow: hidden; }
.statsbar { margin-top: 12px; font-size: 12px; text-align: center; }
@media (max-width: 1024px) {
  .grid { grid-template-columns: 1fr; height: auto; }
  .mapwrap { height: 420px; }
}
</style>
