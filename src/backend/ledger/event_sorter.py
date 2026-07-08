"""
事件排序器

依據 05-ledger.md 6.2 節的排序規則，對 FinancialEvent 列表進行排序。

排序規則：
sequence_in_day 權重（數字小者優先）：
  -1  OPENING_BALANCE
   0  CASH_DEPOSIT
   1  DIVIDEND_RECEIVE / STOCK_DIVIDEND / CORPORATE_ACTION
   2  SECURITY_SELL
   3  SECURITY_BUY
   4  CASH_WITHDRAW

排序鍵：(event_date, sequence_in_day, event_id) — 完全確定性（deterministic）。
"""

from datetime import date
from typing import List, Tuple

from .domain_models import FinancialEvent, EventType


# sequence_in_day 權重對照表（數字小者優先）
SEQUENCE_WEIGHTS = {
    EventType.OPENING_BALANCE:  -1,
    EventType.CASH_DEPOSIT:      0,
    EventType.DIVIDEND_RECEIVE:  1,
    EventType.STOCK_DIVIDEND:    1,
    EventType.CORPORATE_ACTION:  1,
    EventType.SECURITY_SELL:     2,
    EventType.SECURITY_BUY:      3,
    EventType.CASH_WITHDRAW:     4,
}


def get_sort_key(event: FinancialEvent) -> Tuple[date, int, str]:
    """
    取得事件的排序鍵。

    排序鍵：(event_date, sequence_in_day, event_id)
    - event_date: 事件發生日期（升序）
    - sequence_in_day: 同日事件排序權重（升序，數字小者優先）
    - event_id: 事件編號（升序，用於完全確定性）

    Args:
        event: 要取得排序鍵的 FinancialEvent 物件

    Returns:
        排序鍵元組 (event_date, sequence_in_day, event_id)
    """
    return (event.event_date, event.sequence_in_day, event.event_id)


def sort_events(events: List[FinancialEvent]) -> List[FinancialEvent]:
    """
    對 FinancialEvent 列表進行排序。

    排序規則：
    1. 先依 event_date 升序排列
    2. 同日事件依 sequence_in_day 升序排列
    3. 若 sequence_in_day 相同，依 event_id 升序排列

    此排序保證完全確定性（deterministic），
    相同的輸入事件列表必定產生相同的排序結果。

    Args:
        events: 要排序的 FinancialEvent 列表

    Returns:
        排序後的 FinancialEvent 列表（回傳新列表，不修改原始列表）
    """
    return sorted(events, key=get_sort_key)


def validate_sequence_weights(events: List[FinancialEvent]) -> List[str]:
    """
    驗證事件的 sequence_in_day 是否符合預設權重。

    檢查每個事件的 sequence_in_day 是否與 SEQUENCE_WEIGHTS 中定義的預設值一致。
    若不一致，回傳警告訊息列表。

    Args:
        events: 要驗證的 FinancialEvent 列表

    Returns:
        警告訊息列表（若無警告則為空列表）
    """
    warnings: List[str] = []
    for event in events:
        expected_weight = SEQUENCE_WEIGHTS.get(event.event_type)
        if expected_weight is not None and event.sequence_in_day != expected_weight:
            warnings.append(
                f"事件 {event.event_id} ({event.event_type.value}) 的 "
                f"sequence_in_day 為 {event.sequence_in_day}，"
                f"但預期為 {expected_weight}"
            )
    return warnings
