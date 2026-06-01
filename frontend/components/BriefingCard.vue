<template>
  <div class="panel panel-pad">
    <div class="head">
      <h3>態勢摘要(AI 生成)</h3>
      <AlertBadge v-if="b" :level="b.status_color" />
    </div>
    <div v-if="loading" class="muted">生成中…</div>
    <div v-else-if="b">
      <div class="headline">{{ b.headline }}</div>
      <ul class="facts">
        <li v-for="(f, i) in b.key_facts" :key="i">{{ f }}</li>
      </ul>
      <div v-if="b.recommended_actions?.length" class="actions">
        <div class="muted label">建議行動</div>
        <ol>
          <li v-for="(a, i) in b.recommended_actions" :key="i">{{ a }}</li>
        </ol>
      </div>
      <div class="row foot">
        <span class="tag">AI 信心 {{ Math.round((b.ai_confidence || 0) * 100) }}%</span>
        <span class="tag">{{ (b.data_sources_used || []).length }} 個資料來源</span>
      </div>
    </div>
    <div v-else class="muted">尚未生成摘要。</div>
  </div>
</template>

<script setup lang="ts">
defineProps<{ b: any; loading?: boolean }>();
</script>

<style scoped>
.head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px; }
.headline { font-weight: 700; font-size: 15px; margin-bottom: 8px; }
.facts { margin: 0 0 8px; padding-left: 18px; }
.facts li { margin: 3px 0; font-size: 13px; }
.actions .label { font-size: 11px; text-transform: uppercase; letter-spacing: .6px; }
.actions ol { margin: 4px 0 8px; padding-left: 18px; }
.actions li { margin: 3px 0; font-size: 13px; }
.foot { margin-top: 6px; }
</style>
