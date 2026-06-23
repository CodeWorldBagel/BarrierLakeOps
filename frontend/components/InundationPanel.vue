<template>
  <div class="panel panel-pad">
    <div class="head"><h3>潰壩淹水推估</h3></div>
    <div class="ctrl">
      <select v-model="scenario" class="sel" aria-label="潰壩情境">
        <option value="full">全潰壩</option>
        <option value="partial">部分潰壩</option>
      </select>
      <button class="btn primary" @click="run">🌊 推估淹水</button>
    </div>
    <p class="note muted">推估範圍將繪製於中欄地圖,詳細研判由右側對話回覆。</p>
  </div>
</template>

<script setup lang="ts">
// 不直接打 API:按下後交由右側 ChatPanel 以對話(function call)推估,
// 結果同時套疊中欄地圖 + 由 AI 回覆,左欄不展開、不跑版。
const emit = defineEmits<{ ask: [prompt: string] }>();
const scenario = ref<"full" | "partial">("full");
const label = computed(() => (scenario.value === "full" ? "全潰壩" : "部分潰壩"));

function run() {
  emit(
    "ask",
    `請依「${label.value}」情境推估本堰塞湖的潰壩淹水範圍,並將範圍套疊到地圖;同時說明最大深度、前緣抵達時間與注意事項。`,
  );
}
</script>

<style scoped>
.head { margin-bottom: 10px; }
.ctrl { display: flex; gap: 8px; align-items: center; }
.ctrl .sel {
  background: var(--bg-2); color: var(--text); border: 1px solid var(--border);
  border-radius: 8px; padding: 6px 8px; font-size: 12.5px;
}
.ctrl .btn { flex: 1; }
.note { font-size: 11.5px; margin-top: 10px; line-height: 1.5; }
</style>
