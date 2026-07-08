# 第三層｜Portfolio Engine

> **依賴章節**：`00-overview.md`、`04-domain-models.md`（5.3 Portfolio 模型）、`05-ledger.md`

---

## 第八章　第三層｜Portfolio Engine（Lots 稀釋算子，解決 E3）

### 8.1 設計動機

> **E3 問題**（v2.0 漏洞）：v2.0 的 `StockDividendEvent` 處理邏輯在 FIFO 佇列尾端 `append` 一個新的 `FifoLot`（`unit_cost = 0`）。這將導致：FIFO 賣出時，最舊批次（高成本）的股票仍在前面，無成本的股利股票在尾端永遠不會被賣到，造成損益計算嚴重扭曲。
>
> **v2.1 解法**：採 Lots 稀釋算子（Dilution Operator），**嚴禁追加新 Lot**，改為原位（In-place）依比例稀釋所有現存 Lots。

### 8.2 Dilution Operator 實作規格

```python
# src/portfolio/fifo_engine.py

def apply_dilution_operator(open_lots: list[FifoLot], ratio: float) -> list[FifoLot]:
    """
    v2.1 Lots 稀釋算子公式：
    - 遍歷當前該股票所有未平倉的 open_lots
    - 對於每一個 Lot，在原位（In-place）重新計算其 quantity 與 unit_cost

    公式：
      New Quantity = floor(Old Quantity * ratio)  # 無條件捨去至整數股，台股不足一股轉現金
      New Unit Cost = (Old Unit Cost / ratio) * (Old Quantity / New Quantity)
      # 確保總成本（Cost Basis）守恆：Old Quantity * Old Unit Cost ≈ New Quantity * New Unit Cost

    成本守恆驗證（強制）：
      abs(sum(lot.quantity * lot.unit_cost for lot in updated_lots) -
          sum(lot.quantity * lot.unit_cost for lot in open_lots)) ≤ 0.01
      若誤差 > 0.01 → ERR012 WARNING

    完整保留 open_event_id（原始交易血緣不中斷）。
    """
    updated_lots = []
    for lot in open_lots:
        new_qty = int(lot.quantity * ratio)  # floor
        if new_qty == 0:
            continue
        new_unit_cost = (lot.unit_cost / ratio) * (lot.quantity / new_qty)
        updated_lots.append(
            FifoLot(
                lot_id=lot.lot_id,
                stock_id=lot.stock_id,
                open_date=lot.open_date,
                open_event_id=lot.open_event_id,  # 完整保留原始交易血緣
                quantity=new_qty,
                unit_cost=new_unit_cost
            )
        )
    return updated_lots
```

### 8.3 Portfolio Engine 責任範圍

```
Portfolio Engine 只做：
  ✅ 維護每個 stock_id 的 FIFO 佇列（FifoLot deque）
  ✅ 處理 SecurityTradeEvent → 更新持倉 / 計算 Realized P&L
  ✅ 處理 StockDividendEvent → 呼叫 apply_dilution_operator（嚴禁 append）
  ✅ 處理 CorporateActionEvent → 呼叫 apply_dilution_operator（嚴禁 append）
  ✅ 輸出 PortfolioState（持倉快照 + 現金餘額）

  ❌ 不碰 BalanceSheet / IncomeStatement / CashFlow
  ❌ 不感知 Evidence / Analytics 的存在
```

### 8.4 FIFO 撮合邏輯

- 買進：`deque.append(FifoLot(lot_id, open_event_id=event_id, ...))`
- 賣出：從 `deque[0]` 依序扣除，計算每個 Lot 的 Realized P&L
- 股票股利 / 分割：**呼叫 `apply_dilution_operator(open_lots, ratio)`，原位更新，不追加**
- 公司行動（合併）：同上，`ratio < 1.0`，股數縮減、成本提高

### 8.5 `open_event_id` 的血緣意義

```
EvidenceEntry (METRIC_UNREALIZED_PL)
  └─ lineage.source_event_ids = ["EVT-00000042", "EVT-00000051"]
       └─ FifoLot.open_event_id = "EVT-00000042"
            └─ SecurityTradeEvent.source_ref = "transactions.csv:row_42"
```

---
