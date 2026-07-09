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
