# 專案架構總覽

## 專案目標
建立一個投資組合健康儀表板（Investment Health Dashboard），能夠：
1. 從 CSV 檔案載入交易紀錄與銀行帳務資料
2. 以 FIFO 會計方式管理庫存與已實現損益
3. 結合市場行情資料（含 LOCF 補值演算法）
4. 計算未實現損益、資產配置權重、歷史淨值與報酬率
5. 透過 **Metric DAG 引擎** 驅動指標計算，確保依賴順序與計算效率
6. 提供 **投資組合健康評分**（0~100），七大維度量化評估
7. 透過 FastAPI 提供 RESTful API 供前端儀表板使用

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

### Phase 4b — Accounting Engine（雙階段股利會計引擎）
- `DividendReceivable`：應收股利領域模型（frozen dataclass），記錄：
  - `ex_dividend_date`：除權息日（權責發生基準）
  - `pay_date`：實際入帳日（現金流量基準）
  - `net_amount`：淨股利金額（已扣稅）
  - `is_settled`：是否已銷帳
- **雙階段權責發生制處理邏輯**：
  1. **第一階段（除權息日）**：`_handle_dividend()` 建立 `DividendReceivable` 記錄，不影響現金餘額，但計入應收股利
  2. **第二階段（入帳日）**：`_settle_dividend()` 將 `DividendReceivable` 標記為 `is_settled=True`，同時增加現金餘額
- `NavHistoryGenerator` 支援將應收股利計入每日淨值計算
- `DashboardService._calculate_dividend_receivable()` 提供未銷帳應收股利查詢

### Phase 5 — Application Service & API Layer（應用服務與 API 層）
- `DashboardService`：整合型 Service，串聯 CSV 載入 → Ledger → PortfolioEngine → MarketData → Metrics 完整管線
- FastAPI 路由：
  - `GET /api/v1/dashboard/summary` — 總資產市值、現金、未實現/已實現損益、資產配置、健康評分
  - `GET /api/v1/dashboard/allocation` — 詳細資產配置權重清單
  - `GET /api/v1/dashboard/nav-history` — 歷史淨值與報酬率時間序列
  - `GET /health` — 健康檢查

### Phase 6 — Analytics Layer（分析層）⭐ NEW

#### MetricRegistry（指標註冊表）
- 管理指標定義與依賴關係，提供 DAG 圖的建構與查詢介面
- 每個指標定義包含：`metric_id`、`description`、`depends_on`（依賴列表）、`fn`（計算函數）
- 支援動態註冊與取消註冊：
  - `register()` 自動驗證依賴是否存在（防止懸浮依賴）
  - `unregister()` 檢查是否有其他指標依賴（防止孤立節點）
- 提供 `get_dependency_graph()`、`get_root_metrics()`、`get_leaf_metrics()` 等查詢

#### DAGResolver（拓撲排序執行引擎）
- 使用 **Kahn's Algorithm** 進行拓撲排序，確保每個節點只被計算一次
- 核心流程：
  1. 從 MetricRegistry 取得 DAG
  2. 拓撲排序（Kahn's Algorithm）
  3. 按排序依序執行各 metric function，結果快取於 context dict
  4. 若偵測到循環依賴 → 拋出 `CycleDetectedError`
  5. 最終回傳完整 `MetricsBundle`
- 支援 `target_metrics` 參數，只計算需要的指標（自動收集傳遞依賴）
- **錯誤隔離**：單一節點計算失敗不影響其他節點，錯誤記錄於 `MetricsBundle.errors`
- 執行時間測量（`execution_time_ms`）

#### HealthScoreCalculator（投資組合健康評分）
七大維度量化評估，產出 0~100 的綜合健康得分：

| 維度 | 權重 | 評分邏輯 |
|------|------|----------|
| 持股集中度風險 | 20 | 單一持股 > 30% 扣分，> 60% 額外扣 5 分 |
| 現金留存比率 | 20 | 偏離理想值 15% 扣分，歸零扣 10 分 |
| 資產週轉率 | 15 | > 0.5 扣分，> 3.0 額外扣分 |
| 投資績效 | 15 | < 10% 遞減，< -10% 額外扣 5 分 |
| 風險管理 | 15 | 波動度、回撤、Sharpe 三項各 5 分 |
| 交易紀律 | 10 | 平均每檔 > 3 次扣分 |
| 多元化程度 | 5 | < 5 檔扣分，僅 1 檔額外扣 1 分 |

- 每項扣分附帶 **證據鏈（Evidence Chain）**：包含維度名稱、扣分原因描述、扣分數、嚴重程度（low/medium/high）
- `HealthScoreResult.to_dict()` 提供 JSON 可序列化輸出

#### DashboardService DAG 整合
```
RAW_INPUTS (root)
  ├── UNREALIZED_PNL
  ├── REALIZED_PNL
  ├── ALLOCATION
  └── CASH_BALANCE
       └── NAV_SUMMARY (depends on UNREALIZED_PNL + CASH_BALANCE)
            └── HEALTH_SCORE (depends on ALLOCATION + CASH_BALANCE + REALIZED_PNL + RAW_INPUTS)
```

## 模組地圖

```
src/backend/
├── __init__.py
├── ledger/                      # Phase 1
│   ├── __init__.py
│   ├── domain_models.py         # FinancialEvent 家族
│   ├── csv_converter.py         # CsvToEventConverter
│   └── event_sorting.py         # sort_events()
├── market_data/                 # Phase 2
│   ├── __init__.py
│   ├── provider_interface.py    # PriceProviderInterface
│   └── locf_operator.py         # apply_locf()
├── portfolio_engine/            # Phase 3 + 4b
│   ├── __init__.py
│   ├── lot.py                   # Lot, RealizedPnL
│   ├── fifo_accountant.py       # FifoAccountant
│   ├── engine.py                # PortfolioEngine（含雙階段股利）
│   └── dividend_receivable.py   # DividendReceivable（應收股利模型）
├── metrics/                     # Phase 4
│   ├── __init__.py
│   ├── unrealized_pnl.py        # UnrealizedPnlCalculator
│   ├── asset_allocation.py      # AssetAllocationCalculator
│   └── nav_history.py           # NavHistoryGenerator（含應收股利）
├── analytics/                   # Phase 6 ⭐ NEW
│   ├── __init__.py
│   ├── registry.py              # MetricRegistry + MetricDefinition
│   ├── dag_resolver.py          # DAGResolver + MetricsBundle + CycleDetectedError
│   └── health_score.py          # HealthScoreCalculator + HealthScoreResult
└── api/                         # Phase 5
    ├── __init__.py
    ├── dashboard_service.py     # DashboardService（DAG 驅動）
    ├── routes.py                # FastAPI 路由
    └── main.py                  # FastAPI 應用程式入口

tests/
├── test_market_data.py          # Phase 2 (20 tests)
├── test_portfolio_engine.py     # Phase 3 (40 tests)
├── test_metrics.py              # Phase 4 (22 tests)
├── test_accounting_engine.py    # Phase 4b (16 tests) ⭐ NEW
├── test_api.py                  # Phase 5 (24 tests)
└── test_analytics_dag.py        # Phase 6 (41 tests) ⭐ NEW
```

## 測試狀態
**163 tests passed in 1.34s** — 後端六大階段全面封頂 ✅

| 測試檔案 | 數量 | 涵蓋範圍 |
|----------|------|----------|
| `test_market_data.py` | 20 | LOCF 補值演算法 |
| `test_portfolio_engine.py` | 40 | FIFO 會計、庫存管理、股利處理 |
| `test_metrics.py` | 22 | 未實現損益、資產配置、NAV 歷史 |
| `test_accounting_engine.py` | 16 | 雙階段股利權責發生制 |
| `test_api.py` | 24 | DashboardService 整合、FastAPI 路由 |
| `test_analytics_dag.py` | 41 | Registry(13) + DAG(10) + HealthScore(14) + 整合(4) |
| **總計** | **163** | |

## 啟動方式
```bash
# 啟動 API 伺服器（開發模式）
uvicorn src.backend.api.main:app --reload

# 執行全部測試
python -m pytest tests/ -v

# 執行特定階段測試
python -m pytest tests/test_analytics_dag.py -v
```

## 開發路線圖（建議後續方向）

### Phase 7 — 前端整合
- 將 FastAPI 與 Streamlit 前端串接
- 在儀表板中展示健康評分雷達圖與扣分證據鏈

### Phase 8 — 進階風險指標
- Sharpe Ratio 計算器
- 最大回撤（Max Drawdown）計算器
- Beta / Alpha 係數

### Phase 9 — DAG 快取與增量計算
- 實作增量計算，避免重複計算
- 支援部分指標更新

### Phase 10 — Dilution Operator
- 處理 StockDividendEvent 與 CorporateActionEvent（股票股利、分割、合併）

### Phase 11 — 具體 PriceProvider
- YahooFinanceProvider 實作
- 支援多資料源切換
