# Phase 5.5：雙階段股利會計引擎（Dividend Accounting Engine）

## 概述

本階段實作了完整的雙階段股利會計引擎，解決了股利事件在除權息日與發放日之間的會計處理問題。核心概念是引入 `DividendReceivable` 領域模型，將股利事件拆分為兩個階段處理。

## 新增檔案

### `src/backend/portfolio_engine/dividend_receivable.py`
- `DividendReceivable`：frozen dataclass，代表一筆應收股利記錄
  - 自動計算 `net_amount = gross_amount - withholding_tax`
  - `settle()` 方法回傳已銷帳的新實例（不可變性）
  - 欄位：`receivable_id`, `stock_id`, `ex_dividend_date`, `payment_date`, `total_shares`, `dividend_per_share`, `gross_amount`, `withholding_tax`, `net_amount`, `is_settled`

### `tests/test_accounting_engine.py`
- 16 項測試，涵蓋：
  - `DividendReceivable` 領域模型（建立、自動計算、不可變性、settle）
  - PortfolioEngine 雙階段處理（第一階段產生應收、第二階段銷帳）
  - NAV 計算包含應收股利（除權息日後 NAV 不變、發放日現金增加）
  - DashboardService 整合

## 修改檔案

### `src/backend/portfolio_engine/engine.py`
- 新增 `dividend_receivables: List[DividendReceivable]` 屬性
- 新增 `_handle_dividend()` 方法：
  - 第一階段（ex_dividend_date == event_date）：產生未銷帳應收股利
  - 第二階段（ex_dividend_date != event_date）：尋找對應未銷帳記錄並銷帳
- `reset()` 方法新增清除 `dividend_receivables`
- `process_events()` 中對 `DividendEvent` 調用 `_handle_dividend()`

### `src/backend/portfolio_engine/__init__.py`
- 匯出 `DividendReceivable`

### `src/backend/metrics/nav_history.py`
- `generate()` 方法中，處理 `DividendEvent` 第二階段時，從 `dividend_receivables` 尋找已銷帳記錄並增加現金

### `src/backend/api/dashboard_service.py`
- 新增 `_calculate_dividend_receivable()` 方法
- `_calculate_cash_balance()` 加入註解說明不包含應收股利

## 設計決策

1. **不可變性（Frozen Dataclass）**：`DividendReceivable` 使用 `frozen=True`，確保記錄不會被意外修改。銷帳透過 `settle()` 回傳新實例。
2. **雙階段識別**：透過比較 `DividendEvent.ex_dividend_date` 與 `event_date` 來區分第一/第二階段。
3. **NAV 計算**：除權息日後 NAV 不變（市值下降但應收股利補償），發放日現金增加。
4. **DashboardService 整合**：提供 `_calculate_dividend_receivable()` 方法供前端查詢未實現應收股利。

## 測試結果

```
122 passed in 1.59s
```

## 下一步建議

1. 前端顯示「應收股利」欄位
2. 支援股利再投資（DRIP）場景
3. 支援股票股利（Stock Dividend）處理
