<template>
  <div class="panel panel-pad">
    <div class="head"><h3>潰壩淹水推估</h3></div>

    <div class="opts">
      <button
        v-for="o in SCENARIOS"
        :key="o.value"
        type="button"
        class="opt"
        :class="{ on: scenario === o.value }"
        :aria-pressed="scenario === o.value"
        @click="scenario = o.value"
      >
        <span class="ol">{{ o.label }}</span>
        <span class="od">{{ o.desc }}</span>
      </button>
    </div>

    <button class="btn primary run" @click="run">🌊 推估淹水（{{ label }}）</button>

    <p class="note muted">推估範圍將繪製於中欄地圖,詳細研判由右側對話回覆。</p>
  </div>
</template>

<script setup lang="ts">
// 不直接打 API:按下後交由右側 ChatPanel 以對話(function call)推估,
// 結果同時套疊中欄地圖 + 由 AI 回覆,左欄不展開、不跑版。
const emit = defineEmits<{ ask: [prompt: string] }>();

const SCENARIOS = [
  { value: "full", label: "全潰壩", desc: "壩體完全潰決" },
  { value: "partial", label: "部分潰壩", desc: "壩體局部潰決" },
] as const;

const scenario = ref<"full" | "partial">("full");
const label = computed(() => (scenario.value === "full" ? "全潰壩" : "部分潰壩"));

function run() {
  emit(
    "ask",
    `請依「${label.value}」情境完整研判本堰塞湖的潰壩淹水,依序逐步進行:` +
      `(1)查詢目前堰塞湖狀態、(2)查上游集水區雨量、(3)推估潰壩淹水範圍並套疊到地圖、` +
      `(4)估算影響人口(村里、戶數、老幼弱勢),最後彙整成淹水研判摘要。`,
  );
}
</script>

<style scoped>
.head { margin-bottom: 12px; }
.opts { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
.opt {
  display: flex; flex-direction: column; gap: 3px; align-items: flex-start;
  padding: 10px 12px; background: var(--bg-2); border: 1px solid var(--border);
  border-radius: 10px; cursor: pointer; text-align: left; font-family: inherit;
  transition: border-color .12s, background .12s;
}
.opt:hover { border-color: var(--accent); }
.opt.on { border-color: var(--accent); box-shadow: inset 0 0 0 1px var(--accent); }
.opt .ol { font-size: 13.5px; font-weight: 700; color: var(--text); }
.opt.on .ol { color: var(--accent); }
.opt .od { font-size: 11px; color: var(--muted); }
.run { width: 100%; margin-top: 10px; }
.note { font-size: 11.5px; margin-top: 12px; line-height: 1.5; }
</style>
