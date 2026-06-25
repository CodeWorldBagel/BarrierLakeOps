<template>
  <div class="war">
    <div class="cols">
      <!-- 左:狀態 / 上游雨量 / 淹水推估 -->
      <div class="col scroll">
        <StatusCards :status="status" />
        <WeatherPanel :weather="weather" />
        <InundationPanel @ask="onInundationAsk" />
      </div>

      <!-- 中:地圖(淹水圖層由 Chat 推估結果套疊) -->
      <div class="col mapcol">
        <div class="panel mapwrap">
          <ClientOnly>
            <LakeMap
              :lakes="mapLakes"
              :inundation="inundationFeature"
              :envelope="envelopeFeature"
              :lake-id="id"
              :center="center"
              :zoom="12"
            />
          </ClientOnly>
        </div>
      </div>

      <!-- 右:Chat 作戰助手(淹水/人口/摘要皆透過對話與快速鍵呈現) -->
      <div class="col chatcol">
        <ChatPanel ref="chatRef" :lake-id="id" @inundation="onInundation" @envelope="onEnvelope" />
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

// 淹水圖層 + 安全包絡線:由 ChatPanel 的 estimate_inundation 工具結果回填
const inundationFeature = ref<any>(null);
const envelopeFeature = ref<any>(null);
const onInundation = (polygon: any) => (inundationFeature.value = polygon);
const onEnvelope = (polygon: any) => (envelopeFeature.value = polygon);

// 左欄「推估淹水」按鈕 → 模擬使用者在右側對話送出訊息(走 function call,
// 結果同時套疊地圖 + 由 AI 回覆),左欄不展開、不跑版。
const chatRef = ref<{ ask: (p: string) => void } | null>(null);
const onInundationAsk = (prompt: string) => chatRef.value?.ask(prompt);
</script>

<style scoped>
.war { height: calc(100vh - 53px); display: flex; flex-direction: column; padding: 12px 16px; gap: 12px; }
.cols { flex: 1; display: grid; grid-template-columns: 340px 1fr 420px; gap: 12px; min-height: 0; }
.col { display: flex; flex-direction: column; gap: 12px; min-height: 0; }
.col.scroll { overflow-y: auto; padding-right: 4px; }
.mapcol { min-height: 0; }
.mapwrap { flex: 1; min-height: 0; overflow: hidden; }
.chatcol { min-height: 0; }
@media (max-width: 1200px) {
  .cols { grid-template-columns: 1fr; overflow-y: auto; }
  .war { height: auto; }
  .mapcol { height: 360px; }
  .chatcol { height: 600px; }
}
</style>
