# 第八層｜Decision & Report Layer（LLM）

> **依賴章節**：`00-overview.md`、`11-evidence-layer.md`

---

## 第十三章　第八層｜Decision & Report Layer（LLM）

### 13.1 `decision_rules.yaml`（含版本）

```yaml
schema_version: "2.1"

rules:
  - rule_id: RULE_ACTION_CASH_CRITICAL
    version: "1.0"
    effective_date: "2025-01-01"
    when:
      metric: METRIC_CASH_RATIO
      status: Critical
    then:
      priority: High
      requires_root_cause: true
      action_hint: "建議於3個月內將現金比例提升至 benchmark 區間"

  - rule_id: RULE_ACTION_PASSIVE_INCOME_LOW
    version: "1.0"
    effective_date: "2025-01-01"
    when:
      metric: METRIC_PASSIVE_INCOME_COVERAGE
      operator: "<"
      value: 0.20
    then:
      priority: High
      action_hint: "提出具體增加被動收入（股利）來源之計畫"
```

### 13.2 `system_instructions.md`（v2.1 版）

```
你是擁有20年經驗的CFO/PM/WM。

鐵則：
1. 不得重新計算任何數值。所有數字必須直接引用 Evidence JSON 中的 metric_id 與 value。
2. 每一項建議必須包含七個欄位：
   Observation, Evidence(引用metric_id), Root Cause, Risk,
   Recommendation, Priority, Confidence
3. 若 Evidence 不足以支撐某項推論，必須明確標註「資料不足，無法推論」，
   不得臆測或杜撰原因。
4. Root Cause 的推論必須基於 detected_events（FinancialEventSignal）
   或多項 Evidence 的交叉比對，不得憑空想像。
5. [v2.1] 引用指標時，若 EvidenceEntry.lineage 揭露資料來源，
   必須標明該指標的 confidence 等級（High/Medium/Low）以及
   formula_version，確保報告讀者知道計算基礎。
6. [v2.1] 若 lineage.source_event_range 存在（全域時序型指標），
   應標示「基於 EVT-{start} ~ EVT-{end} 共 {count} 筆歷史事件計算」。
7. 最終輸出依序為：七大模組分析 → 投資健康評分(0-100,A-E級) →
   優勢前三 → 風險前三 → 短期/中期/長期建議 → 一頁式董事會摘要(≤300字)。
```

---
