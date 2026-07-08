# 第六層｜Analytics Layer：Metric DAG 引擎

> **依賴章節**：`00-overview.md`、`09-timeline-projection.md`

---

## 第十一章　第六層｜Analytics Layer：Metric DAG 引擎

### 11.1 矩陣輸入式指標計算（v2.1）

由於第五層直接輸出 `BalanceSheetSnapshot[]` 時序序列，第六層的指標函數**被嚴格禁止重新呼叫重放引擎**：

1. `compute_nav_series()` 直接從 `list[BalanceSheetSnapshot]` 提取 `net_worth`，形成 $NAV_{Timeline}$ 向量。
2. `compute_daily_return()` 接收 $NAV_{Timeline}$ 向量與現金流量時序，一次性矩陣化計算每日報酬率向量。
3. 拓樸排序（DAG Resolver）按順序向後推進，每個中間向量只計算一次。

### 11.2 Metric Dependency Graph（DAG）

```
NAV (每日淨資產，含 dividend_receivable)
  └─► DailyReturn (修正式 Dietz 調整後每日報酬率)
        ├─► GrowthIndex (累積成長指數)
        │     ├─► MDD (最大回撤)
        │     └─► RollingReturn (滾動報酬)
        ├─► Volatility (年化波動度)
        │     ├─► SharpeRatio
        │     └─► SortinoRatio
        └─► XIRR (另需 CashFlowTimeSeries)

CashFlowTimeSeries ──► XIRR
PortfolioState ──────► AllocationMetrics
IncomeStatement ─────► DividendYield / PassiveIncomeCoverage
BehaviorEvents ──────► WinRate / ProfitLossRatio / HoldingDays
```

### 11.3 `config/metric_dag.yaml` 定義格式

```yaml
metrics:
  nav:
    metric_id: NAV
    description: "每日淨資產（現金 + 應收股利 + 持倉市值）"
    depends_on: []
    module: nav
    function: nav.compute_nav

  daily_return:
    metric_id: DAILY_RETURN
    description: "修正式 Dietz 調整後每日報酬率"
    depends_on: [NAV]
    module: returns
    function: returns.compute_daily_return

  growth_index:
    metric_id: GROWTH_INDEX
    description: "累積成長指數，排除外部金流影響"
    depends_on: [DAILY_RETURN]
    module: returns
    function: returns.compute_growth_index

  max_drawdown:
    metric_id: MDD
    description: "基於 GrowthIndex 計算之最大回撤"
    depends_on: [GROWTH_INDEX]
    module: risk
    function: risk.compute_mdd

  volatility:
    metric_id: VOLATILITY
    description: "年化波動度"
    depends_on: [DAILY_RETURN]
    module: risk
    function: risk.compute_volatility

  sharpe_ratio:
    metric_id: SHARPE
    description: "Sharpe Ratio（使用 settings.py 中之無風險利率）"
    depends_on: [DAILY_RETURN, VOLATILITY]
    module: risk
    function: risk.compute_sharpe
```

### 11.4 `MetricRegistry` + `DAGResolver` 介面

```python
# src/analytics/registry.py
class MetricRegistry:
    def register(self, metric_id: str, fn: Callable, depends_on: list[str]): ...
    def get_all_metric_ids(self) -> list[str]: ...
    def get_dependency_graph(self) -> dict[str, list[str]]: ...

# src/analytics/dag_resolver.py
class DAGResolver:
    """
    1. 從 MetricRegistry 取得 DAG
    2. 拓樸排序（Kahn's Algorithm）
    3. 按排序依序執行各 metric function，結果快取於 context dict
    4. 若偵測到循環依賴 → ERR010 FATAL
    5. 最終回傳完整 MetricsBundle
    """
    def resolve(self, registry: MetricRegistry, inputs: dict) -> MetricsBundle: ...
```

### 11.5 關鍵公式（精確定義，禁止偏差）

**修正式 Dietz 日報酬率**：

$$r_t = \frac{NAV_t - CF_t - NAV_{t-1}}{NAV_{t-1}}$$

其中 $NAV_t$ 已含 `dividend_receivable`（應收股利），確保除息日 NAV 穩定。

**GrowthIndex（累積成長指數）**：

$$G_t = G_{t-1} \times (1+r_t)$$

**最大回撤（MDD）**：

$$MDD_T = \max_{t \in [0,T]}\left(\frac{\max_{\tau \le t} G_\tau - G_t}{\max_{\tau \le t} G_\tau}\right)$$

**波動度**：$\text{std}(r_t) \times \sqrt{252}$

**XIRR**：使用 `scipy.optimize.brentq` 求解 $\sum_{i} \frac{CF_i}{(1+r)^{t_i}} = 0$。

### 11.6 投資健康評分

七大模組權重：財富成長 20% / 投資績效 20% / 現金流健康 15% / 資產配置 15% / 風險管理 15% / 交易紀律 10% / 財務自由 5%。子分數轉換規則存於 `scoring_weights.yaml`，含版本化機制。

---
