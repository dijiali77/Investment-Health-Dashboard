# 開發路線圖：Cline 分階段實作指南（v3.0）

> **依賴章節**：本檔總覽全部 01～15 章節對應的 Phase 順序，為 Cline 任務指派的主索引

---

## 第十九章　開發路線圖：Cline 分階段實作指南（v3.0）

| Phase | 對應目錄 | 本版核心實作重點 | 驗收標準（Zero-Bias）|
|---|---|---|---|
| **Phase 1** | `src/ledger/`、`src/errors/` | FinancialEvent 繼承體系 + Error Domain | 1) 所有子類別 `frozen=True` 且通過 Pydantic 驗證 2) ERR003/ERR005/ERR007 正確觸發 3) 排序鍵 `(event_date, sequence_in_day, event_id)` 100% 確定性 |
| **Phase 2** | `src/market_data/`（含 locf_operator.py）| PriceProvider 介面 + **LOCF 補值算子** | 1) `get_aligned_daily_prices` 回傳完全對齊、無週末休市中斷的股價向量 2) MockProvider 可離線執行所有測試 3) ERR008 觸發時自動切換 Provider 4) `test_locf_operator.py` 通過 |
| **Phase 3** | `src/portfolio/`（含 dilution_operator）| FIFO 撮合 + **Lots 稀釋算子** | 1) 遭遇 `STOCK_DIVIDEND`/`CORPORATE_ACTION` 時，未平倉 Lots 原位更新，佇列尾端無新 Lot 追加 2) 總成本守恆誤差 ≤ 0.01 3) `test_dilution_operator.py` 通過 |
| **Phase 4** | `src/accounting/`（含應收股利）| 複式記帳分錄 + **權責發生制應收股利雙階段** | 1) 除權息日自動建立 `Dividend Receivable` 借貸分錄 2) `DIVIDEND_RECEIVE` 事件完成沖銷 3) `BalanceSheetSnapshot.net_worth` 在除息日保持平穩（NAV 不跳空）4) `test_dividend_receivable.py` 通過 |
| **Phase 5** | `src/projections/`（重構）| **Timeline Projector 單次線性掃描** | 1) 實現單次線性掃描（$O(N+D)$），嚴禁任何雙重迴圈重放 2) 輸出包含每日 `BalanceSheetSnapshot[]`、`IncomeStatementSnapshot[]`、`CashFlowSnapshot[]` 的完整時序矩陣 3) `test_timeline_engine.py` 通過（含效能測試：10年×100支股票 ≤ 300ms）|
| **Phase 6** | `src/analytics/`（矩陣輸入）| Metric DAG 全面對接時序矩陣輸入 | 1) `compute_nav_series()` 直接消費 `list[BalanceSheetSnapshot]` 2) DAG 拓樸排序執行，Analytics 層無任何重放邏輯 3) XIRR/MDD 執行耗時 ≤ 150ms 4) `test_metric_dag.py` 通過（含 cycle 偵測）|
| **Phase 7** | `src/evidence/`（邊界壓縮）| RuleSchema + Versioning + **邊界血緣壓縮** | 1) YAML 載入時通過 Pydantic 驗證，格式錯誤 → ERR009 2) 版本選擇邏輯正確 3) 全域時序型指標自動啟用 `source_event_range` 4) Evidence JSON 體積 ≤ 50KB 5) `test_lineage_compression.py` 通過 |
| **Phase 8** | `src/repository/`、`src/telemetry/` | Repository Layer + Telemetry | 1) 切換 `REPOSITORY_BACKEND = "sqlite"` 不影響上層 2) OutputPayload 含 telemetry_summary 且各層耗時符合目標值 |
| **Phase 9** | `src/exporter/`、`main.py`、`prompts/` | 整合所有層 + LLM 端 | 1) 輸出符合 `95-output-schema.md` 的 Schema 2) Pipeline 端對端一次執行完成 3) `test_pipeline_e2e.py` 通過 4) LLM 輸出引用 `rule_version`/`formula_version`，時序型指標標示 `source_event_range`，未自行計算任何數字 |
| **Phase 10** | `src/api/`（FastAPI）| **【v3.0 新增】API Gateway 全端點實作** | 1) 全部 7 個端點（`/snapshot`、`/timeline`、`/evidence`、`/positions`、`/events/drilldown`、`/lineage/metric`、`/health`）符合 `14-api-gateway.md` 規格 2) API 層完全不含業務計算，僅做序列化與路由 3) `test_api_endpoints.py` 通過 4) CORS 設定正確，僅允許 GET 方法 |
| **Phase 11** | `frontend/`（React + TypeScript）| **【v3.0 新增】互動式報表前端全頁面實作** | 1) 五大頁面（Overview / NAVChart / EvidenceMatrix / PositionDrilldown / LineageExplorer）符合 `15-frontend.md` 規格 2) 前端零計算驗證：所有數值均來自 API 回應，無客戶端財務公式 3) TypeScript 型別與後端 Pydantic Schema 完全對應，無 `any` 濫用 4) `test_api_drilldown_e2e.py` 通過（驗證點擊鑽取至原始 CSV 行號）|

---
