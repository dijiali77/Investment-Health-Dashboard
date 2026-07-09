# 專案架構總覽

## 專案目標
建立一個投資組合健康儀表板（Investment Health Dashboard），能夠：
1. 從 CSV 檔案載入交易紀錄與銀行帳務資料
2. 以 FIFO 會計方式管理庫存與已實現損益
3. 結合市場行情資料（含 LOCF 補值演算法）
4. 計算未實現損益、資產配置權重、歷史淨值與報酬率
5. 透過 FastAPI 提供 RESTful API 供前端儀表板使用

## 技術棧
- **語言**: Python 3.13+
- **網頁框架**: FastAPI (Starlette)
- **資料處理**: pandas, numpy
- **測試**: pytest, FastAPI TestClient
- **型別檢查**: Python typing (Pydantic 相容)

## 核心業務邏輯

### Phase 1 — Ledger & Domain Models（帳務領域模型）
- `FinancialEvent` 與其子類別（`SecurityTradeEvent`、`CashEvent`、`OpeningBalanceEvent` 等）
- `CsvToEventConverter`：將 CSV 行轉換為領域事件
- `sort_events()`：依日期與序號排序事件

### Phase 2 — Market Data（市場資料）
- `PriceProviderInterface`：抽象價格提供者介面
- `apply_locf()`：Last Observation Carried Forward 補值演算法，將離散交易日資料填補為連續日曆日序列

### Phase 3 — Portfolio Engine（投資組合引擎）
- `Lot`：庫存批次（含成本基礎、數量、稀釋操作）
- `RealizedPnL`：已實現損益記錄（凍結不可變）
- `FifoAccountant`：FIFO 會計帳務員（管理 Lots、計算已實現損益）
- `PortfolioEngine`：高層引擎，接收 FinancialEvent 串流驅動會計處理

### Phase 4 — Metrics Engine（指標引擎）
- `UnrealizedPnlCalculator`：計算未實現損益（支援指定日期與 LOCF 補值）
- `AssetAllocationCalculator`：計算資產配置權重（依市值排序）
- `NavHistoryGenerator`：生成歷史淨值時間序列（含每日報酬率與累積報酬率）

### Phase 5 — Application Service & API Layer（應用服務與 API 層）
- `DashboardService`：整合型 Service，串聯 CSV 載入 → Ledger → PortfolioEngine → MarketData → Metrics 完整管線
- FastAPI 路由：
  - `GET /api/v1/dashboard/summary` — 總資產市值、現金、未實現/已實現損益、資產配置
  - `GET /api/v1/dashboard/allocation` — 詳細資產配置權重清單
  - `GET /api/v1/dashboard/nav-history` — 歷史淨值與報酬率時間序列
  - `GET /health` — 健康檢查

## 模組地圖

```
src/backend/
├── __init__.py
├── ledger/                  # Phase 1
│   ├── __init__.py
│   ├── domain_models.py     # FinancialEvent 家族
│   ├── csv_converter.py     # CsvToEventConverter
│   └── event_sorting.py     # sort_events()
├── market_data/             # Phase 2
│   ├── __init__.py
│   ├── provider_interface.py # PriceProviderInterface
│   └── locf_operator.py     # apply_locf()
├── portfolio_engine/        # Phase 3
│   ├── __init__.py
│   ├── lot.py               # Lot, RealizedPnL
│   ├── fifo_accountant.py   # FifoAccountant
│   └── engine.py            # PortfolioEngine
├── metrics/                 # Phase 4
│   ├── __init__.py
│   ├── unrealized_pnl.py    # UnrealizedPnlCalculator
│   ├── asset_allocation.py  # AssetAllocationCalculator
│   └── nav_history.py       # NavHistoryGenerator
└── api/                     # Phase 5
    ├── __init__.py
    ├── dashboard_service.py # DashboardService
    ├── routes.py            # FastAPI 路由
    └── main.py              # FastAPI 應用程式入口

tests/
├── test_market_data.py      # Phase 2 (20 tests)
├── test_portfolio_engine.py # Phase 3 (39 tests)
├── test_metrics.py          # Phase 4 (23 tests)
└── test_api.py              # Phase 5 (24 tests)
```

## 測試狀態
**106 tests passed in 1.13s** — 後端五大階段全面封頂 ✅

## 啟動方式
```bash
# 啟動 API 伺服器（開發模式）
uvicorn src.backend.api.main:app --reload

# 執行全部測試
python -m pytest tests/ -v

# 執行特定階段測試
python -m pytest tests/test_api.py -v
```

## 開發路線圖（建議後續方向）
1. **Dilution Operator** — 處理 StockDividendEvent 與 CorporateActionEvent（股票股利、分割、合併）
2. **具體 PriceProvider** — 如 YahooFinanceProvider 實作
3. **前端開發** — React/Vue 儀表板 UI，串接 `/api/v1/dashboard/*` 端點
