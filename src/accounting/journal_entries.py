"""
Accounting Engine — 複式記帳分錄引擎

根據 08-accounting-engine.md 9.2 節的權責發生制股利分錄規則實作。

階段一（除權息日）：
  借（Debit）: Dividend Receivable（應收股利）
  貸（Credit）: Unrealized Dividend Income（未實現股利收入）

階段二（發放日）：
  借（Debit）: Cash Balance（現金資產）
  貸（Credit）: Dividend Receivable（應收股利）
"""

from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from typing import Dict, List, Optional


class AccountType(str, Enum):
    """會計科目類型。"""
    ASSET = "ASSET"           # 資產
    LIABILITY = "LIABILITY"   # 負債
    EQUITY = "EQUITY"         # 權益
    INCOME = "INCOME"         # 收入
    EXPENSE = "EXPENSE"       # 費用


@dataclass(frozen=True)
class JournalEntry:
    """
    複式記帳分錄。

    每筆分錄包含一組借貸科目，借貸總額必須平衡。

    Attributes
    ----------
    entry_id : str
        分錄編號，格式 JE-{序號}。
    entry_date : date
        分錄日期。
    description : str
        分錄說明。
    debits : Dict[str, float]
        借方科目與金額，key = 科目名稱，value = 金額。
    credits : Dict[str, float]
        貸方科目與金額，key = 科目名稱，value = 金額。
    source_event_id : Optional[str]
        來源事件 ID，用於血緣追溯。
    """
    entry_id: str
    entry_date: date
    description: str
    debits: Dict[str, float]
    credits: Dict[str, float]
    source_event_id: Optional[str] = None

    def __post_init__(self):
        """驗證借貸平衡。"""
        total_debits = round(sum(self.debits.values()), 2)
        total_credits = round(sum(self.credits.values()), 2)
        if abs(total_debits - total_credits) > 0.01:
            raise ValueError(
                f"借貸不平衡: 借方={total_debits}, 貸方={total_credits}, "
                f"entry_id={self.entry_id}"
            )


class AccountingEngine:
    """
    會計引擎 — 管理複式記帳分錄與財務報表。

    根據事件流產生對應的會計分錄，維護 BalanceSheetSnapshot、
    IncomeStatementSnapshot、CashFlowSnapshot 三表。

    Attributes
    ----------
    journal_entries : List[JournalEntry]
        所有會計分錄的歷史記錄。
    cash_balance : float
        當前現金餘額。
    dividend_receivable : float
        當前應收股利總額。
    total_stock_value : float
        當前持倉總市值。
    realized_pl : float
        累計已實現損益。
    dividend_income : float
        累計股利收入。
    fee_expense : float
        累計手續費支出。
    tax_expense : float
        累計稅金支出。
    """

    def __init__(self):
        self.journal_entries: List[JournalEntry] = []
        self.cash_balance: float = 0.0
        self.dividend_receivable: float = 0.0
        self.total_stock_value: float = 0.0
        self.realized_pl: float = 0.0
        self.dividend_income: float = 0.0
        self.fee_expense: float = 0.0
        self.tax_expense: float = 0.0
        self._entry_counter: int = 0

    def _next_entry_id(self) -> str:
        """產生下一個分錄編號。"""
        self._entry_counter += 1
        return f"JE-{self._entry_counter:06d}"

    def record_dividend_accrual(
        self,
        event_date: date,
        stock_id: str,
        total_shares: int,
        dividend_per_share: float,
        withholding_tax: float,
        source_event_id: str,
    ) -> JournalEntry:
        """
        階段一：除權息日 — 應收股利分錄。

        借（Debit）: Dividend Receivable（應收股利）
        貸（Credit）: Unrealized Dividend Income（未實現股利收入）

        Parameters
        ----------
        event_date : date
            除權息日。
        stock_id : str
            股票代號。
        total_shares : int
            持股股數。
        dividend_per_share : float
            每股股利。
        withholding_tax : float
            扣繳稅額。
        source_event_id : str
            來源事件 ID。

        Returns
        -------
        JournalEntry
            產生的會計分錄。
        """
        gross_amount = round(total_shares * dividend_per_share, 2)
        net_amount = round(gross_amount - withholding_tax, 2)

        entry = JournalEntry(
            entry_id=self._next_entry_id(),
            entry_date=event_date,
            description=f"應收股利 — {stock_id}（除權息日）",
            debits={"Dividend Receivable": net_amount},
            credits={"Unrealized Dividend Income": net_amount},
            source_event_id=source_event_id,
        )
        self.journal_entries.append(entry)
        self.dividend_receivable += net_amount
        return entry

    def record_dividend_settlement(
        self,
        event_date: date,
        stock_id: str,
        net_amount: float,
        source_event_id: str,
    ) -> JournalEntry:
        """
        階段二：發放日 — 股利銷帳分錄。

        借（Debit）: Cash Balance（現金資產）
        貸（Credit）: Dividend Receivable（應收股利）

        Parameters
        ----------
        event_date : date
            發放日。
        stock_id : str
            股票代號。
        net_amount : float
            淨入帳金額。
        source_event_id : str
            來源事件 ID。

        Returns
        -------
        JournalEntry
            產生的會計分錄。
        """
        entry = JournalEntry(
            entry_id=self._next_entry_id(),
            entry_date=event_date,
            description=f"股利入帳 — {stock_id}（發放日）",
            debits={"Cash Balance": net_amount},
            credits={"Dividend Receivable": net_amount},
            source_event_id=source_event_id,
        )
        self.journal_entries.append(entry)
        self.cash_balance += net_amount
        self.dividend_receivable -= net_amount
        self.dividend_income += net_amount
        return entry

    def record_trade_settlement(
        self,
        event_date: date,
        stock_id: str,
        quantity: int,
        price: float,
        fee: float,
        tax: float,
        is_buy: bool,
        source_event_id: str,
    ) -> JournalEntry:
        """
        記錄證券交易分錄。

        買入：
          借（Debit）: Stock Investments（股票投資）
          貸（Credit）: Cash Balance（現金資產）

        賣出：
          借（Debit）: Cash Balance（現金資產）
          貸（Credit）: Stock Investments（股票投資）
          借/貸（Debit/Credit）: Realized Gain/Loss（實現損益）

        Parameters
        ----------
        event_date : date
            交易日期。
        stock_id : str
            股票代號。
        quantity : int
            交易股數。
        price : float
            交易價格。
        fee : float
            手續費。
        tax : float
            交易稅。
        is_buy : bool
            是否為買入。
        source_event_id : str
            來源事件 ID。

        Returns
        -------
        JournalEntry
            產生的會計分錄。
        """
        if is_buy:
            total_cost = quantity * price + fee
            entry = JournalEntry(
                entry_id=self._next_entry_id(),
                entry_date=event_date,
                description=f"買入 {stock_id} {quantity}股 @ {price}",
                debits={"Stock Investments": round(total_cost, 2)},
                credits={"Cash Balance": round(total_cost, 2)},
                source_event_id=source_event_id,
            )
            self.cash_balance -= total_cost
            self.fee_expense += fee
        else:
            proceeds = quantity * price - fee - tax
            entry = JournalEntry(
                entry_id=self._next_entry_id(),
                entry_date=event_date,
                description=f"賣出 {stock_id} {quantity}股 @ {price}",
                debits={"Cash Balance": round(proceeds, 2)},
                credits={"Stock Investments": round(proceeds, 2)},
                source_event_id=source_event_id,
            )
            self.cash_balance += proceeds
            self.fee_expense += fee
            self.tax_expense += tax

        self.journal_entries.append(entry)
        return entry

    def get_balance_sheet(self, as_of_date: date) -> Dict:
        """
        取得資產負債表快照。

        Returns
        -------
        Dict
            BalanceSheetSnapshot 資料。
        """
        return {
            "as_of_date": as_of_date,
            "cash_balance": round(self.cash_balance, 2),
            "dividend_receivable": round(self.dividend_receivable, 2),
            "total_stock_value": round(self.total_stock_value, 2),
            "total_etf_value": 0.0,
            "net_worth": round(
                self.cash_balance + self.dividend_receivable + self.total_stock_value, 2
            ),
        }

    def get_income_statement(self, period_start: date, period_end: date) -> Dict:
        """
        取得損益表快照。

        Returns
        -------
        Dict
            IncomeStatementSnapshot 資料。
        """
        return {
            "period_start": period_start,
            "period_end": period_end,
            "realized_pl": round(self.realized_pl, 2),
            "dividend_income": round(self.dividend_income, 2),
            "fee_expense": round(self.fee_expense, 2),
            "tax_expense": round(self.tax_expense, 2),
            "net_profit": round(
                self.realized_pl + self.dividend_income - self.fee_expense - self.tax_expense, 2
            ),
        }

    def reset(self) -> None:
        """重置所有會計狀態。"""
        self.journal_entries.clear()
        self.cash_balance = 0.0
        self.dividend_receivable = 0.0
        self.total_stock_value = 0.0
        self.realized_pl = 0.0
        self.dividend_income = 0.0
        self.fee_expense = 0.0
        self.tax_expense = 0.0
        self._entry_counter = 0
