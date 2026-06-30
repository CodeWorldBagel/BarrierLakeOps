<template>
  <div class="panel lakelist">
    <div class="panel-pad head">
      <h3>監測中堰塞湖 · 依風險排序</h3>
      <div class="row filters">
        <button
          v-for="f in filters"
          :key="f.v"
          class="btn sm"
          :class="{ primary: activeFilters.includes(f.v) }"
          @click="$emit('toggle', f.v)"
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
          <AlertBadge v-if="lk.alert_level !== 'unknown'" :level="lk.alert_level" />
          <span v-else class="badge st" :class="'st-' + lk.status">
            <span class="dot" />{{ statusText(lk.status) }}
          </span>
          <span class="name">{{ lk.name }}</span>
        </div>
        <div class="item-sub muted">
          <span v-if="lk.headroom_m != null">headroom {{ lk.headroom_m }} m · {{ statusText(lk.status) }}</span>
          <span v-else-if="lk.formed_at">形成於 {{ lk.formed_at }}</span>
        </div>
      </NuxtLink>
      <div v-if="!lakes.length" class="panel-pad muted">請選擇標籤</div>
    </div>
    <div class="panel-pad foot muted">資料來源:data.moa 國有林堰塞湖 + Lake Catalog</div>
  </div>
</template>

<script setup lang="ts">
defineProps<{ lakes: any[]; selected?: string; activeFilters: string[] }>();
defineEmits<{ toggle: [v: string] }>();
const filters = [
  { v: "alert", t: "警戒中" },
  { v: "monitoring", t: "監測中" },
  { v: "archived", t: "已解除" },
];
const statusText = (s: string) =>
  ({ monitoring: "監測中", archived: "已解除" })[s] || s;
</script>

<style scoped>
.lakelist { display: flex; flex-direction: column; height: 100%; min-height: 0; overflow: hidden; }
.head { border-bottom: 1px solid var(--border); }
.filters { margin-top: 8px; }
.list { flex: 1; min-height: 0; }
.item { display: block; padding: 11px 16px; border-bottom: 1px solid var(--border); color: var(--text); }
.item:hover { background: var(--panel-2); text-decoration: none; }
.item.active { background: var(--panel-2); box-shadow: inset 3px 0 0 var(--accent); }
.item-top { display: flex; align-items: center; gap: 8px; }
.item-top .name { font-weight: 600; }
.item-sub { font-size: 12px; margin-top: 3px; }
.foot { border-top: 1px solid var(--border); font-size: 11px; }

/* 湖況狀態徽章(無警戒資料時):監測中 / 已解除 以色彩區分 */
.badge.st-monitoring { color: #4f6f97; background: rgba(79,111,151,.14); border-color: rgba(79,111,151,.4); }
.badge.st-monitoring .dot { background: #5878a0; }
.badge.st-archived { color: #9a8f79; background: rgba(154,143,121,.12); border-color: rgba(154,143,121,.32); }
.badge.st-archived .dot { background: #b6ab93; }

@media (max-width: 768px) {
  .lakelist { height: auto; max-height: 280px; }
  .item-top .name {
    overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
    max-width: 200px;
  }
  .filters { flex-wrap: wrap; gap: 6px; }
}
</style>
