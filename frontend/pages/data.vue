<template>
  <div class="container data">
    <div class="head">
      <div>
        <h1>資料同步狀況</h1>
        <p class="muted small">各資料來源的更新狀態。即時資料查詢時抓取;排程資料每日自動更新。</p>
      </div>
      <button class="btn primary" :disabled="syncing || loading" @click="runSync">
        {{ syncing ? "更新中…" : "立即更新全部" }}
      </button>
    </div>

    <div v-if="loading" class="muted pad">載入中…</div>
    <div v-else-if="error" class="muted pad">⚠ 無法載入資料同步狀態:{{ error }}</div>

    <template v-else-if="status">
      <div class="metrics">
        <div class="metric"><span class="lbl">資料集</span><span class="val">{{ status.datasets.length }}</span></div>
        <div class="metric"><span class="lbl">正常</span><span class="val">{{ countOk }}</span></div>
        <div class="metric"><span class="lbl">待處理</span><span class="val">{{ countPending }}</span></div>
        <div class="metric"><span class="lbl">異常</span><span class="val" :class="{ bad: countErr }">{{ countErr }}</span></div>
      </div>

      <!-- 即時 -->
      <section v-if="byKind.live.length" class="panel panel-pad sec">
        <h3>⚡ 即時資料 <span class="shint">查詢時即時抓取,不進排程</span></h3>
        <div v-for="d in byKind.live" :key="d.key" class="row">
          <span class="nm">{{ d.label }}</span>
          <span class="muted">{{ d.source }}</span>
          <span class="chip live">即時</span>
        </div>
      </section>

      <!-- 堰塞湖清單:上傳模組 -->
      <section v-if="byKind.upload.length" class="panel panel-pad sec">
        <h3>📋 堰塞湖清單 <span class="chip">手動上傳 YAML</span></h3>
        <div v-for="d in byKind.upload" :key="d.key" class="row">
          <span class="nm">{{ d.label }}</span>
          <span class="muted">{{ d.message || d.source }}</span>
          <span class="muted">{{ d.last_success_at ? fmt(d.last_success_at) : "尚未上傳" }}</span>
          <span class="muted">{{ d.row_count != null ? d.row_count + " 筆" : "" }}</span>
          <span class="sdot" :class="d.status">{{ statusZh(d.status) }}</span>
        </div>
        <div
          class="drop"
          :class="{ over: dragOver }"
          @dragover.prevent="dragOver = true"
          @dragleave.prevent="dragOver = false"
          @drop.prevent="onDrop"
        >
          <div class="muted">{{ pickedName || "將 lakes.yaml 拖曳至此,或" }}</div>
          <div class="drop-actions">
            <button class="btn sm" @click="fileInput?.click()">選擇檔案</button>
            <button class="btn sm primary" :disabled="!picked || uploading" @click="doUpload()">
              {{ uploading ? "上傳中…" : "上傳並解析" }}
            </button>
          </div>
          <input ref="fileInput" type="file" accept=".yaml,.yml" hidden @change="onPick" />
        </div>
        <div v-if="uploadMsg" class="upmsg muted small">ℹ {{ uploadMsg }}</div>
        <!-- 重複警告 dialog -->
        <div v-if="dupWarnings.length" class="modal-bg" @click.self="dupWarnings = []">
          <div class="panel panel-pad modal">
            <h3>⚠ 偵測到潛在重複堰塞湖</h3>
            <p class="muted small">以下項目 formed_at 相同且距離小於 500m，可能為同一座湖。</p>
            <div v-for="w in dupWarnings" :key="w.lake_id_a + w.lake_id_b" class="dup-row">
              <span class="nm">{{ w.name_a }} <span class="muted">({{ w.lake_id_a }})</span></span>
              <span class="muted">↔</span>
              <span class="nm">{{ w.name_b }} <span class="muted">({{ w.lake_id_b }})</span></span>
              <span class="muted small">{{ w.reason }}</span>
            </div>
            <div class="tip-box">略過：跳過上列項目，其餘照常匯入。</div>
            <div class="modal-actions">
              <button class="btn" @click="dupWarnings = []">取消</button>
              <button class="btn" :disabled="uploading" @click="doUploadSkip">略過</button>
              <button class="btn primary" :disabled="uploading" @click="doUpload(true)">全部匯入</button>
            </div>
          </div>
        </div>
      </section>

      <!-- 每日排程 -->
      <section v-if="byKind.scheduled.length" class="panel panel-pad sec">
        <h3>🗓 每日排程資料 <span class="shint">每日自動拉取 → 寫入 DB</span></h3>
        <div v-for="d in byKind.scheduled" :key="d.key" class="row">
          <span class="nm">{{ d.label }}</span>
          <span class="muted">{{ d.source }}</span>
          <span class="muted">{{ d.last_success_at ? fmt(d.last_success_at) : "—" }}</span>
          <span class="muted">{{ d.row_count != null ? d.row_count + " 筆" : "" }}</span>
          <span class="sdot" :class="d.status">{{ statusZh(d.status) }}</span>
        </div>
      </section>

      <!-- 靜態 -->
      <section v-if="byKind.static.length" class="panel panel-pad sec">
        <h3>🗿 靜態資料 <span class="shint">地形不變,一次處理</span></h3>
        <div v-for="d in byKind.static" :key="d.key" class="row">
          <span class="nm">{{ d.label }}</span>
          <span class="muted">{{ d.source }}</span>
          <span class="chip">靜態</span>
        </div>
      </section>

    </template>
  </div>
</template>

<script setup lang="ts">
const api = useApi();

const status = ref<any>(null);
const loading = ref(true);
const error = ref("");
const syncing = ref(false);

async function load() {
  try {
    status.value = await api.dataStatus();
    error.value = "";
  } catch (e: any) {
    error.value = e?.message || String(e);
  } finally {
    loading.value = false;
  }
}
onMounted(load);

const byKind = computed(() => {
  const g: Record<string, any[]> = { live: [], upload: [], scheduled: [], static: [], manual: [] };
  for (const d of status.value?.datasets || []) (g[d.kind] ||= []).push(d);
  return g;
});
const countOk = computed(() => (status.value?.datasets || []).filter((d: any) => d.status === "ok").length);
const countPending = computed(() => (status.value?.datasets || []).filter((d: any) => d.status === "pending").length);
const countErr = computed(() => (status.value?.datasets || []).filter((d: any) => d.status === "error").length);

const fmt = (s: string) => (s ? new Date(s).toLocaleString("zh-TW") : "—");
const statusZh = (s: string) => ({ ok: "正常", pending: "待處理", running: "更新中", error: "異常" }[s] || s);

async function runSync() {
  syncing.value = true;
  try {
    await api.triggerSync();
    await load();
  } catch (e: any) {
    error.value = e?.message || String(e);
  } finally {
    syncing.value = false;
  }
}

// 上傳模組
const fileInput = ref<HTMLInputElement | null>(null);
const picked = ref<File | null>(null);
const pickedName = computed(() => picked.value?.name || "");
const uploading = ref(false);
const uploadMsg = ref("");
const dragOver = ref(false);
const dupWarnings = ref<any[]>([]);

function setFile(f: File | null | undefined) {
  if (!f) return;
  if (!/\.(ya?ml)$/i.test(f.name)) {
    uploadMsg.value = "請選擇 .yaml / .yml 檔案。";
    return;
  }
  picked.value = f;
  uploadMsg.value = "";
}
const onPick = (e: Event) => setFile((e.target as HTMLInputElement).files?.[0]);
function onDrop(e: DragEvent) {
  dragOver.value = false;
  setFile(e.dataTransfer?.files?.[0]);
}
async function doUpload(force = false, skipIds?: string[]) {
  if (!picked.value) return;
  uploading.value = true;
  try {
    const r: any = await api.uploadLakes(picked.value, force, skipIds);
    if (!r?.imported && r?.warnings?.length) {
      dupWarnings.value = r.warnings;
      uploadMsg.value = "";
      return;
    }
    dupWarnings.value = [];
    uploadMsg.value = r?.message || "已上傳。";
    picked.value = null;
    if (fileInput.value) fileInput.value.value = "";
    await load();
  } catch (e: any) {
    uploadMsg.value = "上傳失敗:" + (e?.message || e);
  } finally {
    uploading.value = false;
  }
}

function doUploadSkip() {
  const ids = dupWarnings.value.flatMap((w: any) => [w.lake_id_a, w.lake_id_b]);
  doUpload(false, ids);
}

</script>

<style scoped>
.container { max-width: 920px; margin: 0 auto; padding: 24px 20px 60px; }
.head { display: flex; justify-content: space-between; align-items: flex-start; gap: 16px; flex-wrap: wrap; margin-bottom: 18px; }
h1 { margin: 0 0 4px; }
.small { font-size: 12.5px; }
.pad { padding: 20px 0; }
.metrics { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin-bottom: 18px; }
.metric { background: var(--bg-2); border: 1px solid var(--border); border-radius: 10px; padding: 12px 14px; }
.metric .lbl { display: block; font-size: 12px; color: var(--muted); }
.metric .val { font-size: 24px; font-weight: 700; }
.metric .val.bad { color: #c0563b; }
.sec { margin-bottom: 14px; }
.sec h3 { margin: 0 0 8px; }
.shint { font-size: 12px; color: var(--muted); font-weight: 400; margin-left: 8px; }
.row { display: flex; align-items: center; gap: 12px; padding: 9px 0; border-top: 1px solid var(--border); font-size: 13px; }
.row .nm { flex: 1; min-width: 0; }
.chip { font-size: 12px; padding: 2px 9px; border-radius: 6px; background: var(--bg-2); border: 1px solid var(--border); color: var(--muted); }
.chip.live { color: var(--accent); border-color: var(--accent); }
.sdot { font-size: 12px; padding: 2px 9px; border-radius: 6px; }
.sdot.ok { color: #2f7d4f; }
.sdot.error { color: #c0563b; }
.sdot.pending, .sdot.running { color: var(--muted); }
.drop { border: 1.5px dashed var(--border); border-radius: 10px; padding: 18px; text-align: center; }
.drop.over { border-color: var(--accent); background: var(--bg-2); }
.drop-actions { display: flex; gap: 8px; justify-content: center; margin-top: 10px; }
.upmsg, .mt { margin-top: 8px; }
.dup-row { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; padding: 8px 0; border-top: 1px solid var(--border); font-size: 13px; }
.tip-box { font-size: 11px; color: var(--muted); border-left: 2px solid var(--border); padding: 2px 8px; margin-top: 10px; }
.modal-bg { position: fixed; inset: 0; background: rgba(0,0,0,.45); display: flex; align-items: center; justify-content: center; z-index: 50; padding: 16px; }
.modal { width: 100%; max-width: 420px; }
.modal h3 { margin: 0 0 12px; }
.modal label { display: flex; flex-direction: column; gap: 4px; font-size: 12.5px; color: var(--muted); margin-bottom: 10px; }
.modal input, .modal textarea { background: var(--bg-2); border: 1px solid var(--border); border-radius: 8px; color: var(--text); padding: 7px 10px; font-size: 13px; }
.modal input:focus, .modal textarea:focus { outline: none; border-color: var(--accent); }
.modal-actions { display: flex; justify-content: flex-end; gap: 8px; margin-top: 6px; }
@media (max-width: 640px) { .metrics { grid-template-columns: 1fr 1fr; } }
</style>
