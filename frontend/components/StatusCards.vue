<template>
  <div class="panel panel-pad">
    <div class="lakehead">
      <NuxtLink to="/" class="back" aria-label="返回列表">←</NuxtLink>
      <b class="title">{{ status?.name || "—" }}</b>
      <AlertBadge v-if="status" :level="status.alert_level" />
    </div>
    <div class="head">
      <h3>堰塞湖狀態</h3>
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
.lakehead { display: flex; align-items: center; gap: 10px; min-width: 0; margin-bottom: 12px; }
.lakehead .back {
  display: inline-flex; align-items: center; justify-content: center;
  width: 30px; height: 30px; flex: 0 0 auto;
  border: 1px solid var(--border); border-radius: 8px;
  color: var(--text); font-size: 16px; line-height: 1; text-decoration: none;
}
.lakehead .back:hover { background: var(--panel-2); }
.lakehead .title { flex: 1; min-width: 0; font-size: 17px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
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
