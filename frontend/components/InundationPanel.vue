<template>
  <div class="panel panel-pad">
    <div class="head">
      <h3>潰壩淹水推估</h3>
      <span v-if="result?.model_used" class="modeltag">{{ result.model_used }}</span>
    </div>

    <div class="ctrl">
      <select v-model="scenario" class="sel" :disabled="busy" aria-label="潰壩情境">
        <option value="full">全潰壩</option>
        <option value="partial">部分潰壩</option>
      </select>
      <button class="btn primary" :disabled="busy || !lakeId" @click="run">
        {{ busy ? "推估中…" : result ? "重新推估" : "🌊 推估淹水" }}
      </button>
    </div>

    <div v-if="result" class="out">
      <div class="metrics">
        <div class="metric">
          <span class="lbl">最大深度</span>
          <span class="val">{{ fmt(result.max_depth_m_estimate) }}<small> m</small></span>
        </div>
        <div class="metric">
          <span class="lbl">前緣抵達</span>
          <span class="val">{{ fmt(result.leading_edge_arrival_minutes) }}<small> 分</small></span>
        </div>
      </div>
      <div class="overlaid">✓ 已套疊至中欄地圖</div>
      <div v-if="result.disclaimer" class="disclaimer">⚠ {{ result.disclaimer }}</div>
    </div>
    <div v-else-if="error" class="muted note">⚠ {{ error }}</div>
    <div v-else class="muted note">選擇潰壩情境後推估;淹水為 MVP 簡化模型,僅供研判參考。</div>
  </div>
</template>

<script setup lang="ts">
const props = defineProps<{ lakeId?: string }>();
const emit = defineEmits<{ inundation: [polygon: any] }>();
const api = useApi();

const scenario = ref<"full" | "partial">("full");
const busy = ref(false);
const result = ref<any>(null);
const error = ref("");
const fmt = (v: any) => (v == null ? "—" : Number(v).toLocaleString());

async function run() {
  if (!props.lakeId || busy.value) return;
  busy.value = true;
  error.value = "";
  try {
    const r: any = await api.inundation(props.lakeId, scenario.value);
    result.value = r;
    if (r?.inundation_polygon) emit("inundation", r.inundation_polygon);
  } catch (e: any) {
    error.value = e?.message || "推估失敗";
  } finally {
    busy.value = false;
  }
}
</script>

<style scoped>
.head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 10px; }
.modeltag {
  font-size: 11px; color: var(--muted); background: var(--bg-2);
  border: 1px solid var(--border); border-radius: 6px; padding: 1px 7px;
}
.ctrl { display: flex; gap: 8px; align-items: center; }
.ctrl .sel {
  background: var(--bg-2); color: var(--text); border: 1px solid var(--border);
  border-radius: 8px; padding: 6px 8px; font-size: 12.5px;
}
.ctrl .btn { flex: 1; }
.out { margin-top: 12px; }
.metrics { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
.metric {
  background: var(--bg-2); border: 1px solid var(--border); border-radius: 8px;
  padding: 8px 10px; display: flex; flex-direction: column; gap: 3px;
}
.metric .lbl { font-size: 11.5px; color: var(--muted); }
.metric .val { font-size: 18px; font-weight: 700; }
.metric .val small { font-size: 11.5px; font-weight: 400; color: var(--muted); }
.overlaid { margin-top: 8px; font-size: 11.5px; color: var(--accent); }
.disclaimer { margin-top: 6px; font-size: 11px; color: var(--muted); line-height: 1.5; }
.note { font-size: 11.5px; margin-top: 10px; line-height: 1.5; }
</style>
