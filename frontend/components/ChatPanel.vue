<template>
  <div class="panel chat">
    <div class="panel-pad head"><h3>Chat 作戰助手</h3></div>

    <div ref="scroller" class="scroll body">
      <div v-if="!turns.length" class="hint muted">
        用對話或下方快速鍵調度工具。試試:「光復鄉今晚要不要撤?」、「列出風險最高的堰塞湖」
      </div>
      <template v-for="(t, i) in turns" :key="i">
        <div v-if="t.role === 'user'" class="msg user">{{ t.content }}</div>
        <template v-else-if="t.role === 'assistant'">
          <!-- 每個工具步驟 = 獨立對話框,取得當下即顯示;點「查看資料」展開原始資料 -->
          <div v-for="(s, j) in t.steps" :key="i + '-s-' + j" class="msg bot stepmsg">
            <button
              type="button"
              class="step"
              :class="[s.status, { clickable: !!s.result }]"
              :disabled="!s.result"
              @click="s.open = !s.open"
            >
              <span class="ic">{{ s.status === "done" ? "✓" : "⚙" }}</span>
              <span class="tname">{{ s.status === "done" ? toolLabel(s.name) : "呼叫 " + toolLabel(s.name) + "…" }}</span>
              <span v-if="argHint(s)" class="ahint">{{ argHint(s) }}</span>
              <span v-if="s.result" class="chev">{{ s.open ? "▾ 收合資料" : "▸ 查看資料" }}</span>
            </button>
            <pre v-if="s.open && s.result" class="stepdata">{{ formatResult(s) }}</pre>
          </div>
          <!-- 結論 = 獨立對話框 -->
          <div v-if="t.content" class="msg bot">
            <div class="content md" v-html="renderMd(t.content)"></div>
          </div>
          <div v-else-if="t.busy" class="msg bot muted">研判中…</div>
        </template>
      </template>
    </div>

    <!-- 快速鍵:點擊 = 送出預寫自然語言,交由 agent 路由工具 -->
    <div class="panel-pad quickbar">
      <button class="chip" :disabled="busy" @click="ask('彙整目前狀態、上游雨量、淹水與影響人口,生成一份指揮中心態勢摘要。')">
        📋 態勢摘要
      </button>
      <button class="chip danger" :disabled="busy" @click="ask('根據目前態勢綜合研判,今晚是否需要預警性撤離?請先列關鍵數據(淹水範圍、抵達時間、影響人口)再給建議。')">
        🚨 撤離分析
      </button>
    </div>

    <div class="panel-pad composer">
      <div class="row inp">
        <input
          v-model="text"
          class="field"
          placeholder="輸入自然語言問題…"
          :disabled="busy"
          @keydown.enter="send"
        />
        <button class="btn primary" :disabled="busy || !text.trim()" @click="send">送出</button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import MarkdownIt from "markdown-it";

const props = defineProps<{ lakeId?: string }>();
const emit = defineEmits<{ inundation: [polygon: any] }>();
const { stream } = useChatStream();
const api = useApi();

// html:false → 模型輸出中的原始 HTML 會被轉義(防 XSS);表格為 markdown-it 預設啟用。
const md = new MarkdownIt({ html: false, linkify: true, breaks: true });
const renderMd = (s: string) => md.render((s || "").replace(/\n{3,}/g, "\n\n").trim());

const text = ref("");
const busy = ref(false);
const sessionId = ref<string | undefined>(undefined);
const turns = ref<any[]>([]);
const scroller = ref<HTMLElement | null>(null);

const TOOL_LABELS: Record<string, string> = {
  list_lakes: "列出堰塞湖",
  get_lake_status: "查詢狀態",
  get_upstream_weather: "上游雨量",
  estimate_inundation: "淹水推估",
  get_affected_population: "影響人口",
  compose_briefing: "態勢摘要",
};
const toolLabel = (n: string) => TOOL_LABELS[n] || n;

// 軌跡上顯示的關鍵參數提示(只挑有助理解的)
function argHint(s: any): string {
  if (!s?.args) return "";
  if (s.name === "estimate_inundation") {
    const sc = s.args.breach_scenario;
    return sc === "partial" ? "部分潰壩" : sc === "full" ? "全潰壩" : "";
  }
  return "";
}

// 點開步驟時呈現的「原始取得資料」:剝除大型 GeoJSON,以可讀 JSON 顯示
const STRIP = new Set(["inundation_polygon", "geometry", "polygon", "coordinates"]);
function formatResult(s: any): string {
  const r = s?.result;
  if (r == null) return "";
  if (typeof r !== "object") return String(r);
  const clean = (o: any): any => {
    if (Array.isArray(o)) return o.map(clean);
    if (o && typeof o === "object") {
      const out: Record<string, any> = {};
      for (const k of Object.keys(o)) out[k] = STRIP.has(k) ? "<geojson 已省略>" : clean(o[k]);
      return out;
    }
    return o;
  };
  try {
    return JSON.stringify(clean(r), null, 2);
  } catch {
    return String(r);
  }
}

async function scrollDown() {
  await nextTick();
  if (scroller.value) scroller.value.scrollTop = scroller.value.scrollHeight;
}

function ask(prompt: string) {
  if (busy.value) return;
  text.value = prompt;
  send();
}

// 供左欄 InundationPanel 等同層元件呼叫(模擬使用者送出訊息)
defineExpose({ ask });

async function send() {
  const msg = text.value.trim();
  if (!msg || busy.value) return;
  text.value = "";
  busy.value = true;
  turns.value.push({ role: "user", content: msg });
  const bot = reactive({ role: "assistant", steps: [] as any[], content: "", busy: true });
  turns.value.push(bot);
  await scrollDown();
  try {
    await stream({ message: msg, lake_id: props.lakeId, session_id: sessionId.value }, (ev) => {
      if (ev.type === "session") sessionId.value = ev.session_id || sessionId.value;
      else if (ev.type === "tool_call") bot.steps.push({ name: ev.name, args: ev.args, status: "calling", open: false });
      else if (ev.type === "tool_result") {
        const s = [...bot.steps].reverse().find((x) => x.name === ev.name && x.status === "calling");
        if (s) { s.status = "done"; s.result = ev.result; }
        // 淹水結果套疊到中欄地圖
        if (ev.name === "estimate_inundation" && ev.result?.inundation_polygon)
          emit("inundation", ev.result.inundation_polygon);
      } else if (ev.type === "final") bot.content = ev.content;
      else if (ev.type === "error") bot.content = "⚠ " + ev.message;
      scrollDown();
    });
  } catch (e: any) {
    bot.content = "⚠ 連線錯誤:" + (e?.message || e);
  } finally {
    bot.busy = false;
    busy.value = false;
    scrollDown();
  }
}
</script>

<style scoped>
.chat { display: flex; flex-direction: column; height: 100%; }
.head { border-bottom: 1px solid var(--border); }
.body { flex: 1; padding: 12px 14px; display: flex; flex-direction: column; gap: 10px; }
.hint { font-size: 12px; }
.msg { max-width: 96%; padding: 8px 11px; border-radius: 10px; font-size: 13px; white-space: pre-wrap; }
.msg.user { align-self: flex-end; background: var(--accent); color: #fffdf8; }
.msg.bot { align-self: flex-start; background: var(--panel-2); border: 1px solid var(--border); width: 96%; }
/* 工具調用軌跡:每個步驟為獨立小對話框,可收合查看原始資料 */
.stepmsg { padding: 6px 11px; }
.step {
  font-size: 11.5px; display: flex; gap: 6px; align-items: baseline; width: 100%;
  background: none; border: none; padding: 1px 0; color: inherit; text-align: left; font-family: inherit;
}
.step.clickable { cursor: pointer; }
.step:disabled { cursor: default; }
.step .ic { color: var(--accent); }
.step.calling .ic { opacity: .7; }
.step.calling .tname { color: var(--muted); font-weight: 500; }
.step .tname { color: var(--text); font-weight: 600; }
.step .ahint { color: var(--muted); font-size: 11px; }
.step .chev { margin-left: auto; color: var(--muted); font-size: 11px; white-space: nowrap; }
.step.clickable:hover .chev { color: var(--accent); }
.stepdata {
  margin: 3px 0 4px; background: var(--bg-2); border: 1px solid var(--border);
  border-radius: 7px; padding: 8px 10px; font-size: 11px; line-height: 1.5;
  max-height: 220px; overflow: auto; white-space: pre-wrap; word-break: break-word;
}
.content { margin-top: 2px; }
/* AI 回覆的 Markdown 呈現(v-html 內容需用 :deep) */
/* 關鍵:覆蓋 .msg 的 white-space: pre-wrap,否則 markdown-it 產生的標籤間換行會變成可見空行 */
.md { white-space: normal; }
.md :deep(li > p) { margin: 0; }
.md :deep(p) { margin: 4px 0; }
.md :deep(p:first-child) { margin-top: 0; }
.md :deep(p:last-child) { margin-bottom: 0; }
.md :deep(ul), .md :deep(ol) { margin: 4px 0; padding-left: 18px; }
.md :deep(li) { margin: 2px 0; }
.md :deep(strong) { font-weight: 700; }
.md :deep(h1), .md :deep(h2), .md :deep(h3), .md :deep(h4) { font-size: 13px; margin: 7px 0 3px; }
.md :deep(code) {
  background: var(--bg-2); border: 1px solid var(--border);
  border-radius: 4px; padding: 0 4px; font-size: 11.5px;
}
.md :deep(table) {
  border-collapse: collapse; width: 100%; margin: 6px 0; font-size: 12px;
  display: block; overflow-x: auto;
}
.md :deep(th), .md :deep(td) { border: 1px solid var(--border); padding: 3px 7px; text-align: left; }
.md :deep(th) { background: var(--bg-2); font-weight: 600; }

.quickbar { display: flex; gap: 8px; align-items: stretch; border-top: 1px solid var(--border); }
.chip {
  flex: 1; text-align: center;
  background: var(--bg-2); color: var(--text); border: 1px solid var(--border);
  border-radius: 999px; padding: 7px 11px; font-size: 12.5px; cursor: pointer; white-space: nowrap;
}
.chip:hover:not(:disabled) { border-color: var(--accent); }
.chip:disabled { opacity: .5; cursor: default; }
.chip.danger { border-color: #c0563b; color: #e08a6f; }
.composer { border-top: 1px solid var(--border); }
.inp { display: flex; gap: 8px; }
.field { flex: 1; background: var(--bg-2); border: 1px solid var(--border); border-radius: 8px; color: var(--text); padding: 8px 11px; font-size: 13px; }
.field:focus { outline: none; border-color: var(--accent); }
</style>
