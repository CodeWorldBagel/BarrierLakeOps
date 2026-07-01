<template>
  <div class="war" :class="{ 'mobile-chat-active': mobileChatOpen }">
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
      <div class="col chatcol" :class="{ open: mobileChatOpen }">
        <button class="mobile-chat-close" type="button" aria-label="關閉作戰助手" @click="mobileChatOpen = false">
          ×
        </button>
        <ChatPanel ref="chatRef" :lake-id="id" @inundation="onInundation" @envelope="onEnvelope" />
      </div>
    </div>

    <button class="mobile-chat-fab" type="button" aria-label="開啟作戰助手" @click="mobileChatOpen = true">
      <img src="/logo.png" alt="" />
    </button>
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
const mobileChatOpen = ref(false);

// 左欄「推估淹水」按鈕 → 模擬使用者在右側對話送出訊息(走 function call,
// 結果同時套疊地圖 + 由 AI 回覆),左欄不展開、不跑版。
const chatRef = ref<{ ask: (p: string) => void } | null>(null);
const onInundationAsk = (prompt: string) => {
  mobileChatOpen.value = true;
  chatRef.value?.ask(prompt);
};
</script>

<style scoped>
.war { height: calc(100vh - 53px); display: flex; flex-direction: column; padding: 12px 16px; gap: 12px; }
.cols { flex: 1; display: grid; grid-template-columns: 340px 1fr 420px; gap: 12px; min-height: 0; }
.col { display: flex; flex-direction: column; gap: 12px; min-height: 0; }
.col.scroll { overflow-y: auto; padding-right: 4px; }
.mapcol { min-height: 0; }
.mapwrap { flex: 1; min-height: 0; overflow: hidden; }
.chatcol { min-height: 0; }
.mobile-chat-fab,
.mobile-chat-close { display: none; }

/* lg: 折單欄，順序：狀態(1) → 地圖(2) → 聊天(3) */
@media (max-width: 1024px) {
  .war { height: auto; padding: 10px 14px; }
  .cols { grid-template-columns: 1fr; overflow-y: visible; gap: 10px; }
  .col { order: 1; }
  .mapcol { order: 2; height: 320px; }
  .chatcol { order: 3; height: 500px; }
  .col.scroll { overflow-y: visible; max-height: none; padding-right: 0; }
  .mapwrap { height: 100%; }
}
/* md: 手機橫式 */
@media (max-width: 768px) {
  .war { padding: 8px 10px 88px; }
  .mapcol { height: 260px; }
  .chatcol {
    position: fixed; right: 14px; bottom: 14px; z-index: 1100;
    display: none; width: min(320px, calc(100vw - 28px));
    height: min(420px, calc(100dvh - 132px)); min-height: 280px;
    background: var(--panel); border: 1px solid var(--border); border-radius: 14px;
    box-shadow: 0 12px 36px rgba(80, 66, 45, .22);
  }
  .chatcol.open { display: flex; }
  .chatcol :deep(.chat) {
    border: 0; border-radius: 14px; box-shadow: none;
    min-height: 0; overflow: hidden;
  }
  .mobile-chat-close {
    position: absolute; top: 8px; right: 8px; z-index: 2;
    display: inline-flex; align-items: center; justify-content: center;
    width: 26px; height: 26px; padding: 0;
    background: transparent; color: var(--muted); border: 0;
    font-size: 20px; line-height: 1; cursor: pointer;
  }
  .mobile-chat-close:hover { color: var(--text); }
  .mobile-chat-fab {
    position: fixed; right: 18px; bottom: 18px; z-index: 1050;
    display: inline-flex; align-items: center; justify-content: center;
    width: 64px; height: 64px; padding: 0; border-radius: 50%;
    background: var(--panel); border: 1px solid var(--border);
    box-shadow: 0 8px 24px rgba(80, 66, 45, .22); cursor: pointer;
  }
  .mobile-chat-fab img {
    width: 48px; height: 48px; display: block; border-radius: 50%;
    object-fit: cover;
  }
  .mobile-chat-active .mobile-chat-fab { display: none; }
}
/* sm: 手機直式 */
@media (max-width: 480px) {
  .chatcol {
    right: 8px; bottom: 8px; width: min(320px, calc(100vw - 16px));
    height: min(400px, calc(100dvh - 108px)); min-height: 260px;
  }
  .mobile-chat-fab { right: 14px; bottom: 14px; width: 58px; height: 58px; }
  .mobile-chat-fab img { width: 44px; height: 44px; }
}
</style>
