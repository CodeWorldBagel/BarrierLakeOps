<template>
  <div class="container about">
    <h1>關於 BarrierLakeOps</h1>
    <p class="lead muted">
      堰湖態勢跨部會研判元件 — 把分散在各部會的堰塞湖資料,封裝為 AI Agent 可多步調用的標準工具集
      (MCP + REST 雙介面)。2026 數位發展部「防災積木元件創新賽」參賽作品 · 隊伍 CodeWorldBagel。
    </p>

    <section class="panel panel-pad">
      <h3>問題 → 解法</h3>
      <p>
        2025/9/23 花蓮馬太鞍溪堰塞湖溢流潰壩,關鍵失靈點之一是「跨部會資料無法即時匯流」:
        蓄水位、上游雨量、下游淹水、撤離名冊分散在不同系統,沒有一處能一次看完全貌。
        本元件以 Lake Catalog 設定檔驅動,新增堰塞湖只需加一筆設定,不需改程式碼;
        並以 6 個可拼接 Tool 讓 AI Agent 自主完成跨部會盤點。
      </p>
    </section>

    <section>
      <h3 class="sec">6 個 Tool</h3>
      <div class="tools">
        <div v-for="t in tools" :key="t.name" class="panel panel-pad tool">
          <code>{{ t.name }}</code>
          <div class="muted">{{ t.desc }}</div>
        </div>
      </div>
    </section>

    <section class="panel panel-pad">
      <h3>資料來源與授權</h3>
      <table>
        <thead><tr><th>來源</th><th>用途</th><th>授權</th></tr></thead>
        <tbody>
          <tr v-for="s in sources" :key="s.name">
            <td>{{ s.name }}</td><td>{{ s.use }}</td><td>{{ s.lic }}</td>
          </tr>
        </tbody>
      </table>
    </section>

    <section class="panel panel-pad">
      <h3>AI 應用界線</h3>
      <ul>
        <li>不自動下達撤離指令、不直接觸發警報、不串接 PWS/LINE/Email 發送通道。</li>
        <li>淹水為 MVP 簡化模型(SRTM DEM 容量守恆推估),明確標註 disclaimer。</li>
        <li>水位若為情境基準快照,明確標示非即時(freshness: stale)。</li>
        <li>外部 API 不可用時回傳明確錯誤狀態,不捏造資料。</li>
        <li>人口資料以村里為最小粒度,不揭露個人資訊。</li>
        <li>Chat Agent 僅調用本元件 6 個 Tool,不開啟通用網路搜尋。</li>
      </ul>
    </section>

    <section class="panel panel-pad">
      <h3>掛載 MCP(Claude Desktop)</h3>
      <pre class="code">{{ mcpSnippet }}</pre>
      <div class="row">
        <a class="btn sm" :href="docs" target="_blank">REST API 文件 ↗</a>
        <a class="btn sm" href="https://github.com/CodeWorldBagel/BarrierLakeOps" target="_blank">GitHub ↗</a>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
const docs = (useRuntimeConfig().public.apiBase as string) + "/docs";
const tools = [
  { name: "list_lakes", desc: "列出可查詢堰塞湖(catalog + data.moa,依風險排序)" },
  { name: "get_lake_status", desc: "水位、蓄水量、距溢流 headroom、警戒等級" },
  { name: "get_upstream_weather", desc: "上游集水區鄰近雨量站觀測與警戒(CWA)" },
  { name: "estimate_inundation", desc: "潰壩淹水範圍推估(真實 DEM + MVP 模型)" },
  { name: "get_affected_population", desc: "淹水範圍內村里、戶數、人口與弱勢" },
  { name: "compose_briefing", desc: "LLM 態勢摘要生成(可追溯資料來源)" },
];
const sources = [
  { name: "data.moa 國有林堰塞湖", use: "Tool 0/1", lic: "政府資料開放授權條款 1.0" },
  { name: "中央氣象署 O-A0002 / F-D0047", use: "Tool 2", lic: "政府資料開放授權條款 1.0" },
  { name: "SRTM 30m DEM(NASA)", use: "Tool 3", lic: "Public Domain" },
  { name: "內政部 村里界 / 人口", use: "Tool 4", lic: "政府資料開放授權條款 1.0" },
  { name: "OpenStreetMap", use: "底圖", lic: "ODbL © OpenStreetMap contributors" },
];
const mcpSnippet = `{
  "mcpServers": {
    "barrier-lake-ops": {
      "command": "uv",
      "args": ["run", "barrier-lake-ops"],
      "env": { "CWA_API_KEY": "...", "OPENAI_API_KEY": "..." }
    }
  }
}`;
</script>

<style scoped>
.about { padding-bottom: 40px; }
.lead { max-width: 760px; margin-bottom: 18px; }
section { margin-bottom: 16px; }
.sec { margin: 18px 0 10px; }
.tools { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; }
.tool code { color: var(--accent); font-size: 13px; }
.tool .muted { font-size: 12px; margin-top: 4px; }
ul { margin: 0; padding-left: 18px; }
ul li { margin: 4px 0; }
.code { background: var(--bg-2); border: 1px solid var(--border); border-radius: 8px; padding: 12px; font-size: 12px; overflow-x: auto; }
@media (max-width: 800px) { .tools { grid-template-columns: 1fr; } }
</style>
