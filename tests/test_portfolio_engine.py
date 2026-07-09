import pytest
import warnings
from datetime import date
from src.backend.portfolio_engine.fifo_engine import apply_dilution_operator, FifoLot, ERR012_WARNING

def test_apply_dilution_operator_standard_dividend():
    # 測試正常股票股利（配股），股數增加，單位成本降低
    # 假設發放 10% 股票股利，ratio = 1.1
    open_lots = [
        FifoLot(
            lot_id="L1", stock_id="2330.TW", open_date=date(2023, 1, 1),
            open_event_id="EVT1", quantity=1000, unit_cost=500.0
        ),
        FifoLot(
            lot_id="L2", stock_id="2330.TW", open_date=date(2023, 2, 1),
            open_event_id="EVT2", quantity=2000, unit_cost=600.0
        )
    ]

    updated_lots = apply_dilution_operator(open_lots, ratio=1.1)

    assert len(updated_lots) == 2

    # Lot 1: 1000 * 1.1 = 1100.
    # New Cost: (500 / 1.1) * (1000 / 1100) = 454.5454... * 0.909090... = 413.2231... (This isn't fully accurate, let's just test cost conservation)

    l1 = updated_lots[0]
    assert l1.quantity == 1100
    assert l1.open_event_id == "EVT1"

    l2 = updated_lots[1]
    assert l2.quantity == 2200
    assert l2.open_event_id == "EVT2"

    # 驗證總成本守恆
    old_cost = sum(lot.quantity * lot.unit_cost for lot in open_lots)
    new_cost = sum(lot.quantity * lot.unit_cost for lot in updated_lots)
    assert abs(old_cost - new_cost) <= 0.01

def test_apply_dilution_operator_fractional_shares():
    # 測試非整數情況（向下取整導致的成本分攤）
    open_lots = [
        FifoLot(
            lot_id="L1", stock_id="2330.TW", open_date=date(2023, 1, 1),
            open_event_id="EVT1", quantity=100, unit_cost=500.0
        )
    ]

    # 100 * 1.05 = 105
    # 假設 ratio 為 1.055，100 * 1.055 = 105.5 -> 105 股
    updated_lots = apply_dilution_operator(open_lots, ratio=1.055)

    assert len(updated_lots) == 1
    l1 = updated_lots[0]
    assert l1.quantity == 105

    # 驗證總成本守恆
    old_cost = sum(lot.quantity * lot.unit_cost for lot in open_lots)
    new_cost = sum(lot.quantity * lot.unit_cost for lot in updated_lots)
    assert abs(old_cost - new_cost) <= 0.01

def test_apply_dilution_operator_corporate_action_reverse_split():
    # 測試公司行動（減資/反向分割），股數變少，單位成本提高
    # 假設減資 50%，ratio = 0.5
    open_lots = [
        FifoLot(
            lot_id="L1", stock_id="2330.TW", open_date=date(2023, 1, 1),
            open_event_id="EVT1", quantity=1000, unit_cost=500.0
        )
    ]

    updated_lots = apply_dilution_operator(open_lots, ratio=0.5)

    assert len(updated_lots) == 1
    l1 = updated_lots[0]
    assert l1.quantity == 500

    # 驗證總成本守恆
    old_cost = sum(lot.quantity * lot.unit_cost for lot in open_lots)
    new_cost = sum(lot.quantity * lot.unit_cost for lot in updated_lots)
    assert abs(old_cost - new_cost) <= 0.01

def test_apply_dilution_operator_cost_conservation_warning():
    # 強行製造違反 cost conservation 的情況
    # 在我們的實作中，cost conservation 主要是由於 rounding 到整數股，然後透過算式自動補齊 unit_cost。
    # 正常使用那個算式是數學上保證守恆的。
    # 為了觸發警告，我們可以在測試環境中 override 函數或者假造極端浮點誤差。
    # 另一種方式是如果 quantity = 0 被過濾掉，但它原本有巨大成本，則可能觸發。
    open_lots = [
        FifoLot(
            lot_id="L1", stock_id="2330.TW", open_date=date(2023, 1, 1),
            open_event_id="EVT1", quantity=1, unit_cost=1000.0
        )
    ]

    # ratio = 0.1, 1 * 0.1 = 0.1 -> 0 股。Lot 會被捨棄，導致成本憑空消失 1000。
    with pytest.warns(ERR012_WARNING, match="Cost basis conservation violated"):
        updated_lots = apply_dilution_operator(open_lots, ratio=0.1)

    assert len(updated_lots) == 0

from src.backend.portfolio_engine.fifo_engine import FifoEngine

def test_fifo_engine_buy_and_sell():
    engine = FifoEngine()

    # 買入第一批 1000 股，單價 100
    lot1 = FifoLot(
        lot_id="L1", stock_id="2330.TW", open_date=date(2023, 1, 1),
        open_event_id="EVT1", quantity=1000, unit_cost=100.0
    )
    engine.process_buy(lot1)

    # 買入第二批 2000 股，單價 150
    lot2 = FifoLot(
        lot_id="L2", stock_id="2330.TW", open_date=date(2023, 2, 1),
        open_event_id="EVT2", quantity=2000, unit_cost=150.0
    )
    engine.process_buy(lot2)

    # 驗證庫存
    assert len(engine.portfolios["2330.TW"]) == 2

    # 賣出 1500 股，賣價 200
    # 預期：
    # 消耗 lot1 全部 (1000 股)，實現損益 = (200 - 100) * 1000 = 100000
    # 消耗 lot2 部分 (500 股)，實現損益 = (200 - 150) * 500 = 25000
    # 總實現損益本筆 = 125000
    pnl = engine.process_sell("2330.TW", sell_qty=1500, sell_price=200.0)

    assert pnl == 125000.0
    assert engine.realized_pnl == 125000.0

    # 驗證剩餘 Lot
    queue = engine.portfolios["2330.TW"]
    assert len(queue) == 1
    remaining_lot = queue[0]
    assert remaining_lot.lot_id == "L2"
    assert remaining_lot.quantity == 1500  # 2000 - 500
    assert remaining_lot.unit_cost == 150.0

def test_fifo_engine_insufficient_shares():
    engine = FifoEngine()
    lot1 = FifoLot(
        lot_id="L1", stock_id="2330.TW", open_date=date(2023, 1, 1),
        open_event_id="EVT1", quantity=1000, unit_cost=100.0
    )
    engine.process_buy(lot1)

    # 嘗試賣出 1500 股，超過庫存
    with pytest.raises(ValueError, match="Insufficient shares for 2330.TW. Short by 500 shares."):
        engine.process_sell("2330.TW", sell_qty=1500, sell_price=200.0)
