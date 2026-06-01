<template>
  <div class="dash">
    <div class="grid">
      <LakeListPanel
        :lakes="filtered"
        :model-filter="filter"
        :selected="selectedId"
        @filter="setFilter"
      />
      <div class="mapwrap panel">
        <ClientOnly>
          <LakeMap :lakes="lakes" :selected-id="selectedId" :center="center" @select="goLake" />
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
const filter = ref("all");
const { data: lakesData } = await useAsyncData("lakes", () => api.listLakes("all"));
const lakes = computed<any[]>(() => (lakesData.value as any)?.lakes || []);

const filtered = computed(() =>
  filter.value === "all" ? lakes.value : lakes.value.filter((l) => l.status === filter.value),
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

const setFilter = (v: string) => (filter.value = v);
const goLake = (id: string) => navigateTo(`/lakes/${id}`);
</script>

<style scoped>
.dash { padding: 18px 22px; max-width: 1320px; margin: 0 auto; }
.grid { display: grid; grid-template-columns: 320px 1fr; gap: 16px; height: 64vh; min-height: 460px; }
.grid > * { min-height: 0; }
.mapwrap { overflow: hidden; }
.statsbar { margin-top: 14px; font-size: 12px; text-align: center; }
@media (max-width: 1024px) {
  .grid { grid-template-columns: 1fr; height: auto; }
  .mapwrap { height: 360px; }
}
</style>
