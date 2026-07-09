# Session Log 004 — Phase 3 Portfolio Engine

## Agent 身份
Cline（後端開發代理）

## 驗收條件逐項核對
- [x] 在 `src/backend/portfolio_engine/` 底下建立包結構。
- [x] 實作會計帳算子，核心支援 FIFO（先進先出）銷帳邏輯。
- [x] 當發生部分賣出時，正確計算過往 Lots 的稀釋與剩餘成本。
- [x] 在 `tests/` 底下建立對應的單元測試，完整驗證多筆買入、部分賣出後的持股成本與實現損益是否完全正確。
- [x] 執行 `pytest` 驗證，全數通過（60 passed in 0.66s，含 Phase 2 測試無回歸）。

## 完成事項
- 建立 `src/backend/portfolio_engine/__init__.py`：匯出 `Lot`、`RealizedPnL`、`FifoAccountant`、`PortfolioEngine`。
- 建立 `src/backend/portfolio_engine/lot.py`：`Lot`（持股批次）與 `RealizedPnL`（實現損益）資料模型，皆為 frozen dataclass。
  - `Lot.dilute()`：按比例計算賣出部分的成本基礎與實現損益。
  - `Lot.apply_dilution()`：支援股票股利/分割/合併的稀釋計算。
- 建立 `src/backend/portfolio_engine/fifo_accountant.py`：`FifoAccountant` FIFO 會計帳。
  - 為每檔股票維護獨立的 `deque[Lot]` 佇列。
  - `add_buy()`：買入建 Lot，加入佇列尾端。
  - `add_sell()`：從佇列前端開始銷帳，支援跨 Lot 賣出。
  - 庫存不足與無庫存時拋出明確錯誤。
  - 查詢介面：總股數、總成本、平均成本、已實現損益。
- 建立 `src/backend/portfolio_engine/engine.py`：`PortfolioEngine` 投資組合引擎。
  - 接收 `FinancialEvent` 序列，僅處理 `SecurityTradeEvent`（BUY/SELL）。
  - 非交易事件（股利等）自動忽略。
  - 持倉摘要與損益摘要查詢。
- 建立 `tests/test_portfolio_engine.py`：40 項單元測試，涵蓋：
  - Lot 資料模型（13 項）：建立、屬性、frozen、dilute 完全/部分/超額/零股、apply_dilution 股利/分割/合併
  - RealizedPnL 資料模型（2 項）：建立、frozen
  - FifoAccountant（15 項）：買入建 Lot、多筆買入、完全賣出、部分賣出、跨 Lot 賣出、虧損賣出、庫存不足/無庫存錯誤、查詢介面、重置、多檔股票獨立
  - PortfolioEngine（10 項）：單一買入、買入後完全賣出、買入後部分賣出、多筆買入跨 Lot 賣出、多檔股票、非交易事件忽略、重置、未買入賣出錯誤、超額賣出錯誤

## 目前阻塞（Blockers）
無

## 給下一個 Agent 的上下文
- Phase 3 (Portfolio Engine) 已完整實作，包含 FIFO 會計帳與事件驅動引擎。
- 所有 60 項測試已通過（pytest 0.66s），Phase 2 測試無回歸。
- 接著可進入 Phase 4：Dilution Operator（股票股利/分割/合併處理）或 Portfolio Analytics（報酬率計算、績效指標）。

## 待辦事項（Pending Tasks for Next Agent）
1. 實作 Dilution Operator（處理 StockDividendEvent 與 CorporateActionEvent）。
2. 實作 Portfolio Analytics（報酬率計算、績效指標、圖表資料）。
3. 實作具體的 PriceProvider（如 YahooFinanceProvider）。

## 本次變更檔案
- src/backend/portfolio_engine/__init__.py（新增）
- src/backend/portfolio_engine/lot.py（新增）
- src/backend/portfolio_engine/fifo_accountant.py（新增）
- src/backend/portfolio_engine/engine.py（新增）
- tests/test_portfolio_engine.py（新增）

## Commit
feat(portfolio-engine): implement FIFO accountant and event-driven portfolio engine
