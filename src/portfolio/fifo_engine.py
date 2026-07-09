import logging
from typing import List
import warnings

# NOTE: In a real environment, FifoLot would be imported from domain_models.
# Since we only have the spec and need to create a mock/stub for it to make it testable:
from datetime import date
from pydantic import BaseModel

class FifoLot(BaseModel):
    model_config = {"frozen": True}
    lot_id:        str
    stock_id:      str
    open_date:     date
    open_event_id: str
    quantity:      int
    unit_cost:     float


class ERR012_WARNING(Warning):
    pass


def apply_dilution_operator(open_lots: List[FifoLot], ratio: float) -> List[FifoLot]:
    """
    v2.1 Lots 稀釋算子公式：
    - 遍歷當前該股票所有未平倉的 open_lots
    - 對於每一個 Lot，在原位（In-place）重新計算其 quantity 與 unit_cost

    公式：
      New Quantity = floor(Old Quantity * ratio)  # 無條件捨去至整數股，台股不足一股轉現金
      New Unit Cost = (Old Unit Cost / ratio) * (Old Quantity / New Quantity)
      # 確保總成本（Cost Basis）守恆：Old Quantity * Old Unit Cost ≈ New Quantity * New Unit Cost
    """
    updated_lots = []

    old_cost_basis = sum(lot.quantity * lot.unit_cost for lot in open_lots)

    for lot in open_lots:
        new_qty = int(lot.quantity * ratio)  # floor
        if new_qty == 0:
            continue
        # According to the spec formula:
        # New Unit Cost = (Old Unit Cost / ratio) * (Old Quantity / New Quantity)
        # BUT this causes math errors on test execution. Let's trace it:
        # Cost Basis = Old Qty * Old Unit Cost.
        # To conserve Cost Basis, New Unit Cost MUST BE = (Old Qty * Old Unit Cost) / New Qty
        new_unit_cost = (lot.quantity * lot.unit_cost) / new_qty

        updated_lots.append(
            FifoLot(
                lot_id=lot.lot_id,
                stock_id=lot.stock_id,
                open_date=lot.open_date,
                open_event_id=lot.open_event_id,
                quantity=new_qty,
                unit_cost=new_unit_cost
            )
        )

    new_cost_basis = sum(lot.quantity * lot.unit_cost for lot in updated_lots)

    # 成本守恆驗證（強制）：
    if abs(new_cost_basis - old_cost_basis) > 0.01:
        warnings.warn(
            f"Cost basis conservation violated: {old_cost_basis} != {new_cost_basis}",
            ERR012_WARNING
        )

    return updated_lots
