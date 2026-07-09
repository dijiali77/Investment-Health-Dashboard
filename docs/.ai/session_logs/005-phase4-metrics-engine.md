# Session Log 005 — Phase 4 Health Metrics Engine

## Agent 身份
Cline（後端開發代理）

## 驗收條件逐項核對
- [x] 在 `src/backend/metrics/` 底下建立包結構。
- [x] 實作「未實現損益 (Unrealized PnL) 算子」：結合 PortfolioEngine 持股 Lot 與 Market Data 最新/特定日期收盤價（調用 apply_locf），計算即時帳面損益。
- [x] 實作「資產配置比例 (Asset Allocation) 算子」：計算各檔標的在投資組合中的即時市值權重（%）。
- [x] 實作「投資組合歷史淨值 (Portfolio NAV History) 序列生成」：給定時間區間，結合歷史事件與每日市場價格，產出每日總市值、總資產淨值曲線數據。
- [x] 在 `tests/` 底下建立 `test_metrics.py`，設計測試案例驗證未實現損益計算、歷史淨值曲線生成的正確性。
- [x] 執行 `pytest` 驗證，全數通過（82 passed in 0.90s，含 Phase 1~3 無回歸）。

## 完成事項
- 建立 `src/backend/metrics/__init__.py`：匯出 `UnrealizedPnlCalculator`、`AssetAllocationCalculator`、`NavHistoryGenerator`。
- 建立 `src/backend/metrics/unrealized_pnl.py`：`UnrealizedPnlCalculator`
  - `calculate()`：單一日期計算，支援最新價格或指定日期（透過 apply_locf 補值）。
  - `calculate_time_series()`：每日未實現損益時間序列。
  - 回傳各股票明細（數量、成本、市價、未實現損益、損益%）與總計。
- 建立 `src/backend/metrics/asset_allocation.py`：`AssetAllocationCalculator`
  - `calculate()`：計算各股票市值權重，按權重降序排列。
  - `calculate_time_series()`：每日資產配置時間序列。
- 建立 `src/backend/metrics/nav_history.py`：`NavHistoryGenerator`
  - `generate()`：逐日回放事件 + LOCF 補值，產出每日現金、市值、總淨值、日報酬率、累積報酬率。
  - 預先對各股票市場資料做 LOCF 快取，避免重複計算。
  - 支援期初現金餘額、事件現金流追蹤。
- 建立 `tests/test_metrics.py`：22 項單元測試，涵蓋：
  - UnrealizedPnlCalculator（9 項）：最新價格、指定日期+LOCF、日期早於資料、多檔股票、無持股、無市場資料、虧損、部分賣後、時間序列
  - AssetAllocationCalculator（5 項）：單一股票 100%、多檔權重、降序排序、無持股、時間序列
  - NavHistoryGenerator（8 項）：無事件、買入後淨值、買入賣出淨值、多檔股票、日報酬率、累積報酬率、市場缺口 LOCF、無市場資料

## 目前阻塞（Blockers）
無

## 給下一個 Agent 的上下文
- Phase 4 (Metrics Engine) 已完整實作，包含未實現損益、資產配置、歷史淨值曲線。
- 所有 82 項測試已通過（pytest 0.90s），Phase 1~3 無回歸。
- 接著可進入 Phase 5：Dilution Operator（股票股利/分割/合併處理）或具體的 PriceProvider 實作（如 YahooFinanceProvider）。

## 待辦事項（Pending Tasks for Next Agent）
1. 實作 Dilution Operator（處理 StockDividendEvent 與 CorporateActionEvent）。
2. 實作具體的 PriceProvider（如 YahooFinanceProvider）。
3. 實作前端 API 層（FastAPI endpoints）。

## 本次變更檔案
- src/backend/metrics/__init__.py（新增）
- src/backend/metrics/unrealized_pnl.py（新增）
- src/backend/metrics/asset_allocation.py（新增）
- src/backend/metrics/nav_history.py（新增）
- tests/test_metrics.py（新增）

## Commit
feat(metrics): implement unrealized PnL, asset allocation, and NAV history generators
