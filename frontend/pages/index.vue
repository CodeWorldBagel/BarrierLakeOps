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

    <div class="panel panel-pad overview">
      <div class="head">
        <h3>全台堰塞湖概覽摘要</h3>
        <button class="btn sm" :disabled="ovLoading" @click="genOverview">重新生成</button>
      </div>
      <BriefingCard :b="overview" :loading="ovLoading" />
      <div class="muted note">
        共 {{ lakes.length }} 座可查詢 · 紅色警戒 {{ counts.red }} · 橙 {{ counts.orange }} ·
        資料來源:data.moa 國有林堰塞湖 + Lake Catalog
      </div>
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

const overview = ref<any>(null);
const ovLoading = ref(false);
async function genOverview() {
  ovLoading.value = true;
  try {
    const ctx = {
      lakes: lakes.value.map((l) => ({
        name: l.name,
        alert_level: l.alert_level,
        headroom_m: l.headroom_m,
        status: l.status,
      })),
      data_sources: [
        { source: "農業資料開放平臺 — 國有林堰塞湖資訊", license: "政府資料開放授權條款 1.0" },
      ],
    };
    const r: any = await api.briefing(ctx, "multi_lake_overview");
    overview.value = r.briefing;
  } catch {
    overview.value = null;
  } finally {
    ovLoading.value = false;
  }
}
onMounted(() => {
  if (lakes.value.length) genOverview();
});
</script>

<style scoped>
.dash { padding: 18px 22px; max-width: 1320px; margin: 0 auto; }
.grid { display: grid; grid-template-columns: 320px 1fr; gap: 16px; height: 60vh; min-height: 440px; }
.grid > * { min-height: 0; }
.mapwrap { overflow: hidden; }
.overview { margin-top: 18px; }
.overview .head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 10px; }
.overview .note { font-size: 11.5px; margin-top: 10px; }
@media (max-width: 1024px) {
  .grid { grid-template-columns: 1fr; height: auto; }
  .mapwrap { height: 360px; }
}
</style>
