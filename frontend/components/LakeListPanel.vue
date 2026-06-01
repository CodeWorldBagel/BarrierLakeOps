<template>
  <div class="panel lakelist">
    <div class="panel-pad head">
      <h3>監測中堰塞湖 · 依風險排序</h3>
      <div class="row filters">
        <button
          v-for="f in filters"
          :key="f.v"
          class="btn sm"
          :class="{ primary: modelFilter === f.v }"
          @click="$emit('filter', f.v)"
        >
          {{ f.t }}
        </button>
      </div>
    </div>
    <div class="scroll list">
      <NuxtLink
        v-for="lk in lakes"
        :key="lk.id"
        :to="`/lakes/${lk.id}`"
        class="item"
        :class="{ active: lk.id === selected }"
      >
        <div class="item-top">
          <AlertBadge :level="lk.alert_level" />
          <span class="name">{{ lk.name }}</span>
        </div>
        <div class="item-sub muted">
          <span v-if="lk.headroom_m != null">headroom {{ lk.headroom_m }} m ·</span>
          <span>{{ statusText(lk.status) }}</span>
        </div>
      </NuxtLink>
      <div v-if="!lakes.length" class="panel-pad muted">載入中…</div>
    </div>
    <div class="panel-pad foot muted">資料來源:data.moa 國有林堰塞湖 + Lake Catalog</div>
  </div>
</template>

<script setup lang="ts">
defineProps<{ lakes: any[]; selected?: string; modelFilter: string }>();
defineEmits<{ filter: [v: string] }>();
const filters = [
  { v: "all", t: "全部" },
  { v: "active", t: "監測中" },
  { v: "monitoring", t: "觀察" },
];
const statusText = (s: string) =>
  ({ active: "監測中", monitoring: "觀察中", archived: "已解除" })[s] || s;
</script>

<style scoped>
.lakelist { display: flex; flex-direction: column; height: 100%; }
.head { border-bottom: 1px solid var(--border); }
.filters { margin-top: 8px; }
.list { flex: 1; }
.item { display: block; padding: 11px 16px; border-bottom: 1px solid var(--border); color: var(--text); }
.item:hover { background: var(--panel-2); text-decoration: none; }
.item.active { background: var(--panel-2); box-shadow: inset 3px 0 0 var(--accent); }
.item-top { display: flex; align-items: center; gap: 8px; }
.item-top .name { font-weight: 600; }
.item-sub { font-size: 12px; margin-top: 3px; }
.foot { border-top: 1px solid var(--border); font-size: 11px; }
</style>
