<template>
  <div class="panel panel-pad">
    <div class="head">
      <h3>上游集水區雨量(CWA)</h3>
      <AlertBadge v-if="weather" :level="weather.alert_level" />
    </div>
    <div v-if="weather">
      <table v-if="weather.stations?.length">
        <thead>
          <tr><th>雨量站</th><th>1h</th><th>3h</th><th>24h</th></tr>
        </thead>
        <tbody>
          <tr v-for="s in weather.stations" :key="s.station_id">
            <td>{{ s.name }}<span class="muted"> ({{ s.station_id }})</span></td>
            <td>{{ mm(s.rainfall_1h_mm) }}</td>
            <td>{{ mm(s.rainfall_3h_mm) }}</td>
            <td>{{ mm(s.rainfall_24h_mm) }}</td>
          </tr>
        </tbody>
      </table>
      <div v-else class="muted">無鄰近雨量站資料。</div>
      <div class="rationale muted">{{ weather.rationale }}</div>
    </div>
    <div v-else class="muted">載入中…</div>
  </div>
</template>

<script setup lang="ts">
defineProps<{ weather: any }>();
const mm = (v: any) => (v == null ? "—" : v + "mm");
</script>

<style scoped>
.head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 10px; }
.rationale { font-size: 11.5px; margin-top: 8px; }
</style>
