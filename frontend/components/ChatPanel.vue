<template>
  <div class="panel chat">
    <div class="panel-pad head"><h3>Chat 作戰助手</h3></div>
    <div ref="scroller" class="scroll body">
      <div v-if="!turns.length" class="hint muted">
        試試:「光復鄉今晚要不要撤?」、「列出風險最高的堰塞湖」
      </div>
      <template v-for="(t, i) in turns" :key="i">
        <div v-if="t.role === 'user'" class="msg user">{{ t.content }}</div>
        <div v-else-if="t.role === 'assistant'" class="msg bot">
          <div v-if="t.steps?.length" class="steps">
            <div v-for="(s, j) in t.steps" :key="j" class="step">
              <span class="ic">{{ s.status === "done" ? "✓" : "⚙" }}</span>
              <code>{{ s.name }}</code>
              <span v-if="s.result" class="muted res">{{ brief(s.result) }}</span>
            </div>
          </div>
          <div v-if="t.content" class="content">{{ t.content }}</div>
          <div v-else-if="t.busy" class="muted">研判中…</div>
        </div>
      </template>
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
      <div class="disclaimer">
        ⚠ 本助手僅產生研判建議,<b>不自動發送撤離通知</b>;撤離決策由人類指揮官執行。
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
const props = defineProps<{ lakeId?: string }>();
const { stream } = useChatStream();

const text = ref("");
const busy = ref(false);
const sessionId = ref<string | undefined>(undefined);
const turns = ref<any[]>([]);
const scroller = ref<HTMLElement | null>(null);

async function scrollDown() {
  await nextTick();
  if (scroller.value) scroller.value.scrollTop = scroller.value.scrollHeight;
}

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
      else if (ev.type === "tool_call") bot.steps.push({ name: ev.name, args: ev.args, status: "calling" });
      else if (ev.type === "tool_result") {
        const s = [...bot.steps].reverse().find((x) => x.name === ev.name && x.status === "calling");
        if (s) { s.status = "done"; s.result = ev.result; }
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

const brief = (r: any) =>
  Object.entries(r || {})
    .map(([k, v]) => `${k}=${v}`)
    .join(" ");
</script>

<style scoped>
.chat { display: flex; flex-direction: column; height: 100%; }
.head { border-bottom: 1px solid var(--border); }
.body { flex: 1; padding: 12px 14px; display: flex; flex-direction: column; gap: 10px; }
.hint { font-size: 12px; }
.msg { max-width: 92%; padding: 8px 11px; border-radius: 10px; font-size: 13px; white-space: pre-wrap; }
.msg.user { align-self: flex-end; background: var(--accent); color: #fffdf8; }
.msg.bot { align-self: flex-start; background: var(--panel-2); border: 1px solid var(--border); }
.steps { display: flex; flex-direction: column; gap: 3px; margin-bottom: 6px; }
.step { font-size: 11.5px; display: flex; gap: 6px; align-items: baseline; }
.step .ic { color: var(--accent); }
.step code { color: var(--text); }
.step .res { font-size: 11px; }
.composer { border-top: 1px solid var(--border); }
.inp { margin-bottom: 8px; }
.field { flex: 1; background: var(--bg-2); border: 1px solid var(--border); border-radius: 8px; color: var(--text); padding: 8px 11px; font-size: 13px; }
.field:focus { outline: none; border-color: var(--accent); }
</style>
