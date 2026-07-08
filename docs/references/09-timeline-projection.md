# 第五層｜Timeline Projection Layer

> **依賴章節**：`00-overview.md`、`06-market-data.md`、`07-portfolio-engine.md`、`08-accounting-engine.md`

---

## 第十章　第五層｜Timeline Projection Layer（重構，解決 E1）

### 10.1 設計動機

> **E1 問題**（v2.0 漏洞）：v2.0 的 `replay_to(target_date)` 每次重放所有事件至指定日期。若計算整個分析期間每一天的狀態，複雜度為 $O(N \times D)$（N = 事件數，D = 天數），隨事件增加效能雪崩。
>
> **v2.1 解法**：廢除單日時態重放機制，改為 Timeline Projector 單次線性掃描，複雜度降至 $O(N + D)$。

### 10.2 Timeline Projector 核心引擎

```python
# src/projections/timeline_engine.py
from datetime import date, timedelta
from src.ledger.models import FinancialEvent
from src.market_data.provider_interface import PriceProvider

def generate_state_timeline_matrix(
    start_date: date,
    end_date: date,
    events: list[FinancialEvent],
    price_provider: PriceProvider,
    rule_version: Optional[str] = None,
) -> dict[str, list]:
    """
    v2.1 矩陣投影核心（純函式，複雜度 O(N + D)）：

    前置步驟：
    1. 透過 price_provider.get_aligned_daily_prices(stock_ids, start_date, end_date)
       取得無中斷的日線價格矩陣（所有 Provider 已確保 LOCF 補值）

    單次線性掃描主迴圈（僅允許一層 for loop 遍歷日期）：
    2. 建立事件指針（按 (event_date, sequence_in_day, event_id) 排序）
    3. for today in date_range(start_date, end_date):
         a. 處理所有 event_date == today 的事件：
            - 觸發 portfolio_engine.process(event) → 更新 Portfolio 佇列與會計科目
            - 觸發 accounting_engine.apply_journal(event) → 更新分錄
         b. 若 today 為某股票的 ex_dividend_date → 觸發應收股利分錄
         c. 依據 aligned_prices[today] 結算今日持倉市值
         d. 建立今日 BalanceSheetSnapshot, IncomeStatementSnapshot, CashFlowSnapshot
         e. 灌入時序矩陣
    4. 一次性回傳三個報表的時序序列

    嚴格禁止：
    ❌ 任何形式的雙重迴圈（如 for date in range: for event in events）
    ❌ 呼叫 replay_to() 或任何具有 O(N×D) 特徵的重放邏輯
    """
    # [具體線性掃描演算法由 Cline 依此邏輯編寫實作]
    timeline_balance_sheet    = []  # list[BalanceSheetSnapshot]
    timeline_income_statement = []  # list[IncomeStatementSnapshot]
    timeline_cash_flow        = []  # list[CashFlowSnapshot]
    ...
    return {
        "balance_sheets":     timeline_balance_sheet,
        "income_statements":  timeline_income_statement,
        "cash_flows":         timeline_cash_flow,
    }
```

---
