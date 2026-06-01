<template>
  <div class="panel panel-pad">
    <div class="head" @click="open = !open">
      <h3>歷史簡報 · 稽核軌跡 ({{ items.length }})</h3>
      <span class="muted">{{ open ? "▾" : "▸" }}</span>
    </div>
    <div v-if="open" class="list">
      <div v-if="!items.length" class="muted">尚無歷史簡報。</div>
      <button
        v-for="it in items"
        :key="it.id"
        class="hist"
        @click="$emit('replay', it.id)"
      >
        <AlertBadge :level="it.status_color || 'unknown'" />
        <span class="hl">{{ it.headline }}</span>
        <span class="muted ts">{{ fmtTime(it.created_at) }}</span>
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
defineProps<{ items: any[] }>();
defineEmits<{ replay: [id: string] }>();
const open = ref(true);
const fmtTime = (s: string) => (s ? new Date(s).toLocaleString("zh-TW") : "");
</script>

<style scoped>
.head { display: flex; align-items: center; justify-content: space-between; cursor: pointer; }
.list { margin-top: 8px; display: flex; flex-direction: column; gap: 6px; }
.hist {
  display: flex; align-items: center; gap: 8px; text-align: left;
  background: var(--panel-2); border: 1px solid var(--border); border-radius: 8px;
  padding: 6px 9px; cursor: pointer; color: var(--text);
}
.hist:hover { border-color: var(--accent); }
.hist .hl { flex: 1; font-size: 12px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.hist .ts { font-size: 11px; }
</style>
