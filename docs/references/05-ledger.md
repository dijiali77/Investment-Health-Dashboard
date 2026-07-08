# 第一層｜Ledger Layer

> **依賴章節**：`00-overview.md`、`03-input-data-model.md`、`04-domain-models.md`（5.1 FinancialEvent）

---

## 第六章　第一層｜Ledger Layer 設計原則

### 6.1 CSV → Event 轉換規則

| 原始來源 | 轉換為 | 規則 |
|---|---|---|
| `transactions.csv` 一筆 `BUY` | `SecurityTradeEvent(SECURITY_BUY)` | `cash_impact = -(qty×price + fee)` |
| `transactions.csv` 一筆 `SELL` | `SecurityTradeEvent(SECURITY_SELL)` | `cash_impact = +(qty×price - fee - tax)` |
| `bank_ledger.csv` category=`DIVIDEND` | `DividendEvent` | `cash_impact = +amount`；填入 `ex_dividend_date` 供應收股利模組使用 |
| `bank_ledger.csv` category=`CAPITAL_INJECTION` | `CashFlowEvent(CASH_DEPOSIT)` | `cash_impact = +amount` |
| `bank_ledger.csv` category=`CAPITAL_WITHDRAWAL` | `CashFlowEvent(CASH_WITHDRAW)` | `cash_impact = -amount` |
| `bank_ledger.csv` category=`TRADE_SETTLEMENT` | **不建立事件** | 用於交叉驗證，誤差 > 1 元 → `ERR005 WARNING` |
| `opening_snapshot.csv` | `OpeningBalanceEvent`（每個持股一筆 + 一筆現金）| `sequence_in_day = -1` |

### 6.2 事件排序規則

```
sequence_in_day 權重（數字小者優先）：
  -1  OPENING_BALANCE
   0  CASH_DEPOSIT
   1  DIVIDEND_RECEIVE / STOCK_DIVIDEND / CORPORATE_ACTION
   2  SECURITY_SELL
   3  SECURITY_BUY
   4  CASH_WITHDRAW
```

排序鍵：`(event_date, sequence_in_day, event_id)` — 完全確定性（deterministic）。

### 6.3 不可變性原則

`frozen=True`，錯誤更正以反向沖銷事件處理。`source_ref` 格式統一為 `{filename}:row_{N}`。

---
