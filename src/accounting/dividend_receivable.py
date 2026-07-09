"""
DividendReceivable（應收股利）資料模型

代表一筆在除權息日（Ex-Dividend Date）產生的應收股利，
在發放日（Payment Date）時銷帳並轉為現金。

雙階段會計邏輯：
1. 第一階段（除權息日）：根據持股 Lots 計算應收股利，建立 DividendReceivable
2. 第二階段（發放日）：將 DividendReceivable 銷帳，增加現金餘額
"""

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class DividendReceivable:
    """
    應收股利記錄。

    在除權息日（ex_dividend_date）產生，記錄該檔股票
    在該日期的應收股利總額。在發放日（payment_date）銷帳。

    Attributes
    ----------
    receivable_id : str
        唯一應收股利編號，格式 DR-{event_id}。
    stock_id : str
        股票代號。
    ex_dividend_date : date
        除權息日（權責發生日）。
    payment_date : date
        股利發放日（現金入帳日）。
    total_shares : int
        除權息日當天的持股股數。
    dividend_per_share : float
        每股現金股利。
    gross_amount : float
        應收股利總額（total_shares × dividend_per_share）。
    withholding_tax : float
        扣繳稅額。
    net_amount : float
        淨應收金額（gross_amount - withholding_tax）。
    is_settled : bool
        是否已銷帳（發放日已過）。
    """
    receivable_id: str
    stock_id: str
    ex_dividend_date: date
    payment_date: date
    total_shares: int
    dividend_per_share: float
    gross_amount: float
    withholding_tax: float = 0.0
    net_amount: float = 0.0
    is_settled: bool = False

    def __post_init__(self):
        """自動計算 net_amount 若未提供。"""
        if self.net_amount == 0.0 and self.gross_amount != 0.0:
            object.__setattr__(
                self, "net_amount",
                round(self.gross_amount - self.withholding_tax, 2),
            )

    def settle(self) -> "DividendReceivable":
        """
        銷帳此應收股利，回傳已銷帳的新實例。

        Returns
        -------
        DividendReceivable
            已銷帳的 DividendReceivable（is_settled=True）。
        """
        return DividendReceivable(
            receivable_id=self.receivable_id,
            stock_id=self.stock_id,
            ex_dividend_date=self.ex_dividend_date,
            payment_date=self.payment_date,
            total_shares=self.total_shares,
            dividend_per_share=self.dividend_per_share,
            gross_amount=self.gross_amount,
            withholding_tax=self.withholding_tax,
            net_amount=self.net_amount,
            is_settled=True,
        )
