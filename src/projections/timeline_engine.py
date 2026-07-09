"""
Timeline Projector — 單次線性掃描引擎

根據 09-timeline-projection.md 10.2 節的規格實作。

核心演算法：單次線性掃描（Single-pass Sweep），複雜度 O(N + D)
- N = 事件總數
- D = 天數

嚴格禁止：
❌ 任何形式的雙重迴圈（如 for date in range: for event in events）
❌ 呼叫 replay_to() 或任何具有 O(N×D) 特徵的重放邏輯
"""

from datetime import date, timedelta
from typing import Dict, List, Optional, Tuple

import pandas as pd

from src.ledger.domain_models import (
    FinancialEvent,
    SecurityTradeEvent,
    DividendEvent,
    EventType,
)
from src.portfolio.engine import PortfolioEngine
from src.accounting.journal_entries import AccountingEngine
from src.market_data.locf_operator import apply_locf


def generate_state_timeline_matrix(
    start_date: date,
    end_date: date,
    events: List[FinancialEvent],
    market_data: Dict[str, pd.DataFrame],
    initial_cash: float = 0.0,
    *,
    date_col: str = "date",
    price_col: str = "adj_close",
) -> Dict[str, list]:
    """
    單次線性掃描，產生連續狀態時序矩陣。

    前置步驟：
    1. 對各股票的市場資料執行 LOCF 補值，確保無中斷

    單次線性掃描主迴圈（僅允許一層 for loop 遍歷日期）：
    2. 建立事件指針（按 (event_date, sequence_in_day, event_id) 排序）
    3. for today in date_range(start_date, end_date):
         a. 處理所有 event_date == today 的事件
         b. 若 today 為某股票的 ex_dividend_date → 觸發應收股利分錄
         c. 依據 aligned_prices[today] 結算今日持倉市值
         d. 建立今日 BalanceSheetSnapshot, IncomeStatementSnapshot, CashFlowSnapshot
         e. 灌入時序矩陣
    4. 一次性回傳三個報表的時序序列

    Parameters
    ----------
    start_date : date
        起始日期（含）。
    end_date : date
        結束日期（含）。
    events : List[FinancialEvent]
        已排序的 FinancialEvent 序列。
    market_data : Dict[str, pd.DataFrame]
        key 為 stock_id，value 為市場資料 DataFrame。
    initial_cash : float, default 0.0
        期初現金餘額。
    date_col : str, default "date"
        市場資料的日期欄位名稱。
    price_col : str, default "adj_close"
        市場資料的價格欄位名稱。

    Returns
    -------
    Dict[str, list]
        包含三個報表時序序列的字典：
        - balance_sheets: list[Dict]
        - income_statements: list[Dict]
        - cash_flows: list[Dict]
    """
    # ── 初始化引擎 ──────────────────────────────────────────────
    portfolio_engine = PortfolioEngine()
    accounting_engine = AccountingEngine()
    accounting_engine.cash_balance = initial_cash

    # ── 前置步驟 1：LOCF 補值 ──────────────────────────────────
    locf_cache: Dict[str, pd.DataFrame] = {}
    for stock_id, df in market_data.items():
        if df is not None and not df.empty:
            try:
                locf_cache[stock_id] = apply_locf(
                    df, date_col=date_col, price_col=price_col
                )
            except (ValueError, TypeError):
                pass

    # ── 前置步驟 2：事件按日期分組 ──────────────────────────────
    events_by_date: Dict[date, List[FinancialEvent]] = {}
    for evt in events:
        d = evt.event_date
        if d not in events_by_date:
            events_by_date[d] = []
        events_by_date[d].append(evt)

    # 對每組事件按 sequence_in_day 排序
    for d in events_by_date:
        events_by_date[d].sort(key=lambda e: (e.sequence_in_day, e.event_id))

    # ── 單次線性掃描主迴圈 ──────────────────────────────────────
    date_range = pd.date_range(start=start_date, end=end_date, freq="D")
    timeline_balance_sheet: List[Dict] = []
    timeline_income_statement: List[Dict] = []
    timeline_cash_flow: List[Dict] = []

    for d in date_range:
        current_date = d.date()

        # 3a. 處理當日事件
        if current_date in events_by_date:
            for evt in events_by_date[current_date]:
                # Portfolio Engine 處理事件
                portfolio_engine._process_single_event(evt)

                # Accounting Engine 產生對應分錄
                if isinstance(evt, SecurityTradeEvent):
                    is_buy = evt.event_type == EventType.SECURITY_BUY
                    accounting_engine.record_trade_settlement(
                        event_date=evt.event_date,
                        stock_id=evt.stock_id,
                        quantity=evt.quantity,
                        price=evt.price,
                        fee=evt.fee,
                        tax=evt.tax,
                        is_buy=is_buy,
                        source_event_id=evt.event_id,
                    )
                elif isinstance(evt, DividendEvent):
                    # 判斷階段
                    is_first_stage = (
                        evt.ex_dividend_date is None
                        or evt.event_date == evt.ex_dividend_date
                    )
                    if is_first_stage:
                        # 階段一：應收股利
                        total_shares = portfolio_engine.accountant.get_total_quantity(evt.stock_id)
                        if total_shares > 0:
                            accounting_engine.record_dividend_accrual(
                                event_date=evt.event_date,
                                stock_id=evt.stock_id,
                                total_shares=total_shares,
                                dividend_per_share=evt.dividend_per_share,
                                withholding_tax=evt.withholding_tax,
                                source_event_id=evt.event_id,
                            )
                    else:
                        # 階段二：股利銷帳
                        # 尋找對應的應收股利
                        for dr in portfolio_engine.dividend_receivables:
                            if (
                                dr.stock_id == evt.stock_id
                                and dr.ex_dividend_date == evt.ex_dividend_date
                                and not dr.is_settled
                            ):
                                settled = dr.settle()
                                portfolio_engine.dividend_receivables[
                                    portfolio_engine.dividend_receivables.index(dr)
                                ] = settled
                                accounting_engine.record_dividend_settlement(
                                    event_date=evt.event_date,
                                    stock_id=evt.stock_id,
                                    net_amount=dr.net_amount,
                                    source_event_id=evt.event_id,
                                )
                                break

        # 3c. 結算今日持倉市值
        total_stock_value = 0.0
        for stock_id in portfolio_engine.accountant.get_all_stock_ids():
            lots = portfolio_engine.accountant.get_lots(stock_id)
            total_qty = sum(lot.remaining_quantity for lot in lots)
            if total_qty <= 0:
                continue

            price = _get_price_from_cache(
                stock_id=stock_id,
                locf_cache=locf_cache,
                target_date=current_date,
                price_col=price_col,
            )
            if price is not None:
                total_stock_value += total_qty * price

        accounting_engine.total_stock_value = round(total_stock_value, 2)

        # 3d. 建立今日快照
        bs = accounting_engine.get_balance_sheet(current_date)
        inc = accounting_engine.get_income_statement(start_date, current_date)

        timeline_balance_sheet.append(bs)
        timeline_income_statement.append(inc)

        # CashFlowSnapshot（簡化版）
        cf = {
            "period_start": start_date,
            "period_end": current_date,
            "operating_dividend_received": accounting_engine.dividend_income,
            "operating_adjustments": {},
            "net_operating_cash": accounting_engine.dividend_income,
            "investing_security_purchase": 0.0,
            "investing_security_proceeds": 0.0,
            "investing_net_cash": 0.0,
            "financing_capital_injection": 0.0,
            "financing_capital_withdrawal": 0.0,
            "financing_net_cash": 0.0,
            "net_cash_change": accounting_engine.cash_balance - initial_cash,
        }
        timeline_cash_flow.append(cf)

    return {
        "balance_sheets": timeline_balance_sheet,
        "income_statements": timeline_income_statement,
        "cash_flows": timeline_cash_flow,
    }


def _get_price_from_cache(
    stock_id: str,
    locf_cache: Dict[str, pd.DataFrame],
    target_date: date,
    price_col: str,
) -> Optional[float]:
    """從 LOCF 快取中取得指定日期的價格。"""
    if stock_id not in locf_cache:
        return None

    filled = locf_cache[stock_id]
    mask = filled["date"] <= target_date
    if not mask.any():
        return None

    return float(filled[mask].iloc[-1][price_col])
