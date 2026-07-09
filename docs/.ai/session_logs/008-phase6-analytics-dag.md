# Phase 6：Analytics Layer（分析層）— Metric DAG 引擎與健康評分

**日期：** 2026-07-09  
**負責人：** AI Assistant (Cline)  
**狀態：** ✅ 完成

---

## 概述

本階段建立 **Analytics Layer（分析層）**，提供：
1. **MetricRegistry** — 指標註冊表，管理指標定義與依賴關係
2. **DAGResolver** — 拓撲排序執行引擎（Kahn's Algorithm），確保每個節點只計算一次
3. **HealthScoreCalculator** — 投資組合健康評分算子（0~100），七大維度評估
4. **DashboardService DAG 整合** — 將 summary 查詢改由 DAG 引擎驅動

---

## 新增檔案

| 檔案 | 說明 |
|------|------|
| `src/backend/analytics/__init__.py` | 模組匯出 |
| `src/backend/analytics/registry.py` | MetricRegistry + MetricDefinition |
| `src/backend/analytics/dag_resolver.py` | DAGResolver + MetricsBundle + CycleDetectedError |
| `src/backend/analytics/health_score.py` | HealthScoreCalculator + HealthScoreResult |
| `tests/test_analytics_dag.py` | 完整測試（41 項） |

## 修改檔案

| 檔案 | 變更內容 |
|------|----------|
| `src/backend/api/dashboard_service.py` | 重構為 DAG 引擎驅動，新增 health_score 回傳 |
| `tests/test_api.py` | summary 驗證加入 health_score 鍵值 |

---

## 核心實作細節

### 1. MetricRegistry

- `register(metric_id, description, depends_on, fn)` — 動態註冊指標
- 驗證依賴存在（防止懸浮依賴）
- `unregister()` — 檢查是否有其他指標依賴（防止孤立）
- `get_dependency_graph()` — 回傳完整 DAG
- `get_root_metrics()` / `get_leaf_metrics()` — 根節點與葉節點查詢

### 2. DAGResolver

- 使用 **Kahn's Algorithm** 進行拓撲排序
- 支援 `target_metrics` 參數，只計算需要的指標（自動收集傳遞依賴）
- 錯誤隔離：單一節點計算失敗不影響其他節點
- 執行時間測量（`execution_time_ms`）

### 3. HealthScoreCalculator

七大維度評分：

| 維度 | 權重 | 主要扣分規則 |
|------|------|-------------|
| 持股集中度風險 | 20 | 單一持股 > 30% 扣分，> 60% 額外扣 |
| 現金留存比率 | 20 | 偏離理想值 15% 扣分，歸零扣 10 |
| 資產週轉率 | 15 | > 0.5 扣分，> 3.0 額外扣 |
| 投資績效 | 15 | < 10% 遞減，< -10% 額外扣 |
| 風險管理 | 15 | 波動度、回撤、Sharpe 三項各 5 分 |
| 交易紀律 | 10 | 平均每檔 > 3 次扣分 |
| 多元化程度 | 5 | < 5 檔扣分，僅 1 檔額外扣 |

### 4. DashboardService DAG 整合

```
RAW_INPUTS (root)
  ├── UNREALIZED_PNL
  ├── REALIZED_PNL
  ├── ALLOCATION
  └── CASH_BALANCE
       └── NAV_SUMMARY (depends on UNREALIZED_PNL + CASH_BALANCE)
            └── HEALTH_SCORE (depends on ALLOCATION + CASH_BALANCE + REALIZED_PNL + RAW_INPUTS)
```

---

## 測試結果

```
163 passed in 1.34s
```

| 測試檔案 | 數量 | 說明 |
|----------|------|------|
| `test_accounting_engine.py` | 16 | 雙階段股利會計 |
| `test_analytics_dag.py` | 41 | Registry(13) + DAG(10) + HealthScore(14) + 整合(4) |
| `test_api.py` | 24 | DashboardService + FastAPI 路由 |
| `test_market_data.py` | 20 | LOCF 補值 |
| `test_metrics.py` | 22 | 未實現損益 + 資產配置 + NAV 歷史 |
| `test_portfolio_engine.py` | 40 | FIFO 會計 + 庫存管理 |

---

## 已知事項

- `HealthScoreCalculator` 的 `turnover_rate` 計算目前使用簡化版（已實現損益 / 總市值），未來可改用更精確的公式
- DAG 引擎目前無持久化快取，每次 `resolve()` 都會重新計算所有指標
- `CycleDetectedError` 的測試透過直接操作 `_metrics` 內部 dict 來製造循環，這是因為 `register()` 會防止循環註冊

---

## 下一步建議

1. **Phase 7：前端整合** — 將 FastAPI 與 Streamlit 前端串接
2. **Phase 8：進階指標** — 加入 Sharpe Ratio、最大回撤、Beta 等風險指標
3. **Phase 9：DAG 快取** — 實作增量計算，避免重複計算
