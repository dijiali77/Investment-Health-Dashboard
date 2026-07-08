# 輸入資料模型（Input CSV Schema）

> **依賴章節**：`00-overview.md`（架構總覽）

---

## 第四章　輸入資料模型（Input CSV Schema）

### 4.1 `transactions.csv`（證券交易明細）

| 欄位 | 型別 | 說明 |
|---|---|---|
| `trade_date` | date | 交易日期 |
| `trade_type` | enum | `BUY` / `SELL` |
| `trade_category` | enum | `BOARD_LOT`（整張）/ `ODD_LOT`（零股）/ `AFTER_HOURS`（盤後）/ `SCHEDULED`（定期定額）|
| `stock_id` | str | 股票代號 |
| `stock_name` | str | 股票名稱 |
| `market` | enum | `TWSE`（上市）/ `TPEx`（上櫃）|
| `quantity` | int | 成交股數 |
| `price` | float | 成交均價 |
| `fee` | float | 手續費 |
| `tax` | float | 證交稅（賣出時收取）|
| `settlement_date` | date | 交割日（通常為 T+2）|
| `broker` | str | （選填）券商名稱，供行為分析 |

### 4.2 `bank_ledger.csv`（銀行交割戶進出記錄）

| 欄位 | 型別 | 說明 |
|---|---|---|
| `entry_date` | date | 帳務日期 |
| `category` | enum | `TRADE_SETTLEMENT` / `DIVIDEND` / `CAPITAL_INJECTION` / `CAPITAL_WITHDRAWAL` |
| `stock_id` | str | （選填，股利類有值）|
| `amount` | float | 金額（正數）|
| `dividend_per_share` | float | （選填）每股股利，供 `DividendEvent` 使用 |
| `ex_dividend_date` | date | 【v2.1 關鍵】除權息日，供應收股利模組使用 |
| `memo` | str | 備註 |

### 4.3 `opening_snapshot.csv`（選填，期初快照）

| 欄位 | 型別 | 說明 |
|---|---|---|
| `stock_id` | str | 股票代號 |
| `quantity` | int | 持有股數 |
| `average_cost` | float | 平均成本 |
| `cash_balance` | float | （僅現金行使用）期初現金餘額 |

---
