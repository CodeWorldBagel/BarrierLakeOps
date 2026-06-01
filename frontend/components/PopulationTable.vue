<template>
  <div class="panel panel-pad">
    <h3>潰壩影響人口</h3>
    <div v-if="pop">
      <div class="cards">
        <div class="card">
          <div class="muted">受影響村里</div>
          <div class="kpi">{{ pop.affected_villages?.length ?? 0 }}</div>
        </div>
        <div class="card">
          <div class="muted">戶數</div>
          <div class="kpi">{{ num(pop.total_households) }}</div>
        </div>
        <div class="card">
          <div class="muted">人口</div>
          <div class="kpi">{{ num(pop.total_population) }}</div>
        </div>
      </div>
      <div class="row vuln">
        <span class="tag">65 歲以上 {{ num(pop.vulnerable_estimate?.elderly_65plus) }}</span>
        <span class="tag">6 歲以下 {{ num(pop.vulnerable_estimate?.children_under6) }}</span>
      </div>
      <table v-if="pop.affected_villages?.length">
        <thead><tr><th>鄉鎮</th><th>村里</th><th>戶</th><th>人口</th></tr></thead>
        <tbody>
          <tr v-for="v in pop.affected_villages.slice(0, 8)" :key="v.village_code">
            <td>{{ v.town }}</td><td>{{ v.village }}</td>
            <td>{{ num(v.households) }}</td><td>{{ num(v.population) }}</td>
          </tr>
        </tbody>
      </table>
    </div>
    <div v-else class="muted">尚未推估(請於地圖選擇潰壩情境)。</div>
  </div>
</template>

<script setup lang="ts">
defineProps<{ pop: any }>();
const num = (v: any) => (v == null ? "—" : Number(v).toLocaleString());
</script>

<style scoped>
.cards { display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; margin: 8px 0; }
.card { background: var(--panel-2); border: 1px solid var(--border); border-radius: 10px; padding: 8px 10px; }
.vuln { margin-bottom: 8px; }
</style>
