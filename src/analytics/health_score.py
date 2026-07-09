"""
HealthScoreCalculator（投資組合健康評分算子）

依據量化公式，綜合評估投資組合的健康度，產出 0~100 的綜合健康得分，
並附帶具體扣分原因的證據鏈（Evidence/Reasons）。

評分維度與權重：
1. 持股集中度風險（Concentration Risk）— 20 分
2. 現金留存比率（Cash Reserve Ratio）— 20 分
3. 資產週轉率（Turnover Rate）— 15 分
4. 投資績效（Performance）— 15 分
5. 風險管理（Risk Management）— 15 分
6. 交易紀律（Trading Discipline）— 10 分
7. 多元化程度（Diversification）— 5 分
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from math import sqrt
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class HealthScoreResult:
    """
    健康評分結果。

    Attributes
    ----------
    total_score : float
        綜合健康得分（0~100）。
    breakdown : Dict[str, float]
        各維度得分明細。
    deductions : List[Dict]
        扣分原因列表，每項包含：
        - dimension: 維度名稱
        - reason: 扣分原因描述
        - points_deducted: 扣分數
        - severity: 嚴重程度（low/medium/high）
    max_score : float
        滿分（100）。
    calculation_date : Optional[date]
        計算日期。
    """

    total_score: float = 0.0
    breakdown: Dict[str, float] = field(default_factory=dict)
    deductions: List[Dict[str, Any]] = field(default_factory=list)
    max_score: float = 100.0
    calculation_date: Optional[date] = None

    def to_dict(self) -> Dict[str, Any]:
        """轉換為字典格式（JSON 可序列化）。"""
        return {
            "total_score": round(self.total_score, 1),
            "max_score": self.max_score,
            "breakdown": {
                k: round(v, 1) for k, v in self.breakdown.items()
            },
            "deductions": self.deductions,
            "calculation_date": (
                self.calculation_date.isoformat()
                if self.calculation_date
                else None
            ),
        }


class HealthScoreCalculator:
    """
    投資組合健康評分計算器。

    評估七大維度，產出 0~100 的綜合健康得分。

    Usage
    -----
    >>> calculator = HealthScoreCalculator()
    >>> result = calculator.calculate(
    ...     positions={"2330": {"weight_pct": 60.0}},
    ...     cash_ratio=0.2,
    ...     turnover_rate=0.3,
    ...     total_return_pct=5.0,
    ...     num_stocks=3,
    ...     trade_count=5,
    ...     total_trades=10,
    ... )
    >>> result.total_score
    75.0
    """

    # 維度權重
    WEIGHT_CONCENTRATION = 20  # 持股集中度風險
    WEIGHT_CASH_RESERVE = 20  # 現金留存比率
    WEIGHT_TURNOVER = 15  # 資產週轉率
    WEIGHT_PERFORMANCE = 15  # 投資績效
    WEIGHT_RISK = 15  # 風險管理
    WEIGHT_DISCIPLINE = 10  # 交易紀律
    WEIGHT_DIVERSIFICATION = 5  # 多元化程度

    def __init__(self):
        pass

    def calculate(
        self,
        *,
        # 必要參數
        positions: Dict[str, Dict[str, Any]],
        cash_ratio: float,
        turnover_rate: float,
        total_return_pct: float,
        num_stocks: int,
        trade_count: int,
        total_trades: int,
        # 可選參數
        max_single_weight: float = 30.0,
        ideal_cash_ratio: float = 0.15,
        ideal_turnover: float = 0.5,
        target_diversification: int = 5,
        calculation_date: Optional[date] = None,
        # 進階風險參數
        volatility_pct: Optional[float] = None,
        max_drawdown_pct: Optional[float] = None,
        sharpe_ratio: Optional[float] = None,
    ) -> HealthScoreResult:
        """
        計算投資組合健康評分。

        Parameters
        ----------
        positions : Dict[str, Dict[str, Any]]
            各股票的持倉資訊，每項需包含 "weight_pct"。
        cash_ratio : float
            現金佔總資產比例（0~1）。
        turnover_rate : float
            資產週轉率（0~∞）。
        total_return_pct : float
            總報酬率（%）。
        num_stocks : int
            持有股票檔數。
        trade_count : int
            有交易的股票檔數。
        total_trades : int
            總交易次數。
        max_single_weight : float, default 30.0
            單一股票最大建議權重（%）。
        ideal_cash_ratio : float, default 0.15
            理想現金比例（0~1）。
        ideal_turnover : float, default 0.5
            理想年化週轉率。
        target_diversification : int, default 5
            目標分散檔數。
        calculation_date : Optional[date], default None
            計算日期。
        volatility_pct : Optional[float], default None
            年化波動度（%）。
        max_drawdown_pct : Optional[float], default None
            最大回撤（%）。
        sharpe_ratio : Optional[float], default None
            Sharpe Ratio。

        Returns
        -------
        HealthScoreResult
            健康評分結果。
        """
        deductions: List[Dict[str, Any]] = []
        breakdown: Dict[str, float] = {}

        # ── 1. 持股集中度風險（20 分）─────────────────────────────
        score_concentration, deductions_con = self._score_concentration(
            positions, max_single_weight
        )
        breakdown["concentration_risk"] = score_concentration
        deductions.extend(deductions_con)

        # ── 2. 現金留存比率（20 分）────────────────────────────────
        score_cash, deductions_cash = self._score_cash_reserve(
            cash_ratio, ideal_cash_ratio
        )
        breakdown["cash_reserve"] = score_cash
        deductions.extend(deductions_cash)

        # ── 3. 資產週轉率（15 分）──────────────────────────────────
        score_turnover, deductions_turn = self._score_turnover(
            turnover_rate, ideal_turnover
        )
        breakdown["turnover"] = score_turnover
        deductions.extend(deductions_turn)

        # ── 4. 投資績效（15 分）────────────────────────────────────
        score_perf, deductions_perf = self._score_performance(
            total_return_pct
        )
        breakdown["performance"] = score_perf
        deductions.extend(deductions_perf)

        # ── 5. 風險管理（15 分）────────────────────────────────────
        score_risk, deductions_risk = self._score_risk_management(
            volatility_pct=volatility_pct,
            max_drawdown_pct=max_drawdown_pct,
            sharpe_ratio=sharpe_ratio,
        )
        breakdown["risk_management"] = score_risk
        deductions.extend(deductions_risk)

        # ── 6. 交易紀律（10 分）────────────────────────────────────
        score_disc, deductions_disc = self._score_discipline(
            trade_count, total_trades, num_stocks
        )
        breakdown["trading_discipline"] = score_disc
        deductions.extend(deductions_disc)

        # ── 7. 多元化程度（5 分）───────────────────────────────────
        score_div, deductions_div = self._score_diversification(
            num_stocks, target_diversification
        )
        breakdown["diversification"] = score_div
        deductions.extend(deductions_div)

        # ── 總分計算 ──────────────────────────────────────────────
        total_score = sum(breakdown.values())
        total_score = max(0.0, min(100.0, total_score))

        return HealthScoreResult(
            total_score=total_score,
            breakdown=breakdown,
            deductions=deductions,
            max_score=100.0,
            calculation_date=calculation_date,
        )

    # ── 各維度評分邏輯 ────────────────────────────────────────────

    def _score_concentration(
        self,
        positions: Dict[str, Dict[str, Any]],
        max_single_weight: float,
    ) -> Tuple[float, List[Dict]]:
        """
        評估持股集中度風險（20 分）。

        規則：
        - 最大權重 <= max_single_weight：滿分 20
        - 每超過 10% 扣 5 分
        - 若單一持股 > 60%：額外扣 5 分（嚴重集中）
        """
        deductions: List[Dict] = []
        if not positions:
            return 0.0, [{
                "dimension": "concentration_risk",
                "reason": "無任何持股",
                "points_deducted": 20.0,
                "severity": "high",
            }]

        max_weight = max(
            p.get("weight_pct", 0.0) for p in positions.values()
        )
        score = self.WEIGHT_CONCENTRATION

        if max_weight > max_single_weight:
            excess = max_weight - max_single_weight
            penalty = (excess // 10) * 5
            score -= penalty
            deductions.append({
                "dimension": "concentration_risk",
                "reason": (
                    f"最大持股權重 {max_weight:.1f}% 超過建議上限 "
                    f"{max_single_weight:.0f}%，扣 {penalty:.0f} 分"
                ),
                "points_deducted": penalty,
                "severity": "high" if max_weight > 60 else "medium",
            })

        if max_weight > 60:
            extra_penalty = 5.0
            score -= extra_penalty
            deductions.append({
                "dimension": "concentration_risk",
                "reason": (
                    f"單一持股權重 {max_weight:.1f}% 超過 60%，"
                    f"屬嚴重集中，額外扣 {extra_penalty:.0f} 分"
                ),
                "points_deducted": extra_penalty,
                "severity": "high",
            })

        return max(0.0, score), deductions

    def _score_cash_reserve(
        self,
        cash_ratio: float,
        ideal_cash_ratio: float,
    ) -> Tuple[float, List[Dict]]:
        """
        評估現金留存比率（20 分）。

        規則：
        - cash_ratio 在 ideal_cash_ratio ±5% 內：滿分 20
        - 每偏離 5% 扣 3 分
        - 現金歸零（cash_ratio < 0.01）：扣 10 分
        - 現金過高（> 50%）：扣 5 分（資金運用效率低）
        """
        deductions: List[Dict] = []
        score = self.WEIGHT_CASH_RESERVE

        if cash_ratio < 0.01:
            score -= 10.0
            deductions.append({
                "dimension": "cash_reserve",
                "reason": "現金餘額趨近於零，無緩衝資金",
                "points_deducted": 10.0,
                "severity": "high",
            })
            return max(0.0, score), deductions

        deviation = abs(cash_ratio - ideal_cash_ratio)
        if deviation > 0.05:
            penalty = (deviation // 0.05) * 3
            score -= penalty
            deductions.append({
                "dimension": "cash_reserve",
                "reason": (
                    f"現金比例 {cash_ratio*100:.1f}% 偏離理想值 "
                    f"{ideal_cash_ratio*100:.0f}%，扣 {penalty:.0f} 分"
                ),
                "points_deducted": penalty,
                "severity": "medium",
            })

        if cash_ratio > 0.50:
            score -= 5.0
            deductions.append({
                "dimension": "cash_reserve",
                "reason": (
                    f"現金比例 {cash_ratio*100:.1f}% 過高，"
                    f"資金運用效率低，扣 5 分"
                ),
                "points_deducted": 5.0,
                "severity": "low",
            })

        return max(0.0, score), deductions

    def _score_turnover(
        self,
        turnover_rate: float,
        ideal_turnover: float,
    ) -> Tuple[float, List[Dict]]:
        """
        評估資產週轉率（15 分）。

        規則：
        - turnover <= ideal_turnover：滿分 15
        - 每超過 0.5 扣 3 分
        - 超過 3.0：扣 10 分（極度頻繁交易）
        """
        deductions: List[Dict] = []
        score = self.WEIGHT_TURNOVER

        if turnover_rate <= ideal_turnover:
            return score, deductions

        excess = turnover_rate - ideal_turnover
        penalty = (excess // 0.5) * 3
        score -= penalty

        deductions.append({
            "dimension": "turnover",
            "reason": (
                f"週轉率 {turnover_rate:.2f} 超過理想值 "
                f"{ideal_turnover:.1f}，扣 {penalty:.0f} 分"
            ),
            "points_deducted": penalty,
            "severity": "medium",
        })

        if turnover_rate > 3.0:
            extra_penalty = 10.0 - penalty
            if extra_penalty > 0:
                score -= extra_penalty
                deductions.append({
                    "dimension": "turnover",
                    "reason": (
                        f"週轉率 {turnover_rate:.2f} 超過 3.0，"
                        f"屬極度頻繁交易，額外扣 {extra_penalty:.0f} 分"
                    ),
                    "points_deducted": extra_penalty,
                    "severity": "high",
                })

        return max(0.0, score), deductions

    def _score_performance(
        self,
        total_return_pct: float,
    ) -> Tuple[float, List[Dict]]:
        """
        評估投資績效（15 分）。

        規則：
        - return >= 10%：滿分 15
        - return >= 5%：12 分
        - return >= 0%：10 分
        - return >= -5%：5 分
        - return < -5%：0 分
        - return < -10%：額外扣 5 分
        """
        deductions: List[Dict] = []

        if total_return_pct >= 10.0:
            return self.WEIGHT_PERFORMANCE, deductions
        elif total_return_pct >= 5.0:
            score = 12.0
            deductions.append({
                "dimension": "performance",
                "reason": f"報酬率 {total_return_pct:.1f}% 低於 10%",
                "points_deducted": 3.0,
                "severity": "low",
            })
        elif total_return_pct >= 0.0:
            score = 10.0
            deductions.append({
                "dimension": "performance",
                "reason": f"報酬率 {total_return_pct:.1f}% 僅持平",
                "points_deducted": 5.0,
                "severity": "medium",
            })
        elif total_return_pct >= -5.0:
            score = 5.0
            deductions.append({
                "dimension": "performance",
                "reason": f"報酬率 {total_return_pct:.1f}% 為負值",
                "points_deducted": 10.0,
                "severity": "high",
            })
        else:
            score = 0.0
            deductions.append({
                "dimension": "performance",
                "reason": f"報酬率 {total_return_pct:.1f}% 嚴重虧損",
                "points_deducted": 15.0,
                "severity": "high",
            })

        if total_return_pct < -10.0:
            score = max(0.0, score - 5.0)
            deductions.append({
                "dimension": "performance",
                "reason": f"報酬率 {total_return_pct:.1f}% 低於 -10%，額外扣 5 分",
                "points_deducted": 5.0,
                "severity": "high",
            })

        return max(0.0, score), deductions

    def _score_risk_management(
        self,
        volatility_pct: Optional[float] = None,
        max_drawdown_pct: Optional[float] = None,
        sharpe_ratio: Optional[float] = None,
    ) -> Tuple[float, List[Dict]]:
        """
        評估風險管理（15 分）。

        規則：
        - 波動度 < 15%：5 分；15-25%：3 分；> 25%：0 分
        - 最大回撤 < 10%：5 分；10-20%：3 分；> 20%：0 分
        - Sharpe > 1.0：5 分；0.5-1.0：3 分；< 0.5：1 分；負值：0 分
        """
        deductions: List[Dict] = []
        score = 0.0

        # 波動度評分（5 分）
        if volatility_pct is not None:
            if volatility_pct < 15.0:
                score += 5.0
            elif volatility_pct <= 25.0:
                score += 3.0
                deductions.append({
                    "dimension": "risk_management",
                    "reason": f"年化波動度 {volatility_pct:.1f}% 偏高",
                    "points_deducted": 2.0,
                    "severity": "medium",
                })
            else:
                deductions.append({
                    "dimension": "risk_management",
                    "reason": f"年化波動度 {volatility_pct:.1f}% 過高",
                    "points_deducted": 5.0,
                    "severity": "high",
                })
        else:
            score += 3.0  # 無資料時給中間分

        # 最大回撤評分（5 分）
        if max_drawdown_pct is not None:
            if max_drawdown_pct < 10.0:
                score += 5.0
            elif max_drawdown_pct <= 20.0:
                score += 3.0
                deductions.append({
                    "dimension": "risk_management",
                    "reason": f"最大回撤 {max_drawdown_pct:.1f}% 偏高",
                    "points_deducted": 2.0,
                    "severity": "medium",
                })
            else:
                deductions.append({
                    "dimension": "risk_management",
                    "reason": f"最大回撤 {max_drawdown_pct:.1f}% 過高",
                    "points_deducted": 5.0,
                    "severity": "high",
                })
        else:
            score += 3.0

        # Sharpe Ratio 評分（5 分）
        if sharpe_ratio is not None:
            if sharpe_ratio > 1.0:
                score += 5.0
            elif sharpe_ratio >= 0.5:
                score += 3.0
                deductions.append({
                    "dimension": "risk_management",
                    "reason": f"Sharpe Ratio {sharpe_ratio:.2f} 偏低",
                    "points_deducted": 2.0,
                    "severity": "medium",
                })
            elif sharpe_ratio >= 0.0:
                score += 1.0
                deductions.append({
                    "dimension": "risk_management",
                    "reason": f"Sharpe Ratio {sharpe_ratio:.2f} 過低",
                    "points_deducted": 4.0,
                    "severity": "high",
                })
            else:
                deductions.append({
                    "dimension": "risk_management",
                    "reason": f"Sharpe Ratio {sharpe_ratio:.2f} 為負值",
                    "points_deducted": 5.0,
                    "severity": "high",
                })
        else:
            score += 3.0

        return min(self.WEIGHT_RISK, score), deductions

    def _score_discipline(
        self,
        trade_count: int,
        total_trades: int,
        num_stocks: int,
    ) -> Tuple[float, List[Dict]]:
        """
        評估交易紀律（10 分）。

        規則：
        - 平均每檔交易次數 = total_trades / max(num_stocks, 1)
        - 平均次數 <= 3：滿分 10
        - 每多 1 次扣 2 分
        - 若 trade_count == 0（完全無交易）：扣 5 分（過度保守）
        """
        deductions: List[Dict] = []
        score = self.WEIGHT_DISCIPLINE

        if total_trades == 0:
            score -= 5.0
            deductions.append({
                "dimension": "trading_discipline",
                "reason": "完全無任何交易記錄，可能過度保守",
                "points_deducted": 5.0,
                "severity": "low",
            })
            return max(0.0, score), deductions

        avg_trades = total_trades / max(num_stocks, 1)
        if avg_trades > 3:
            excess = avg_trades - 3
            penalty = min(excess * 2, 10.0)
            score -= penalty
            deductions.append({
                "dimension": "trading_discipline",
                "reason": (
                    f"平均每檔交易 {avg_trades:.1f} 次，"
                    f"超過建議 3 次，扣 {penalty:.0f} 分"
                ),
                "points_deducted": penalty,
                "severity": "medium",
            })

        return max(0.0, score), deductions

    def _score_diversification(
        self,
        num_stocks: int,
        target: int,
    ) -> Tuple[float, List[Dict]]:
        """
        評估多元化程度（5 分）。

        規則：
        - num_stocks >= target：滿分 5
        - 每少 1 檔扣 1 分
        - 若只有 1 檔：額外扣 1 分
        """
        deductions: List[Dict] = []
        score = self.WEIGHT_DIVERSIFICATION

        if num_stocks >= target:
            return score, deductions

        shortage = target - num_stocks
        penalty = min(shortage * 1.0, 5.0)
        score -= penalty

        deductions.append({
            "dimension": "diversification",
            "reason": (
                f"僅持有 {num_stocks} 檔股票，"
                f"建議至少 {target} 檔，扣 {penalty:.0f} 分"
            ),
            "points_deducted": penalty,
            "severity": "medium",
        })

        if num_stocks == 1:
            score -= 1.0
            deductions.append({
                "dimension": "diversification",
                "reason": "僅持有單一股票，風險高度集中",
                "points_deducted": 1.0,
                "severity": "high",
            })

        return max(0.0, score), deductions
