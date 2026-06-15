<template>
  <div class="war">
    <div class="cols">
      <!-- 左:標題 / 狀態 / 雨量 / 人口 -->
      <div class="col scroll">
        <StatusCards :status="status" />
        <WeatherPanel :weather="weather" />
        <PopulationTable :pop="population" />
      </div>

      <!-- 中:只放地圖 -->
      <div class="col mapcol">
        <div class="panel mapwrap">
          <ClientOnly>
            <LakeMap :lakes="mapLakes" :inundation="inundationFeature" :center="center" :zoom="12" />
          </ClientOnly>
        </div>
      </div>

      <!-- 右:Chat(上) + 淹水/摘要(下) -->
      <div class="col rightcol">
        <div class="chatwrap">
          <ChatPanel :lake-id="id" />
        </div>
        <div class="rightlower scroll">
          <div class="panel panel-pad controls">
            <div class="row">
              <label class="muted">潰壩情境</label>
              <select v-model="scenario" class="sel">
                <option value="full">全潰壩 (full)</option>
                <option value="partial">部分潰壩 (partial)</option>
              </select>
              <button class="btn primary" :disabled="floodLoading" @click="estimate">
                {{ floodLoading ? "推估中…" : "推估淹水範圍" }}
              </button>
            </div>
            <div v-if="inundation" class="row stat">
              <span class="tag">最大深度 {{ inundation.max_depth_m_estimate }} m</span>
              <span class="tag">抵達 {{ inundation.leading_edge_arrival_minutes }} 分</span>
            </div>
            <div v-if="inundation" class="disclaimer">⚠ {{ inundation.disclaimer }}</div>
          </div>
          <div class="row genbar">
            <button class="btn" :disabled="brfLoading" @click="genBriefing">生成態勢摘要</button>
            <span class="muted note">彙整狀態 / 雨量 / 淹水 / 人口 → AI 摘要(寫入稽核)</span>
          </div>
          <BriefingCard :b="briefing" :loading="brfLoading" />
          <BriefingHistory :items="history" @replay="replay" />
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
const route = useRoute();
const id = route.params.id as string;
const api = useApi();

const [{ data: status }, { data: weather }, { data: lakesData }] = await Promise.all([
  useAsyncData(`status-${id}`, () => api.lakeStatus(id)),
  useAsyncData(`weather-${id}`, () => api.lakeWeather(id)),
  useAsyncData("lakes-all", () => api.listLakes("all")),
]);

const thisLake = computed(() =>
  ((lakesData.value as any)?.lakes || []).find((l: any) => l.id === id),
);
const mapLakes = computed(() => (thisLake.value ? [thisLake.value] : []));
const center = computed<[number, number] | undefined>(() =>
  thisLake.value && thisLake.value.lat != null
    ? [thisLake.value.lat, thisLake.value.lon]
    : undefined,
);

const scenario = ref("full");
const inundation = ref<any>(null);
const inundationFeature = computed(() => inundation.value?.inundation_polygon);
const population = ref<any>(null);
const floodLoading = ref(false);

async function estimate() {
  floodLoading.value = true;
  try {
    inundation.value = await api.inundation(id, scenario.value);
    population.value = await api.population(inundation.value.inundation_polygon);
  } finally {
    floodLoading.value = false;
  }
}

const briefing = ref<any>(null);
const brfLoading = ref(false);
async function genBriefing() {
  brfLoading.value = true;
  try {
    const ctx: any = { status: status.value, weather: weather.value };
    if (inundation.value)
      ctx.inundation = { ...inundation.value, inundation_polygon: undefined };
    if (population.value) ctx.population = population.value;
    const r: any = await api.briefing(ctx, "command_center", id);
    briefing.value = r.briefing;
    await loadHistory();
  } finally {
    brfLoading.value = false;
  }
}

const history = ref<any[]>([]);
async function loadHistory() {
  try {
    const r: any = await api.listBriefings(id);
    history.value = r.briefings || [];
  } catch {
    history.value = [];
  }
}
async function replay(bid: string) {
  const r: any = await api.getBriefing(bid);
  briefing.value = {
    status_color: r.status_color,
    headline: r.headline,
    key_facts: r.key_facts,
    recommended_actions: r.recommended_actions,
    natural_language: r.natural_language,
    ai_confidence: r.ai_confidence,
    data_sources_used: r.data_sources_used,
  };
}
onMounted(loadHistory);
</script>

<style scoped>
.war { height: calc(100vh - 53px); display: flex; flex-direction: column; padding: 12px 16px; gap: 12px; }
.cols { flex: 1; display: grid; grid-template-columns: 340px 1fr 400px; gap: 12px; min-height: 0; }
.col { display: flex; flex-direction: column; gap: 12px; min-height: 0; }
.col.scroll { overflow-y: auto; padding-right: 4px; }
.mapcol { min-height: 0; }
.mapwrap { flex: 1; min-height: 0; overflow: hidden; }

/* 右欄:Chat 在上、淹水/摘要在下 */
.rightcol { min-height: 0; }
.chatwrap { flex: 1 1 46%; min-height: 240px; display: flex; }
.chatwrap > * { width: 100%; }
.rightlower { flex: 1 1 54%; overflow-y: auto; padding-right: 4px; }
.controls .sel { background: var(--bg-2); color: var(--text); border: 1px solid var(--border); border-radius: 8px; padding: 6px 9px; }
.controls .row { align-items: center; }
.controls .stat { margin-top: 8px; }
.controls .disclaimer { margin-top: 8px; }
.genbar { align-items: center; }
.genbar .note { font-size: 11.5px; }
@media (max-width: 1200px) {
  .cols { grid-template-columns: 1fr; overflow-y: auto; }
  .war { height: auto; }
  .mapcol { height: 360px; }
  .rightcol { height: auto; }
  .chatwrap { flex: none; height: 520px; }
  .rightlower { flex: none; overflow: visible; }
}
</style>
