# 輸出 Schema 完整範例（v3.0）

> **依賴章節**：`04-domain-models.md`、`11-evidence-layer.md`、`14-api-gateway.md`

---

## 第十八章　輸出 Schema 完整範例（v3.0）

```json
{
  "as_of_date": "2026-06-28",
  "pipeline_version": "3.0",
  "balance_sheet": {
    "as_of_date": "2026-06-28",
    "cash_balance": 320000,
    "dividend_receivable": 15000,
    "total_stock_value": 2150000,
    "total_etf_value": 4530000,
    "net_worth": 7015000
  },
  "income_statement": {
    "period_start": "2026-01-01",
    "period_end": "2026-06-28",
    "realized_pl": 185000,
    "dividend_income": 210000,
    "fee_expense": 8500,
    "tax_expense": 3200,
    "net_profit": 383300
  },
  "cash_flow_statement": {
    "period_start": "2026-01-01",
    "period_end": "2026-06-28",
    "operating_dividend_received": 210000,
    "operating_adjustments": {"dividend_receivable_change": 15000},
    "net_operating_cash": 210000,
    "investing_security_purchase": -1500000,
    "investing_security_proceeds": 320000,
    "investing_net_cash": -1180000,
    "financing_capital_injection": 600000,
    "financing_capital_withdrawal": 0,
    "financing_net_cash": 600000,
    "net_cash_change": -370000
  },
  "metrics_summary": {
    "xirr": 0.138,
    "max_drawdown": 0.21,
    "volatility_annualized": 0.165,
    "sharpe_ratio": 0.85
  },
  "health_score": {
    "total_score": 84.5,
    "grade": "B",
    "breakdown": {
      "wealth": 88.0,
      "performance": 82.0,
      "cashflow": 79.0,
      "allocation": 85.0,
      "risk": 87.0,
      "behavior": 81.0,
      "financial_freedom": 72.0
    },
    "score_version": "1.0"
  },
  "evidence_layer": [
    {
      "metric_id": "METRIC_CASH_RATIO",
      "metric_name": "現金比例",
      "module": "模組四：資產配置分析",
      "value": 0.0456,
      "formatted_value": "4.6%",
      "status": "Warning",
      "benchmark": "12% ~ 22%",
      "priority": "Medium",
      "confidence": "High",
      "rule_id": "RULE_CASH_RATIO_V2",
      "rule_version": "2.0",
      "lineage": {
        "derived_from": ["NAV", "CASH_BALANCE"],
        "source_event_ids": [],
        "source_event_range": null,
        "formula_id": "cash_ratio_v1",
        "formula_version": "1.0",
        "computed_at": "2026-06-28T10:23:45Z"
      }
    },
    {
      "metric_id": "METRIC_MDD",
      "metric_name": "最大回撤",
      "module": "模組五：風險管理",
      "value": 0.21,
      "formatted_value": "21.0%",
      "status": "Good",
      "benchmark": "< 25%",
      "priority": "Medium",
      "confidence": "High",
      "rule_id": "RULE_MDD_V1",
      "rule_version": "1.0",
      "lineage": {
        "derived_from": ["GROWTH_INDEX", "DAILY_RETURN", "NAV"],
        "source_event_ids": [],
        "source_event_range": {
          "start_id": "EVT-00000001",
          "end_id": "EVT-00000347",
          "count": 347
        },
        "formula_id": "mdd_growth_index",
        "formula_version": "1.0",
        "computed_at": "2026-06-28T10:23:45Z"
      }
    }
  ],
  "detected_events": [
    {
      "event_code": "EVT_DIVIDEND_BREAKTHROUGH",
      "title": "年度股利首次突破20萬",
      "severity": "Positive",
      "detected_at": "2026-06-28",
      "source_metric_ids": ["METRIC_DIVIDEND_INCOME"]
    }
  ],
  "telemetry_summary": {
    "Ledger.load_ms": 42.3,
    "MarketData.fetch_ms": 1205.7,
    "PortfolioEngine.process_ms": 88.1,
    "AccountingEngine.build_ms": 31.4,
    "Timeline.generate_ms": 198.6,
    "Analytics.dag_resolve_ms": 115.3,
    "Evidence.evaluate_ms": 12.2,
    "Pipeline.total_ms": 1693.6,
    "cache_hit_rate": 0.87,
    "errors": [
      {
        "code": "ERR001",
        "severity": "RECOVERABLE",
        "title": "PriceMissing",
        "detail": "2330 於 2026-06-27 無收盤價，LOCF 延用 2026-06-26 價格",
        "source_ref": "stock_id=2330, date=2026-06-27",
        "recoverable": true
      }
    ]
  }
}
```

---
