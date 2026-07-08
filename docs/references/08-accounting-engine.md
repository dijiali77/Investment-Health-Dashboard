# 第四層｜Accounting Engine

> **依賴章節**：`00-overview.md`、`04-domain-models.md`（5.3 Accounting 模型）、`07-portfolio-engine.md`

---

## 第九章　第四層｜Accounting Engine（權責發生制應收模組，解決 E2）

### 9.1 設計動機

> **E2 問題**（v2.0 漏洞）：除息日當天股價因除息跳空跌落，但現金股利尚未入帳，導致 NAV 當天虛擬暴跌，MDD 與波動度嚴重失真。
>
> **v2.1 解法**：採權責發生制（Accrual Basis）雙階段分錄，除息日即認列應收股利，維持 NAV 穩定。

### 9.2 權責發生制股利分錄規則

**階段一：除權息日（Ex-Dividend Date）**

當外部資料源或事件流標註某股票遭遇除息日時（`DividendEvent.ex_dividend_date` 不為 None）：

| 分錄方向 | 科目 | 金額 |
|---|---|---|
| 借（Debit）| `Dividend Receivable`（應收股利）| 當前持倉股數 × 每股股利 |
| 貸（Credit）| `Unrealized Dividend Income`（未實現股利收入）| 同上 |

效果：`BalanceSheetSnapshot.dividend_receivable` 增加，`net_worth` 保持穩定，NAV 不因除息跳空下跌。

**階段二：股利入帳付現日（`DIVIDEND_RECEIVE` 事件）**

| 分錄方向 | 科目 | 金額 |
|---|---|---|
| 借（Debit）| `Cash Balance`（現金資產）| 實際入帳金額 |
| 貸（Credit）| `Dividend Receivable`（應收股利）| 沖銷應收 |

效果：現金增加，應收股利歸零，`net_worth` 守恆，`CashFlowSnapshot.operating_dividend_received` 更新。

### 9.3 狀態變更矩陣（v2.1 完整版）

| 事件 | Cash Balance | Dividend Receivable | PortfolioState | Income Statement | Cash Flow |
|---|---|---|---|---|---|
| `OPENING_BALANCE` | 設定初始值 | — | 建立初始 FifoLot | — | — |
| `SECURITY_BUY` | `-= (qty×price + fee)` | — | 新增 FifoLot | — | Investing.Purchase `+=` |
| `SECURITY_SELL` | `+= (qty×price - fee - tax)` | — | 移除 FIFO Lots | Realized Gain `+=` | Investing.Proceeds `+=` |
| **除息日（被動觸發）** | **不變** | **+= 持倉×每股股利** | 不變 | — | — |
| `DIVIDEND_RECEIVE` | `+= (amount - withholding_tax)` | `-= 應收金額（沖銷）` | 不變 | Dividend Income `+=` | Operating.Dividend `+=` |
| `STOCK_DIVIDEND` | 不變 | — | **呼叫 Dilution Operator** | — | 揭露但淨現金流 = 0 |
| `CORPORATE_ACTION` | 不變 | — | **呼叫 Dilution Operator** | — | — |
| `CASH_DEPOSIT` | `+= amount` | — | 不變 | — | Financing.Injection `+=` |
| `CASH_WITHDRAW` | `-= amount` | — | 不變 | — | Financing.Withdrawal `+=` |

### 9.4 現金流量表：依用戶財務原則編製

1. **直接法**：逐筆事件歸類，不從損益表間接調整。
2. **時間差調整區塊**：`operating_adjustments` dict 明確列出所有非立即付現項目。
3. **大資金池**：Cash Balance 包含所有電子支付、活存、定存。
4. **投資活動總額揭露**：`investing_security_purchase`（負）與 `investing_security_proceeds`（正）分開揭露。
5. **籌資活動含本金轉入/提出**：利息支出（若有）亦歸此類。

---
