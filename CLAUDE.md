# BarrierLakeOps — repo notes

堰湖態勢跨部會研判元件。`backend/`(FastAPI + FastMCP, Python 3.12, uv)、`frontend/`(Nuxt 3)。
完整施工藍圖見 [`docs/EXECUTION_PLAN.md`](docs/EXECUTION_PLAN.md)。

## ⚠️ 核心原則:問題定義已凍結(competition baseline)

本專案已通過「防災積木元件創新賽」初選。**競賽報名時所提交的「問題定義 / 要解決的問題敘述」是評審依據,已凍結、不得再更改。**

- **不可變(frozen)**:本專案所要解決的問題、問題範圍、問題敘述與核心價值主張。任何修改、重新詮釋或擴大/縮小問題範疇都不允許 — 即使技術上更好或更有趣,也以維持初選版本的問題定義為準。
- **可變(open to change)**:介面(UI)、操作流程(UX / 互動)、資料呈現方式、版面配置、視覺風格、文案措辭、效能與實作細節。這些可以自由迭代優化,只要不改變上述問題定義。
- **判斷準則**:收到需求時先自問「這會改到『我們要解決什麼問題』嗎?」
  - 否(只動到怎麼呈現 / 怎麼操作)→ 可直接進行。
  - 是(動到問題本身 / 解決標的)→ 停下來向使用者確認,不要逕自更動。

## 本機開發
```bash
docker compose up -d postgres          # 本機 Postgres
cd backend && uv sync && uv run uvicorn barrier_lake_ops.app:app --reload --port 8000
cd frontend && npm install && npm run dev   # http://localhost:3000
```
資料前處理(DEM/村里界,已 commit 處理後小檔):`cd backend && uv run python scripts/prep_geo.py`

## Zeabur 部署
- Project ID: `6a1beb20f9a5b4afba15d962`(BarrierLakeOps, Seoul)
- Environment ID: `6a1beb20b764eebf4f53b460`
- Services(direct deploy;**redeploy 用 `deploy --service-id`**,不能 in-place redeploy):
  - backend  `6a1d0023dde8027c6783f508` → https://barrierlakeops-api.code-world-bagel.com(自訂網域,有效 HTTPS)
  - frontend `6a1d005c2cc61de70f4db855` → https://barrierlakeops.code-world-bagel.com(自訂網域,有效 HTTPS)
  - postgresql `6a1d00e72cc61de70f4db865`(template B20CX0)
  - (備:`*.zeabur.app` 生成網域憑證簽發較慢;自訂網域立即有效)
- 環境變數關聯(改 domain 時兩者需同步更新並 redeploy,**程式碼不需改**):
  - frontend `NUXT_PUBLIC_API_BASE` = backend 公開網域
  - backend `CORS_ORIGINS` = frontend 公開網域(逗號分隔可多個)
- 重新部署:`cd backend && npx zeabur@latest deploy --project-id 6a1beb20f9a5b4afba15d962 --service-id 6a1d0023dde8027c6783f508 --json`

## 環境變數
- backend/.env 與 frontend/.env 各自獨立(變數見 README §A3)。Zeabur 上環境變數已設於各 service。
