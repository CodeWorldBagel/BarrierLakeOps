<template>
  <div class="panel panel-pad">
    <div class="head">
      <h3>堰塞湖狀態</h3>
      <AlertBadge v-if="status" :level="status.alert_level" />
    </div>
    <div v-if="status" class="cards">
      <div class="card">
        <div class="muted">水位</div>
        <div class="kpi">{{ fmt(status.water_level_m) }}<small> m</small></div>
      </div>
      <div class="card">
        <div class="muted">溢流門檻</div>
        <div class="kpi">{{ fmt(status.overflow_threshold_m) }}<small> m</small></div>
      </div>
      <div class="card" :class="hrClass">
        <div class="muted">headroom 距溢流</div>
        <div class="kpi">{{ fmt(status.headroom_m) }}<small> m</small></div>
      </div>
      <div class="card">
        <div class="muted">蓄水量</div>
        <div class="kpi">{{ fmt(status.storage_million_m3) }}<small> 百萬m³</small></div>
      </div>
    </div>
    <div v-if="status?.note" class="note muted">⚠ {{ status.note }}</div>
    <div v-if="status" class="row meta">
      <span class="tag">freshness: {{ status.freshness }}</span>
      <span v-if="status.last_updated" class="tag">更新 {{ status.last_updated }}</span>
    </div>
  </div>
</template>

<script setup lang="ts">
const props = defineProps<{ status: any }>();
const fmt = (v: any) => (v == null ? "—" : v);
const hrClass = computed(() => {
  const a = props.status?.alert_level;
  return a && a !== "unknown" ? a : "";
});
</script>

<style scoped>
.head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 10px; }
.cards { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
.card { background: var(--panel-2); border: 1px solid var(--border); border-radius: 10px; padding: 9px 11px; }
.card .kpi small { font-size: 12px; color: var(--muted); font-weight: 500; }
.card.red { border-color: rgba(239,68,68,.5); }
.card.orange { border-color: rgba(249,115,22,.5); }
.card.yellow { border-color: rgba(234,179,8,.5); }
.note { font-size: 11.5px; margin-top: 10px; }
.meta { margin-top: 8px; }
</style>
