"""
DashboardService（儀表板整合服務）

整合型 Service，負責：
1. 載入 CSV 檔案（透過 CsvToEventConverter）
2. 初始化 Ledger 與事件排序
3. 驅動 PortfolioEngine 處理事件
4. 結合 MarketData（LOCF 補值）
5. 調用 Metrics 算子（UnrealizedPnl、AssetAllocation、NavHistory）
6. 將整個管線（Pipeline）串聯起來，提供統一的查詢介面。
"""

from datetime import date, datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd

from src.backend.ledger import (
    CsvToEventConverter,
    sort_events,
    FinancialEvent,
)
from src.backend.portfolio_engine import PortfolioEngine
from src.backend.metrics import (
    UnrealizedPnlCalculator,
    AssetAllocationCalculator,
    NavHistoryGenerator,
)
from src.backend.market_data.locf_operator import apply_locf


class DashboardService:
    """
    儀表板整合服務。

    封裝完整的投資組合分析管線：
    CSV 載入 → 事件轉換 → 事件排序 → PortfolioEngine 處理
    → Metrics 計算 → 格式化輸出

    Attributes
    ----------
    engine : PortfolioEngine
        已處理過事件的 PortfolioEngine 實例。
    events : List[FinancialEvent]
        已排序的事件列表。
    market_data : Dict[str, pd.DataFrame]
        各股票的市場資料（原始未補值）。
    initial_cash : float
        期初現金餘額。
    """

    def __init__(self):
        self.engine = PortfolioEngine()
        self.events: List[FinancialEvent] = []
        self.market_data: Dict[str, pd.DataFrame] = {}
        self.initial_cash: float = 0.0
        self._loaded: bool = False

    # ── 管線初始化 ────────────────────────────────────────────────

    def load_from_csv(
        self,
        transactions_path: Optional[str] = None,
        bank_ledger_path: Optional[str] = None,
        opening_snapshot_path: Optional[str] = None,
        market_data_dir: Optional[str] = None,
        *,
        date_col: str = "date",
        price_col: str = "adj_close",
    ) -> Dict:
        """
        從 CSV 檔案載入資料，初始化整個管線。

        Parameters
        ----------
        transactions_path : Optional[str]
            transactions.csv 檔案路徑。
        bank_ledger_path : Optional[str]
            bank_ledger.csv 檔案路徑。
        opening_snapshot_path : Optional[str]
            opening_snapshot.csv 檔案路徑。
        market_data_dir : Optional[str]
            市場資料 CSV 目錄路徑。目錄下應有以 stock_id.csv 命名的檔案。
        date_col : str, default "date"
            市場資料的日期欄位名稱。
        price_col : str, default "adj_close"
            市場資料的價格欄位名稱。

        Returns
        -------
        Dict
            載入摘要，包含：
            - event_count: 事件總數
            - stock_ids: 股票代號列表
            - errors: 轉換錯誤列表
            - initial_cash: 期初現金
        """
        converter = CsvToEventConverter()
        all_events: List[FinancialEvent] = []

        # 1. 載入並轉換 CSV 事件
        if transactions_path:
            rows = self._read_csv_rows(transactions_path)
            all_events.extend(converter.convert_file("transactions.csv", rows))

        if bank_ledger_path:
            rows = self._read_csv_rows(bank_ledger_path)
            all_events.extend(converter.convert_file("bank_ledger.csv", rows))

        if opening_snapshot_path:
            rows = self._read_csv_rows(opening_snapshot_path)
            all_events.extend(converter.convert_file("opening_snapshot.csv", rows))

        # 2. 從 OpeningBalanceEvent 提取期初現金
        for evt in all_events:
            if hasattr(evt, "cash_balance") and evt.cash_balance is not None:
                self.initial_cash = float(evt.cash_balance)

        # 3. 排序事件
        self.events = sort_events(all_events)

        # 4. 載入市場資料
        if market_data_dir:
            self._load_market_data(market_data_dir, date_col, price_col)

        # 5. 驅動 PortfolioEngine
        self.engine.reset()
        self.engine.process_events(self.events)

        self._loaded = True

        return {
            "event_count": len(self.events),
            "stock_ids": self.engine.accountant.get_all_stock_ids(),
            "errors": converter.get_errors(),
            "initial_cash": self.initial_cash,
        }

    def load_from_data(
        self,
        events: List[FinancialEvent],
        market_data: Dict[str, pd.DataFrame],
        initial_cash: float = 0.0,
    ) -> None:
        """
        直接從記憶體中的事件與市場資料初始化管線（用於測試）。

        Parameters
        ----------
        events : List[FinancialEvent]
            已排序或未排序的 FinancialEvent 列表。
        market_data : Dict[str, pd.DataFrame]
            key 為 stock_id，value 為市場資料 DataFrame。
        initial_cash : float, default 0.0
            期初現金餘額。
        """
        self.events = sort_events(events)
        self.market_data = market_data
        self.initial_cash = initial_cash

        self.engine.reset()
        self.engine.process_events(self.events)

        self._loaded = True

    # ── 查詢介面 ──────────────────────────────────────────────────

    def get_summary(
        self,
        target_date: Optional[date] = None,
        *,
        price_col: str = "adj_close",
    ) -> Dict:
        """
        取得儀表板摘要資訊。

        Parameters
        ----------
        target_date : Optional[date], default None
            目標計算日期。若為 None，使用最新價格。
        price_col : str, default "adj_close"
            市場資料的價格欄位名稱。

        Returns
        -------
        Dict
            包含以下鍵值：
            - total_market_value: 總資產市值
            - cash_balance: 現金餘額
            - total_nav: 總資產淨值（市值 + 現金）
            - unrealized_pnl: 未實現總損益
            - realized_pnl: 已實現總損益
            - total_return_pct: 總報酬率（%）
            - allocation: 最新資產配置比例
            - calculation_date: 計算日期
        """
        self._ensure_loaded()

        # 計算未實現損益
        pnl_calc = UnrealizedPnlCalculator(self.engine)
        pnl_result = pnl_calc.calculate(
            self.market_data,
            target_date=target_date,
            price_col=price_col,
        )

        # 計算已實現損益
        realized_summary = self.engine.get_realized_pnl_summary()
        total_realized_pnl = realized_summary["total_realized_pnl"]

        # 計算資產配置
        alloc_calc = AssetAllocationCalculator(self.engine)
        alloc_result = alloc_calc.calculate(
            self.market_data,
            target_date=target_date,
            price_col=price_col,
        )

        # 計算現金餘額
        cash_balance = self._calculate_cash_balance(target_date)

        # 總資產淨值
        total_nav = pnl_result["total_market_value"] + cash_balance

        # 總報酬率（基於期初淨值）
        initial_nav = self.initial_cash
        total_return_pct = (
            float(round(((total_nav - initial_nav) / initial_nav) * 100, 2))
            if initial_nav > 0
            else 0.0
        )

        return {
            "total_market_value": pnl_result["total_market_value"],
            "cash_balance": float(round(cash_balance, 2)),
            "total_nav": float(round(total_nav, 2)),
            "unrealized_pnl": pnl_result["total_unrealized_pnl"],
            "realized_pnl": float(round(total_realized_pnl, 2)),
            "total_return_pct": float(total_return_pct),
            "allocation": alloc_result["allocations"],
            "calculation_date": (
                target_date.isoformat() if target_date else None
            ),
        }

    def get_allocation(
        self,
        target_date: Optional[date] = None,
        *,
        price_col: str = "adj_close",
    ) -> Dict:
        """
        取得詳細的資產配置權重清單。

        Parameters
        ----------
        target_date : Optional[date], default None
            目標計算日期。
        price_col : str, default "adj_close"
            市場資料的價格欄位名稱。

        Returns
        -------
        Dict
            包含以下鍵值：
            - allocations: List[Dict]，各標的配置明細
            - total_market_value: 總市值
            - cash_equivalent: 現金等價物
            - calculation_date: 計算日期
        """
        self._ensure_loaded()

        alloc_calc = AssetAllocationCalculator(self.engine)
        return alloc_calc.calculate(
            self.market_data,
            target_date=target_date,
            price_col=price_col,
        )

    def get_nav_history(
        self,
        start_date: date,
        end_date: date,
        *,
        price_col: str = "adj_close",
    ) -> Dict:
        """
        取得歷史淨值與報酬率時間序列。

        Parameters
        ----------
        start_date : date
            起始日期（含）。
        end_date : date
            結束日期（含）。
        price_col : str, default "adj_close"
            市場資料的價格欄位名稱。

        Returns
        -------
        Dict
            包含以下鍵值：
            - nav_series: List[Dict]，每日淨值記錄
            - start_date: str
            - end_date: str
            - total_return_pct: 期間總報酬率（%）
        """
        self._ensure_loaded()

        nav_gen = NavHistoryGenerator(self.engine)
        df = nav_gen.generate(
            events=self.events,
            market_data=self.market_data,
            start_date=start_date,
            end_date=end_date,
            initial_cash=self.initial_cash,
            price_col=price_col,
        )

        # 轉換為 JSON 可序列化格式（處理 NaN 與 Inf）
        nav_series = []
        for idx, row in df.iterrows():
            record = {
                "date": idx.isoformat() if hasattr(idx, "isoformat") else str(idx),
                "cash": _safe_float(row["cash"]),
                "market_value": _safe_float(row["market_value"]),
                "total_nav": _safe_float(row["total_nav"]),
                "daily_return_pct": _safe_float(row["daily_return_pct"]),
                "cumulative_return_pct": _safe_float(row["cumulative_return_pct"]),
            }
            # 加入個股市值（如有）
            for col in df.columns:
                if col not in ("cash", "market_value", "total_nav",
                               "daily_return_pct", "cumulative_return_pct"):
                    record[col] = _safe_float(row[col])
            nav_series.append(record)

        total_return_pct = (
            _safe_float(df["cumulative_return_pct"].iloc[-1])
            if len(df) > 0
            else 0.0
        )

        return {
            "nav_series": nav_series,
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "total_return_pct": total_return_pct,
        }

    # ── 內部輔助方法 ──────────────────────────────────────────────

    def _ensure_loaded(self) -> None:
        """確保管線已初始化。"""
        if not self._loaded:
            raise RuntimeError(
                "DashboardService 尚未初始化。請先呼叫 load_from_csv() "
                "或 load_from_data()。"
            )

    def _read_csv_rows(self, path: str) -> List[Dict[str, str]]:
        """讀取 CSV 檔案，回傳字典列表。"""
        import csv
        rows: List[Dict[str, str]] = []
        with open(path, "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                rows.append({k.strip(): v.strip() for k, v in row.items()})
        return rows

    def _load_market_data(
        self,
        market_data_dir: str,
        date_col: str,
        price_col: str,
    ) -> None:
        """從目錄載入市場資料。"""
        data_path = Path(market_data_dir)
        if not data_path.exists() or not data_path.is_dir():
            return

        for csv_file in data_path.glob("*.csv"):
            stock_id = csv_file.stem
            try:
                df = pd.read_csv(csv_file)
                # 確保必要欄位存在
                if date_col in df.columns and price_col in df.columns:
                    df[date_col] = pd.to_datetime(df[date_col])
                    self.market_data[stock_id] = df
            except Exception:
                pass  # 跳過無法解析的檔案

    def _calculate_cash_balance(
        self,
        target_date: Optional[date] = None,
    ) -> float:
        """
        計算截至指定日期的現金餘額。

        從期初現金開始，累計所有事件的 cash_impact。
        若指定 target_date，只計算該日期之前的事件。
        """
        balance = self.initial_cash
        for evt in self.events:
            if target_date is not None and evt.event_date > target_date:
                break
            balance += evt.cash_impact
        return balance


def _safe_float(value) -> float:
    """
    安全地將值轉換為 float，處理 NaN 與 Inf。

    Parameters
    ----------
    value : any
        要轉換的值。

    Returns
    -------
    float
        轉換後的 float。若為 NaN 或 Inf，回傳 0.0。
    """
    import math
    try:
        v = float(value)
        if math.isnan(v) or math.isinf(v):
            return 0.0
        return v
    except (ValueError, TypeError):
        return 0.0
