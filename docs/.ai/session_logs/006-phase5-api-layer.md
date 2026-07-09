# Session Log 006 — Phase 5 Application Service & API Layer

## Agent 身份
Cline（後端開發代理）

## 驗收條件逐項核對
- [x] 在 `src/backend/api/` 底下建立 FastAPI 的專案結構（`__init__.py`、`main.py`、`routes.py`、`dashboard_service.py`）。
- [x] 實作整合型 `DashboardService`：負責載入 CSV 檔案、初始化 Ledger、驅動 PortfolioEngine、結合 MarketData，並調用 Metrics 算子，將整個管線串聯起來。
- [x] 建立 FastAPI 路由（Endpoints）：
  - `GET /api/v1/dashboard/summary`：回傳總資產市值、現金、未實現總損益、已實現總損益、最新資產配置比例。
  - `GET /api/v1/dashboard/allocation`：回傳詳細的資產配置權重清單。
  - `GET /api/v1/dashboard/nav-history`：回傳歷史淨值與報酬率時間序列（用於前端畫 K 線/折線圖）。
- [x] 在 `tests/` 底下建立 `test_api.py`，使用 FastAPI 的 `TestClient` 撰寫集成測試，驗證 API 接口的回傳狀態碼（200 OK）與 JSON 結構正確性。
- [x] 執行 `pytest` 驗證，全部 106 項測試皆為綠燈（106 passed in 1.13s，含 Phase 1~4 無回歸）。

## 完成事項
- 建立 `src/backend/api/__init__.py`：匯出 `DashboardService`、`router`。
- 建立 `src/backend/api/dashboard_service.py`：`DashboardService`
  - `load_from_csv()`：從 CSV 檔案載入資料，透過 CsvToEventConverter 轉換事件、排序、驅動 PortfolioEngine。
  - `load_from_data()`：直接從記憶體中的事件與市場資料初始化（用於測試）。
  - `get_summary()`：整合 UnrealizedPnlCalculator、AssetAllocationCalculator、已實現損益、現金餘額，回傳完整摘要。
  - `get_allocation()`：委託 AssetAllocationCalculator 計算資產配置權重。
  - `get_nav_history()`：委託 NavHistoryGenerator 生成歷史淨值序列，並轉換為 JSON 可序列化格式（含 NaN/Inf 防護）。
  - `_safe_float()`：模組級輔助函數，安全轉換 float 並處理 NaN/Inf。
- 建立 `src/backend/api/routes.py`：FastAPI 路由
  - `GET /api/v1/dashboard/summary`：支援選擇性 `target_date` 查詢參數。
  - `GET /api/v1/dashboard/allocation`：支援選擇性 `target_date` 查詢參數。
  - `GET /api/v1/dashboard/nav-history`：必填 `start_date` 與 `end_date` 參數，含日期範圍驗證。
  - 異常處理：`HTTPException` 直接穿透、`RuntimeError` → 503、其他 → 500。
  - 支援 `set_service()` 測試注入，方便 TestClient 測試。
- 建立 `src/backend/api/main.py`：FastAPI 應用程式入口，含 `/health` 健康檢查端點。
- 建立 `tests/test_api.py`：24 項集成測試，涵蓋：
  - DashboardService（10 項）：初始化、摘要結構、目標日期、已實現損益、資產配置、歷史淨值、總報酬率、未初始化錯誤、空投資組合、單一股票。
  - API 路由（14 項）：健康檢查、summary/allocation/nav-history 200 OK、target_date 參數、無效日期 400、缺少參數 422、日期範圍驗證 400、未初始化 503、JSON 結構完整性驗證。

## 目前阻塞（Blockers）
無

## 給下一個 Agent 的上下文
- Phase 5 (Application Service & API Layer) 已完整實作。
- 所有 106 項測試已通過（pytest 1.13s），Phase 1~4 無回歸。
- `DashboardService` 同時支援 `load_from_csv()`（從檔案載入）與 `load_from_data()`（從記憶體載入，用於測試）。
- API 路由使用全域 `_service` 變數管理 DashboardService 實例，可透過 `set_service()` 注入測試用實例。
- 可透過 `uvicorn src.backend.api.main:app` 啟動 API 伺服器。
- 接著可進入 Phase 6：前端開發（React/Vue 儀表板 UI）或 Dilution Operator 實作。

## 待辦事項（Pending Tasks for Next Agent）
1. 實作 Dilution Operator（處理 StockDividendEvent 與 CorporateActionEvent）。
2. 實作具體的 PriceProvider（如 YahooFinanceProvider）。
3. 實作前端 API 層（React/Vue 儀表板 UI）。

## 本次變更檔案
- src/backend/api/__init__.py（新增）
- src/backend/api/dashboard_service.py（新增）
- src/backend/api/routes.py（新增）
- src/backend/api/main.py（新增）
- tests/test_api.py（新增）

## Commit
feat(api): implement DashboardService and FastAPI endpoints for Phase 5
