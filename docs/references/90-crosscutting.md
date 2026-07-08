# 橫切關注點（Crosscutting Concerns）

> **依賴章節**：`00-overview.md`；本檔內容適用於所有層級（01～15），所有實作者皆須閱讀

---

## 第十七章　橫切關注點（Crosscutting Concerns）

### 15.1 Versioning（解決 P5）

| 物件 | 版本欄位 | 有效期欄位 | 廢止欄位 |
|---|---|---|---|
| MetricRule | `version` | `effective_date` / `expired_date` | `deprecated_by` |
| DecisionRule | `version` | `effective_date` | — |
| ScoringWeights | `version` | `effective_date` | — |
| MetricFormula | `formula_version` | — | — |
| FinancialEvent | `schema_version` | — | — |

**歷史報告重建場景**：給定 `as_of_date = 2025-06-30`，系統透過 `get_effective_rule(metric_id, as_of_date=2025-06-30)` 自動選用當時生效的規則版本。

**無風險利率版本化**：`RISK_FREE_RATE` 需記錄歷史值（例如台灣銀行一年期定存：2025 年 1.6%，2026 年 2.0%），供 Sharpe 歷史計算使用。

### 15.2 Telemetry Layer（解決 P9）

```python
# src/telemetry/tracer.py
from contextlib import contextmanager

class LayerTracer:
    @contextmanager
    def trace(self, layer_name: str):
        start = time.perf_counter()
        yield
        elapsed_ms = (time.perf_counter() - start) * 1000
        self._record(layer_name, elapsed_ms)

    def get_summary(self) -> dict[str, float]:
        """回傳各層執行耗時（ms），注入 OutputPayload.telemetry_summary"""
```

**必須量測的關鍵指標**：

| 量測點 | 說明 | v2.1 目標耗時 |
|---|---|---|
| `Ledger.load` | CSV 載入與事件轉換耗時 | ≤ 100ms |
| `MarketData.fetch` | Provider API 呼叫耗時（含 LOCF）| ≤ 2000ms |
| `PortfolioEngine.process` | 事件重放耗時 | ≤ 200ms |
| `AccountingEngine.build` | 三表建構耗時 | ≤ 100ms |
| `Timeline.generate` | **單次線性掃描耗時（v2.1）** | ≤ 300ms |
| `Analytics.dag_resolve` | Metric DAG 執行耗時 | ≤ 150ms |
| `Evidence.evaluate` | 規則比對 + 血緣壓縮耗時 | ≤ 50ms |
| `Pipeline.total` | 整條 Pipeline 端對端耗時 | ≤ 3000ms |

### 15.3 Error Domain（解決 P7）

```python
# 正確做法
try:
    price = provider.get_price(stock_id, date)
except ProviderError:
    error = DomainError(
        code="ERR008",
        severity=ErrorSeverity.RECOVERABLE,
        title="ProviderUnavailable",
        detail=f"Provider {provider.provider_name()} 暫時無法存取",
        source_ref=f"stock_id={stock_id}, date={date}",
        recoverable=True,
    )
    error_registry.record(error)
    price = last_known_price(stock_id)  # LOCF 降級處理
    confidence_tracker.set(stock_id, "Medium")
```

---
