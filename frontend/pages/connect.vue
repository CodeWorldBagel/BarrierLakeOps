<template>
  <div class="container connect">
    <h1>接上 MCP — 讓你的 AI 直接調度本元件</h1>
    <p class="lead muted">
      BarrierLakeOps 以 <b>MCP(Model Context Protocol)</b> 暴露 6 個堰塞湖工具。任何支援 MCP 的 AI
      ——Claude Desktop、Cursor、Claude Code——貼上下方設定即可直接調度跨部會資料,<b>免 clone、免裝 Python</b>。
    </p>

    <!-- 遠端端點 -->
    <section class="panel panel-pad">
      <h3>① 遠端 MCP 端點</h3>
      <div class="urlbox">
        <code>{{ mcpUrl }}</code>
        <button class="btn sm" @click="copy(mcpUrl, 'url')">{{ copied === 'url' ? '已複製 ✓' : '複製' }}</button>
      </div>
      <p class="muted small">傳輸方式:streamable-HTTP。</p>
    </section>

    <!-- 設定 JSON -->
    <section class="panel panel-pad">
      <h3>② 設定 JSON</h3>

      <p class="muted small"><b>mcp-remote 橋接版</b> — Claude Desktop(含免費方案)等需 stdio 橋接的 client,寫入 <code>claude_desktop_config.json</code>:</p>
      <div class="codeblock">
        <button class="btn sm copy" @click="copy(claudeCfg, 'bridge')">{{ copied === 'bridge' ? '已複製 ✓' : '複製' }}</button>
        <pre>{{ claudeCfg }}</pre>
      </div>

      <p class="muted small mt"><b>直連 URL 版</b> — Cursor(<code>~/.cursor/mcp.json</code>)等支援遠端 URL 的 client,streamable-HTTP 直連:</p>
      <div class="codeblock">
        <button class="btn sm copy" @click="copy(cursorCfg, 'url2')">{{ copied === 'url2' ? '已複製 ✓' : '複製' }}</button>
        <pre>{{ cursorCfg }}</pre>
      </div>
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
.small { font-size: 12.5px; }
.mt { margin-top: 16px; }
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
code { background: var(--bg-2); border: 1px solid var(--border); border-radius: 5px; padding: 1px 5px; }
.codeblock pre code, .urlbox code { background: none; border: none; padding: 0; }
</style>
