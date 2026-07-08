# 核心領域模型（Pydantic v2 Schema）

> **依賴章節**：`00-overview.md`、`03-input-data-model.md`

---

## 第五章　核心領域模型（Pydantic v2 Schema）

### 5.1 FinancialEvent 繼承體系

> **v1.0 問題**：單一扁平 `FinancialEvent` 缺乏業務語義。**v2.0 解法**：採繼承體系。**v2.1 補充**：`CorporateActionEvent.ratio` 欄位定義明確化（2:1 分割 = `ratio=2.0`；每股配 0.2 股股票股利 = `ratio=1.2`）。

```python
from enum import Enum
from datetime import date
from typing import Optional, Literal
from pydantic import BaseModel, Field

# ── 基底枚舉 ────────────────────────────────────────────────────

class EventType(str, Enum):
    SECURITY_BUY     = "SECURITY_BUY"
    SECURITY_SELL    = "SECURITY_SELL"
    DIVIDEND_RECEIVE = "DIVIDEND_RECEIVE"
    STOCK_DIVIDEND   = "STOCK_DIVIDEND"
    CORPORATE_ACTION = "CORPORATE_ACTION"
    CASH_DEPOSIT     = "CASH_DEPOSIT"
    CASH_WITHDRAW    = "CASH_WITHDRAW"
    OPENING_BALANCE  = "OPENING_BALANCE"

class TradeCategory(str, Enum):
    BOARD_LOT   = "BOARD_LOT"
    ODD_LOT     = "ODD_LOT"
    AFTER_HOURS = "AFTER_HOURS"
    SCHEDULED   = "SCHEDULED"

class Market(str, Enum):
    TWSE = "TWSE"
    TPEx = "TPEx"

class CorporateActionType(str, Enum):
    STOCK_SPLIT  = "STOCK_SPLIT"
    STOCK_MERGER = "STOCK_MERGER"
    RIGHTS_ISSUE = "RIGHTS_ISSUE"

# ── 基底事件 ────────────────────────────────────────────────────

class FinancialEvent(BaseModel):
    model_config = {"frozen": True}
    event_id:        str   = Field(..., description="唯一事件編號，格式 EVT-{8位序號}")
    event_date:      date  = Field(..., description="事件發生日期")
    sequence_in_day: int   = Field(0, description="同日事件排序權重，數字小者優先")
    event_type:      EventType
    cash_impact:     float = Field(..., description="對交割戶現金之淨影響（買進為負）")
    source_ref:      str   = Field(..., description="來源檔案與行號，如 'transactions.csv:row_42'")
    schema_version:  str   = Field("2.1", description="Event Schema 版本")

# ── 證券交易事件 ────────────────────────────────────────────────

class SecurityTradeEvent(FinancialEvent):
    """現股買賣（整張 / 零股 / 盤後 / 定期定額）"""
    event_type:      Literal[EventType.SECURITY_BUY, EventType.SECURITY_SELL]
    stock_id:        str
    stock_name:      str
    quantity:        int
    price:           float
    fee:             float = 0.0
    tax:             float = 0.0
    trade_category:  TradeCategory
    market:          Market
    settlement_date: date
    broker:          Optional[str] = None

# ── 現金股利事件 ─────────────────────────────────────────────

class DividendEvent(FinancialEvent):
    """現金股利入帳（付現日）"""
    event_type:          Literal[EventType.DIVIDEND_RECEIVE]
    stock_id:            str
    dividend_per_share:  float
    total_shares:        int
    withholding_tax:     float = 0.0
    ex_dividend_date:    Optional[date] = None  # 【v2.1 關鍵】供應收股利模組使用

# ── 股票股利事件 ─────────────────────────────────────────────

class StockDividendEvent(FinancialEvent):
    """
    股票股利配股事件。
    【v2.1 重要】本事件觸發 Portfolio Engine 呼叫 Dilution Operator，
    嚴禁在 FIFO 佇列尾端追加新 Lot。
    """
    event_type:          Literal[EventType.STOCK_DIVIDEND]
    stock_id:            str
    ratio:               float  # 例如每股配 0.2 股 → ratio = 1.2（原股數乘以此比率）

# ── 公司行動事件 ─────────────────────────────────────────────

class CorporateActionEvent(FinancialEvent):
    """
    股票分割、合併、減資等。
    【v2.1 ratio 定義】：
      - 2:1 股票分割（1 股變 2 股）→ ratio = 2.0
      - 1:2 股票合併（2 股變 1 股）→ ratio = 0.5
      - 無償配股每股配 0.2 股    → ratio = 1.2
    本事件觸發 Portfolio Engine 呼叫 Dilution Operator。
    """
    event_type:     Literal[EventType.CORPORATE_ACTION]
    stock_id:       str
    action_type:    CorporateActionType
    ratio:          float
    effective_date: date

# ── 現金存入/提出事件 ────────────────────────────────────────

class CashFlowEvent(FinancialEvent):
    event_type: Literal[EventType.CASH_DEPOSIT, EventType.CASH_WITHDRAW]
    memo:       Optional[str] = None

# ── 期初快照事件 ─────────────────────────────────────────────

class OpeningBalanceEvent(FinancialEvent):
    event_type:      Literal[EventType.OPENING_BALANCE]
    stock_id:        Optional[str]   = None
    quantity:        Optional[int]   = None
    average_cost:    Optional[float] = None
    cash_balance:    Optional[float] = None
    sequence_in_day: int = -1
```

### 5.2 Market Data Layer 模型

```python
class HistoricalPrice(BaseModel):
    stock_id:   str
    trade_date: date
    open:       float
    high:       float
    low:        float
    close:      float     # 未調整收盤價，唯一用於 NAV 計算
    adj_close:  float     # 調整後，僅供參考
    volume:     int
    provider:   str = "yahoo"
    fetched_at: date

# 【v2.1 新增】LOCF 對齊後的日線向量型別別名
# dict[date, dict[str, float]]
# 外層 key = 每一日曆日（含週末假日）
# 內層 key = stock_id，value = 當日對齊收盤價
AlignedDailyPrices = dict  # Type: dict[date, dict[str, float]]
```

### 5.3 Portfolio / Accounting / Projection Layer 模型

```python
# src/portfolio/models.py
class FifoLot(BaseModel):
    model_config = {"frozen": True}
    lot_id:        str
    stock_id:      str
    open_date:     date
    open_event_id: str   # Lineage：可追溯至原始 FinancialEvent
    quantity:      int
    unit_cost:     float  # (price*qty + fee) / qty

class PositionSnapshot(BaseModel):
    stock_id:       str
    as_of_date:     date
    total_quantity: int
    average_cost:   float
    market_price:   float
    market_value:   float
    unrealized_pl:  float
    open_lots:      list[FifoLot]

class PortfolioState(BaseModel):
    as_of_date:   date
    positions:    dict[str, PositionSnapshot]  # key = stock_id
    cash_balance: float

# src/accounting/models.py
class BalanceSheetSnapshot(BaseModel):
    as_of_date:          date
    cash_balance:        float
    dividend_receivable: float = Field(0.0, description="【v2.1 新增】應收股利科目（權責發生制）")
    total_stock_value:   float
    total_etf_value:     float
    net_worth:           float  # 淨資產 = 現金 + 應收股利 + 持倉市值

class IncomeStatementSnapshot(BaseModel):
    period_start:    date
    period_end:      date
    realized_pl:     float
    dividend_income: float
    fee_expense:     float
    tax_expense:     float
    net_profit:      float

class CashFlowSnapshot(BaseModel):
    """
    依用戶財務原則編製：
    - 直接法，含時間差調整區塊
    - 股息為營業活動
    - 股票買賣為投資活動（總額揭露）
    - 本金轉入/提出 + 利息支出為籌資活動
    """
    period_start: date
    period_end:   date
    # 一、營業活動
    operating_dividend_received: float
    operating_adjustments:       dict[str, float]
    net_operating_cash:          float
    # 二、投資活動（總額揭露）
    investing_security_purchase: float   # 購買股票本金流出（負值）
    investing_security_proceeds: float   # 出售股票收入（正值）
    investing_net_cash:          float
    # 三、籌資活動
    financing_capital_injection:  float
    financing_capital_withdrawal: float
    financing_net_cash:           float
    # 合計
    net_cash_change: float
```

### 5.4 Evidence & Output 模型（含邊界血緣壓縮，解決 E4）

```python
# src/evidence/models.py
from pydantic import BaseModel, Field
from typing import Optional, Any

class MetricLineage(BaseModel):
    """
    v2.1 邊界血緣壓縮技術：
    - 點對點指標（如特定平倉損益）：記錄於 source_event_ids
    - 全域時序型指標（如 NAV, XIRR, MDD）：嚴禁列出數千個事件 ID，
      改採 source_event_range 壓縮特徵碼，確保 Evidence JSON ≤ 50KB
    """
    derived_from:       list[str]           # 上游 metric_id 列表
    source_event_ids:   list[str] = Field(
        default_factory=list,
        description="精確關聯之點對點事件 ID 列表（僅用於非時序型指標）"
    )
    source_event_range: Optional[dict[str, Any]] = Field(
        None,
        description="時序型事件影響邊界壓縮，格式: {'start_id': 'EVT-001', 'end_id': 'EVT-999', 'count': 999}"
    )
    formula_id:         str
    formula_version:    str
    computed_at:        str  # ISO datetime

class EvidenceEntry(BaseModel):
    metric_id:       str
    metric_name:     str
    module:          str
    value:           float
    formatted_value: str
    status:          str    # Excellent | Good | Warning | Critical
    benchmark:       str
    priority:        str    # High | Medium | Low
    confidence:      str    # High | Medium | Low
    rule_id:         str
    rule_version:    str
    lineage:         MetricLineage

class FinancialEventSignal(BaseModel):
    event_code:        str
    title:             str
    description:       str
    severity:          str   # Positive | Warning | Info
    detected_at:       date
    source_metric_ids: list[str]

class HealthScore(BaseModel):
    total_score:   float
    grade:         str    # A | B | C | D | E
    breakdown:     dict[str, float]
    score_version: str

class OutputPayload(BaseModel):
    as_of_date:          date
    pipeline_version:    str
    balance_sheet:       BalanceSheetSnapshot
    income_statement:    IncomeStatementSnapshot
    cash_flow_statement: CashFlowSnapshot
    metrics_summary:     dict[str, Any]
    health_score:        HealthScore
    evidence_layer:      list[EvidenceEntry]
    detected_events:     list[FinancialEventSignal]
    telemetry_summary:   dict[str, Any]
```

### 5.5 Rule Schema（強型別，解決 P4）

```python
# src/evidence/rule_schema.py
from enum import Enum
from typing import Optional, Literal, Union
from pydantic import BaseModel, Field, field_validator

class StatusLevel(str, Enum):
    EXCELLENT = "Excellent"
    GOOD      = "Good"
    WARNING   = "Warning"
    CRITICAL  = "Critical"

class PriorityLevel(str, Enum):
    HIGH   = "High"
    MEDIUM = "Medium"
    LOW    = "Low"

class Direction(str, Enum):
    HIGHER_IS_BETTER              = "higher_is_better"
    LOWER_IS_BETTER               = "lower_is_better"
    HIGHER_IS_BETTER_UNTIL_EXCESS = "higher_is_better_until_excess"
    RANGE_IS_BEST                 = "range_is_best"

class ThresholdBand(BaseModel):
    max:      float
    status:   StatusLevel
    priority: PriorityLevel = PriorityLevel.LOW
    label:    Optional[str] = None

class MetricRule(BaseModel):
    rule_id:        str   = Field(..., pattern=r"^RULE_[A-Z0-9_]+$")
    metric_id:      str   = Field(..., pattern=r"^METRIC_[A-Z0-9_]+$")
    metric_name:    str
    module:         str
    direction:      Direction
    thresholds:     list[ThresholdBand]
    benchmark:      str
    version:        str   = Field(..., description="規則版本，如 '1.0', '2.0'")
    effective_date: str   = Field(..., description="生效日期 YYYY-MM-DD")
    expired_date:   Optional[str] = None
    deprecated_by:  Optional[str] = None

    @field_validator("thresholds")
    @classmethod
    def thresholds_must_be_ascending(cls, v):
        maxes = [t.max for t in v]
        if maxes != sorted(maxes):
            raise ValueError("thresholds 的 max 值必須遞增排列")
        return v

class RuleSet(BaseModel):
    schema_version: str
    rules:          list[MetricRule]
```

### 5.6 Error Domain 模型（解決 P7）

```python
# src/errors/domain_errors.py
from enum import Enum
from typing import Optional
from pydantic import BaseModel

class ErrorSeverity(str, Enum):
    FATAL       = "FATAL"
    RECOVERABLE = "RECOVERABLE"
    WARNING     = "WARNING"

class DomainError(BaseModel):
    code:        str
    severity:    ErrorSeverity
    title:       str
    detail:      str
    source_ref:  Optional[str] = None
    recoverable: bool

# ── 標準 Error Code 清單 ──────────────────────────────────────────
# ERR001  PriceMissing          RECOVERABLE  市價缺失，LOCF 延用最後已知價
# ERR002  TickerNotFound        RECOVERABLE  代碼查無對應 Provider 格式
# ERR003  DuplicateEvent        FATAL        發現重複事件 ID
# ERR004  NegativeQuantity      FATAL        持倉數量計算出現負值（FIFO 錯誤）
# ERR005  SettlementMismatch    WARNING      交割金額對帳誤差 > 1 元
# ERR006  BrokenFifoQueue       FATAL        FIFO 佇列狀態異常
# ERR007  CsvParseError         RECOVERABLE  CSV 欄位格式錯誤，跳過該行
# ERR008  ProviderUnavailable   RECOVERABLE  資料源暫時無法存取，切換備用
# ERR009  RuleVersionNotFound   FATAL        找不到指定版本的規則定義
# ERR010  MetricDagCycle        FATAL        Metric DAG 存在循環依賴
# ERR011  EvidenceSizeExceeded  WARNING      Evidence JSON 超過 50KB，需確認壓縮邏輯
# ERR012  DilutionCostDrift     WARNING      稀釋後總成本誤差 > 0.01 元，供稽核
```

---
