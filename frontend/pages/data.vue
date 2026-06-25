<template>
  <div class="container data">
    <div class="head">
      <div>
        <h1>資料同步狀況</h1>
        <p class="muted small">各資料來源的更新狀態。即時資料查詢時抓取;排程資料每日更新;人工維護可即時編輯。</p>
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
            <button class="btn sm primary" :disabled="!picked || uploading" @click="doUpload">
              {{ uploading ? "上傳中…" : "上傳並解析" }}
            </button>
          </div>
          <input ref="fileInput" type="file" accept=".yaml,.yml" hidden @change="onPick" />
        </div>
        <div v-if="uploadMsg" class="upmsg muted small">ℹ {{ uploadMsg }}</div>
        <div v-for="d in byKind.upload" :key="d.key" class="muted small mt">
          後端解析入庫由組員實作。目前狀態:{{ statusZh(d.status) }}{{ d.message ? "(" + d.message + ")" : "" }}
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

      <!-- 人工維護 -->
      <section class="panel panel-pad sec">
        <h3>✋ 人工維護 <span class="shint">應變中心可即時編輯,寫 DB + 記錄時間</span></h3>
        <div v-for="s in status.lake_states" :key="'st-' + s.lake_id" class="row">
          <span class="nm">堰塞湖水位 · {{ s.lake_id }}</span>
          <span class="muted">水位 {{ s.water_level_m ?? "—" }} m</span>
          <span class="muted">{{ s.updated_by }} · {{ s.updated_at ? fmt(s.updated_at) : "—" }}</span>
          <button class="btn sm" @click="editState(s)">編輯</button>
        </div>
        <p class="muted small mt">堰塞湖即時水位未開放於 open data,由應變中心依現地回報手動更新。</p>
      </section>
    </template>

    <!-- 編輯彈窗 -->
    <div v-if="editing" class="modal-bg" @click.self="editing = null">
      <div class="modal panel panel-pad">
        <h3>編輯水位 · {{ editing.lake_id }}</h3>
        <label>水位(m)<input v-model.number="form.water_level_m" type="number" step="0.1" /></label>
        <label>蓄水量(百萬 m³)<input v-model.number="form.storage_million_m3" type="number" step="0.1" /></label>
        <label>觀測時間<input v-model="form.observed_at" type="text" placeholder="2026-06-23T18:00:00+08:00" /></label>
        <label>備註<textarea v-model="form.note" rows="2" /></label>
        <div class="modal-actions">
          <button class="btn" @click="editing = null">取消</button>
          <button class="btn primary" :disabled="saving" @click="save">{{ saving ? "儲存中…" : "儲存" }}</button>
        </div>
      </div>
    </div>
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
async function doUpload() {
  if (!picked.value) return;
  uploading.value = true;
  try {
    const r: any = await api.uploadLakes(picked.value);
    uploadMsg.value = r?.message || "已上傳。";
    picked.value = null;
    await load();
  } catch (e: any) {
    uploadMsg.value = "上傳失敗:" + (e?.message || e);
  } finally {
    uploading.value = false;
  }
}

// 編輯彈窗
const editing = ref<{ lake_id: string } | null>(null);
const form = reactive<any>({});
const saving = ref(false);

function editState(s: any) {
  editing.value = { lake_id: s.lake_id };
  Object.assign(form, {
    water_level_m: s.water_level_m, storage_million_m3: s.storage_million_m3,
    observed_at: s.observed_at, note: s.note,
  });
}
async function save() {
  if (!editing.value) return;
  saving.value = true;
  try {
    await api.patchLakeState(editing.value.lake_id, { ...form });
    editing.value = null;
    await load();
  } catch (e: any) {
    error.value = e?.message || String(e);
  } finally {
    saving.value = false;
  }
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
.modal-bg { position: fixed; inset: 0; background: rgba(0,0,0,.45); display: flex; align-items: center; justify-content: center; z-index: 50; padding: 16px; }
.modal { width: 100%; max-width: 420px; }
.modal h3 { margin: 0 0 12px; }
.modal label { display: flex; flex-direction: column; gap: 4px; font-size: 12.5px; color: var(--muted); margin-bottom: 10px; }
.modal input, .modal textarea { background: var(--bg-2); border: 1px solid var(--border); border-radius: 8px; color: var(--text); padding: 7px 10px; font-size: 13px; }
.modal input:focus, .modal textarea:focus { outline: none; border-color: var(--accent); }
.modal-actions { display: flex; justify-content: flex-end; gap: 8px; margin-top: 6px; }
@media (max-width: 640px) { .metrics { grid-template-columns: 1fr 1fr; } }
</style>
