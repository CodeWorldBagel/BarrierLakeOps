<template>
  <div class="container connect">
    <h1>接上 MCP — 讓你的 AI 直接調度本元件</h1>
    <p class="lead muted">
      BarrierLakeOps 以 <b>MCP(Model Context Protocol)</b> 暴露 6 個堰塞湖工具。任何支援 MCP 的 AI
      ——Claude Desktop、Cursor、Claude Code——只要貼上一個網址,就能直接調度跨部會資料,
      <b>免 clone、免裝 Python</b>。本頁所有設定皆指向同一個遠端端點。
    </p>

    <!-- 遠端端點 -->
    <section class="panel panel-pad">
      <h3>① 遠端 MCP 端點</h3>
      <div class="urlbox">
        <code>{{ mcpUrl }}</code>
        <button class="btn sm" @click="copy(mcpUrl, 'url')">{{ copied === 'url' ? '已複製 ✓' : '複製' }}</button>
      </div>
      <p class="muted small">傳輸方式:streamable-HTTP。下面各家設定都用這個網址。</p>
    </section>

    <!-- Claude Desktop -->
    <section class="panel panel-pad">
      <h3>② Claude Desktop</h3>
      <p><b>方法 A · 自訂連接器(推薦)</b></p>
      <p class="muted small">設定 → Connectors → Add custom connector → 名稱填 <code>BarrierLakeOps</code>、網址貼上上方端點即可。</p>
      <p class="mt"><b>方法 B · 設定檔(mcp-remote 橋接)</b></p>
      <p class="muted small">編輯 <code>claude_desktop_config.json</code>:</p>
      <div class="codeblock">
        <button class="btn sm copy" @click="copy(claudeCfg, 'claude')">{{ copied === 'claude' ? '已複製 ✓' : '複製' }}</button>
        <pre>{{ claudeCfg }}</pre>
      </div>
    </section>

    <!-- Cursor / Claude Code -->
    <section class="panel panel-pad">
      <h3>③ Cursor / Claude Code</h3>
      <p class="muted small">Cursor:編輯 <code>~/.cursor/mcp.json</code>(streamable-HTTP 直連):</p>
      <div class="codeblock">
        <button class="btn sm copy" @click="copy(cursorCfg, 'cursor')">{{ copied === 'cursor' ? '已複製 ✓' : '複製' }}</button>
        <pre>{{ cursorCfg }}</pre>
      </div>
      <p class="muted small mt">Claude Code CLI:一行指令掛載:</p>
      <div class="codeblock">
        <button class="btn sm copy" @click="copy(ccCmd, 'cc')">{{ copied === 'cc' ? '已複製 ✓' : '複製' }}</button>
        <pre>{{ ccCmd }}</pre>
      </div>
    </section>

    <!-- 工具 -->
    <section>
      <h3 class="sec">掛上後你的 AI 會得到 6 個工具</h3>
      <div class="tools">
        <div v-for="t in tools" :key="t.name" class="panel panel-pad tool">
          <code>{{ t.name }}</code>
          <div class="muted">{{ t.desc }}</div>
        </div>
      </div>
    </section>

    <!-- 安全界線 -->
    <section class="panel panel-pad guard">
      <h3>④ 安全界線(人在迴路)</h3>
      <p class="muted small">
        這些護欄寫進 MCP server 的 <code>instructions</code> 與各工具描述,因此會隨工具一起傳遞給你的 AI:
      </p>
      <ul>
        <li>只依工具回傳的真實政府開放資料研判,<b>不編造數字、不通用網路搜尋</b>。</li>
        <li>淹水為 <b>MVP 簡化模型</b>,需註明;水位若為情境快照需說明非即時。</li>
        <li>AI <b>只提供研判與建議</b>:不發送撤離簡訊、不觸發警報,<b>撤離決策保留給人類指揮官</b>。</li>
      </ul>
      <p class="muted small">完整守則見 repo 的 <code>AGENT.md</code>。</p>
    </section>
  </div>
</template>

<script setup lang="ts">
const base = (useRuntimeConfig().public.apiBase as string).replace(/\/$/, "");
const mcpUrl = `${base}/mcp/`;

const claudeCfg = `{
  "mcpServers": {
    "barrierlakeops": {
      "command": "npx",
      "args": ["-y", "mcp-remote", "${mcpUrl}"]
    }
  }
}`;

const cursorCfg = `{
  "mcpServers": {
    "barrierlakeops": {
      "url": "${mcpUrl}"
    }
  }
}`;

const ccCmd = `claude mcp add --transport http barrierlakeops ${mcpUrl}`;

const tools = [
  { name: "list_lakes", desc: "列出可查詢堰塞湖,依風險排序" },
  { name: "get_lake_status", desc: "水位、蓄水量、距溢流 headroom、警戒等級" },
  { name: "get_upstream_weather", desc: "上游集水區鄰近雨量站觀測與警戒(CWA)" },
  { name: "estimate_inundation", desc: "潰壩淹水推估(DEM + MVP 模型),輸出 GeoJSON" },
  { name: "get_affected_population", desc: "淹水範圍內村里、戶數、人口、老幼弱勢" },
  { name: "compose_briefing", desc: "彙整以上資料生成態勢摘要(寫入稽核軌跡)" },
];

const copied = ref("");
async function copy(text: string, key: string) {
  try {
    await navigator.clipboard.writeText(text);
    copied.value = key;
    setTimeout(() => (copied.value = ""), 1500);
  } catch {
    /* clipboard 不可用時忽略 */
  }
}
</script>

<style scoped>
.container { max-width: 860px; margin: 0 auto; padding: 28px 20px 60px; }
h1 { margin: 0 0 10px; }
.lead { font-size: 15px; line-height: 1.7; margin-bottom: 22px; }
section { margin-bottom: 18px; }
h3 { margin: 0 0 10px; }
.sec { margin: 8px 0 12px; }
.small { font-size: 12.5px; }
.mt { margin-top: 12px; }
.urlbox {
  display: flex; align-items: center; gap: 10px; flex-wrap: wrap;
  background: var(--bg-2); border: 1px solid var(--border); border-radius: 10px; padding: 10px 12px;
}
.urlbox code { font-size: 14px; word-break: break-all; flex: 1; }
.codeblock { position: relative; }
.codeblock pre {
  background: var(--bg-2); border: 1px solid var(--border); border-radius: 10px;
  padding: 12px 14px; overflow-x: auto; font-size: 12.5px; line-height: 1.55; margin: 6px 0 0;
}
.codeblock .copy { position: absolute; top: 12px; right: 10px; }
.guard ul { margin: 8px 0 6px; padding-left: 18px; }
.guard li { margin: 5px 0; font-size: 13px; line-height: 1.6; }
.tools { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
.tool code { font-size: 13px; color: var(--accent); }
.tool .muted { font-size: 12.5px; margin-top: 4px; }
code { background: var(--bg-2); border: 1px solid var(--border); border-radius: 5px; padding: 1px 5px; }
.codeblock pre code, .urlbox code { background: none; border: none; padding: 0; }
@media (max-width: 640px) { .tools { grid-template-columns: 1fr; } }
</style>
