"""
CSV → Event 轉換器

依據 05-ledger.md 6.1 節的轉換規則，將 CSV 資料列轉換為對應的 FinancialEvent 子類別。

轉換規則摘要：
| 原始來源                          | 轉換為                              | cash_impact 計算                  |
|-----------------------------------|-------------------------------------|-----------------------------------|
| transactions.csv: BUY             | SecurityTradeEvent(SECURITY_BUY)    | -(qty×price + fee)               |
| transactions.csv: SELL            | SecurityTradeEvent(SECURITY_SELL)   | +(qty×price - fee - tax)         |
| bank_ledger.csv: DIVIDEND         | DividendEvent                       | +amount                          |
| bank_ledger.csv: CAPITAL_INJECTION| CashFlowEvent(CASH_DEPOSIT)         | +amount                          |
| bank_ledger.csv: CAPITAL_WITHDRAWAL| CashFlowEvent(CASH_WITHDRAW)       | -amount                          |
| bank_ledger.csv: TRADE_SETTLEMENT | 不建立事件（用於交叉驗證）           | 誤差 > 1 元 → ERR005 WARNING     |
| opening_snapshot.csv              | OpeningBalanceEvent                 | sequence_in_day = -1             |
"""

import csv
from datetime import date
from typing import List, Dict, Optional, Tuple, Any

from .domain_models import (
    FinancialEvent, SecurityTradeEvent, DividendEvent, StockDividendEvent,
    CorporateActionEvent, CashFlowEvent, OpeningBalanceEvent, EventType,
    TradeCategory, Market, CorporateActionType
)


class CsvToEventConverter:
    """將 CSV 資料列轉換為 FinancialEvent 物件的轉換器。"""

    def __init__(self):
        self.errors: List[Dict[str, Any]] = []  # 收集轉換過程中的錯誤

    def convert_transactions_row(self, row: Dict[str, str], row_num: int) -> Optional[SecurityTradeEvent]:
        """轉換 transactions.csv 的一筆資料列為 SecurityTradeEvent。"""
        source_ref = f"transactions.csv:row_{row_num}"
        trade_type = row.get("trade_type", "").strip().upper()

        if trade_type not in ("BUY", "SELL"):
            self.errors.append({
                "code": "ERR007",
                "detail": f"無效的 trade_type: {trade_type}",
                "source_ref": source_ref
            })
            return None

        try:
            quantity = int(row.get("quantity", 0))
            price = float(row.get("price", 0))
            fee = float(row.get("fee", 0))
            tax = float(row.get("tax", 0))

            if trade_type == "BUY":
                cash_impact = -(quantity * price + fee)
                event_type = EventType.SECURITY_BUY
            else:  # SELL
                cash_impact = +(quantity * price - fee - tax)
                event_type = EventType.SECURITY_SELL

            trade_category_str = row.get("trade_category", "").strip()
            trade_category = TradeCategory(trade_category_str) if trade_category_str else TradeCategory.BOARD_LOT

            market_str = row.get("market", "").strip()
            market = Market(market_str) if market_str else Market.TWSE

            return SecurityTradeEvent(
                event_id=f"EVT-{row_num:08d}",
                event_date=date.fromisoformat(row.get("trade_date", "")),
                sequence_in_day=2 if trade_type == "SELL" else 3,  # 依 6.2 節排序規則
                event_type=event_type,
                cash_impact=cash_impact,
                source_ref=source_ref,
                stock_id=row.get("stock_id", ""),
                stock_name=row.get("stock_name", ""),
                quantity=quantity,
                price=price,
                fee=fee,
                tax=tax,
                trade_category=trade_category,
                market=market,
                settlement_date=date.fromisoformat(row.get("settlement_date", "")),
                broker=row.get("broker")
            )
        except (ValueError, TypeError) as e:
            self.errors.append({
                "code": "ERR007",
                "detail": f"資料解析錯誤: {e}",
                "source_ref": source_ref
            })
            return None

    def convert_bank_ledger_row(self, row: Dict[str, str], row_num: int) -> Optional[FinancialEvent]:
        """轉換 bank_ledger.csv 的一筆資料列為對應事件。"""
        source_ref = f"bank_ledger.csv:row_{row_num}"
        category = row.get("category", "").strip().upper()

        try:
            amount = float(row.get("amount", 0))
            entry_date = date.fromisoformat(row.get("entry_date", ""))

            if category == "DIVIDEND":
                event = DividendEvent(
                    event_id=f"EVT-{row_num:08d}",
                    event_date=entry_date,
                    sequence_in_day=1,  # 依 6.2 節排序規則
                    event_type=EventType.DIVIDEND_RECEIVE,
                    cash_impact=+amount,
                    source_ref=source_ref,
                    stock_id=row.get("stock_id", ""),
                    dividend_per_share=float(row.get("dividend_per_share", 0)),
                    total_shares=0,  # 需從其他來源補齊
                    withholding_tax=0.0,
                    ex_dividend_date=date.fromisoformat(row["ex_dividend_date"]) if row.get("ex_dividend_date") else None
                )
                return event

            elif category == "CAPITAL_INJECTION":
                return CashFlowEvent(
                    event_id=f"EVT-{row_num:08d}",
                    event_date=entry_date,
                    sequence_in_day=0,  # 依 6.2 節排序規則
                    event_type=EventType.CASH_DEPOSIT,
                    cash_impact=+amount,
                    source_ref=source_ref,
                    memo=row.get("memo")
                )

            elif category == "CAPITAL_WITHDRAWAL":
                return CashFlowEvent(
                    event_id=f"EVT-{row_num:08d}",
                    event_date=entry_date,
                    sequence_in_day=4,  # 依 6.2 節排序規則
                    event_type=EventType.CASH_WITHDRAW,
                    cash_impact=-amount,
                    source_ref=source_ref,
                    memo=row.get("memo")
                )

            elif category == "TRADE_SETTLEMENT":
                # 不建立事件，用於交叉驗證
                # 誤差 > 1 元 → ERR005 WARNING
                self.errors.append({
                    "code": "ERR005",
                    "detail": f"交割金額待驗證: {amount}",
                    "source_ref": source_ref
                })
                return None

            else:
                self.errors.append({
                    "code": "ERR007",
                    "detail": f"無效的 category: {category}",
                    "source_ref": source_ref
                })
                return None

        except (ValueError, TypeError, KeyError) as e:
            self.errors.append({
                "code": "ERR007",
                "detail": f"資料解析錯誤: {e}",
                "source_ref": source_ref
            })
            return None

    def convert_opening_snapshot_row(self, row: Dict[str, str], row_num: int) -> OpeningBalanceEvent:
        """轉換 opening_snapshot.csv 的一筆資料列為 OpeningBalanceEvent。"""
        source_ref = f"opening_snapshot.csv:row_{row_num}"

        return OpeningBalanceEvent(
            event_id=f"EVT-{row_num:08d}",
            event_date=date.fromisoformat(row.get("trade_date", "1900-01-01")),
            sequence_in_day=-1,  # 依 6.2 節排序規則
            event_type=EventType.OPENING_BALANCE,
            cash_impact=0.0,
            source_ref=source_ref,
            stock_id=row.get("stock_id"),
            quantity=int(row["quantity"]) if row.get("quantity") else None,
            average_cost=float(row["average_cost"]) if row.get("average_cost") else None,
            cash_balance=float(row["cash_balance"]) if row.get("cash_balance") else None
        )

    def convert_file(self, filename: str, rows: List[Dict[str, str]]) -> List[FinancialEvent]:
        """
        轉換整個 CSV 檔案的資料列為事件列表。

        Args:
            filename: CSV 檔案名稱（用於判斷轉換規則）
            rows: CSV 資料列列表

        Returns:
            轉換後的事件列表
        """
        events: List[FinancialEvent] = []

        for i, row in enumerate(rows, start=1):
            event = None

            if filename == "transactions.csv":
                event = self.convert_transactions_row(row, i)
            elif filename == "bank_ledger.csv":
                event = self.convert_bank_ledger_row(row, i)
            elif filename == "opening_snapshot.csv":
                event = self.convert_opening_snapshot_row(row, i)

            if event is not None:
                events.append(event)

        return events

    def get_errors(self) -> List[Dict[str, Any]]:
        """取得轉換過程中收集的錯誤列表。"""
        return self.errors
