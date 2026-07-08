# 第七層｜Evidence Layer

> **依賴章節**：`00-overview.md`、`04-domain-models.md`（5.4 Evidence 模型、5.5 Rule Schema）、`10-analytics-dag.md`

---

## 第十二章　第七層｜Evidence Layer（邊界血緣壓縮，解決 E4）

### 12.1 血緣壓縮器

```python
# src/evidence/builder.py

def compress_lineage_horizon(event_timeline: list[FinancialEvent]) -> dict:
    """
    v2.1 邊界血緣壓縮：將龐大事件流壓縮為邊界特徵碼，保護 LLM 上下文空間。
    適用於全域時序型指標（NAV, XIRR, MDD, Volatility 等）。
    """
    if not event_timeline:
        return {"start_id": None, "end_id": None, "count": 0}
    return {
        "start_id": event_timeline[0].event_id,
        "end_id":   event_timeline[-1].event_id,
        "count":    len(event_timeline),
    }

def build_evidence(
    metric_key: str,
    value: float,
    metrics_bundle: MetricsBundle,
    rule: MetricRule,
    all_events: list[FinancialEvent],
    related_event_ids: list[str] = None,  # 點對點指標才傳入
) -> EvidenceEntry:
    """
    自動判斷指標類型並套用對應血緣策略：
    - 點對點型：source_event_ids = related_event_ids
    - 全域時序型（depends_on 的 DAG 深度 >= 2 或依賴 NAV）：
      source_event_range = compress_lineage_horizon(all_events)
    """
    ...
```

### 12.2 `evidence_rules.yaml` 結構（強型別，Versioned）

```yaml
schema_version: "2.1"

rules:
  - rule_id: RULE_CASH_RATIO
    metric_id: METRIC_CASH_RATIO
    metric_name: "現金比例"
    module: "模組四：資產配置分析"
    direction: higher_is_better_until_excess
    thresholds:
      - { max: 0.05, status: Critical,  priority: High,   label: "嚴重不足" }
      - { max: 0.10, status: Warning,   priority: Medium, label: "偏低" }
      - { max: 0.20, status: Good,      priority: Low,    label: "合理" }
      - { max: 0.35, status: Excellent, priority: Low,    label: "充裕" }
      - { max: 1.00, status: Warning,   priority: Medium, label: "過多，機會成本偏高" }
    benchmark: "10% ~ 20%"
    version: "1.0"
    effective_date: "2025-01-01"
    expired_date: null

  - rule_id: RULE_CASH_RATIO_V2
    metric_id: METRIC_CASH_RATIO
    metric_name: "現金比例"
    module: "模組四：資產配置分析"
    direction: higher_is_better_until_excess
    thresholds:
      - { max: 0.05, status: Critical,  priority: High }
      - { max: 0.12, status: Warning,   priority: Medium }
      - { max: 0.22, status: Good,      priority: Low }
      - { max: 0.40, status: Excellent, priority: Low }
      - { max: 1.00, status: Warning,   priority: Medium }
    benchmark: "12% ~ 22%"
    version: "2.0"
    effective_date: "2026-01-01"
    expired_date: null
```

### 12.3 版本選擇邏輯

```python
def get_effective_rule(metric_id: str, as_of_date: date, rules: list[MetricRule]) -> MetricRule:
    """
    給定 metric_id 與分析基準日 as_of_date，
    從所有版本中找出 effective_date <= as_of_date 且
    (expired_date is None OR expired_date > as_of_date) 的最新版本。
    若查無任何版本 → ERR009 FATAL。
    """
```

---
