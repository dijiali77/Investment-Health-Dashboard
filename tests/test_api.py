"""
Application Service & API Layer 集成測試

測試範圍：
1. DashboardService 整合測試：
   - load_from_data 初始化管線
   - get_summary 回傳正確的摘要資訊
   - get_allocation 回傳正確的資產配置
   - get_nav_history 回傳正確的歷史淨值序列
   - 未初始化時拋出 RuntimeError
2. FastAPI 路由測試（使用 TestClient）：
   - GET /api/v1/dashboard/summary（200 OK + JSON 結構）
   - GET /api/v1/dashboard/allocation（200 OK + JSON 結構）
   - GET /api/v1/dashboard/nav-history（200 OK + JSON 結構）
   - GET /api/v1/dashboard/nav-history 缺少參數（422）
   - GET /api/v1/dashboard/summary 未初始化（503）
   - GET /health（200 OK）
"""

import pytest
from datetime import date, timedelta
from typing import Dict, List

import pandas as pd
from fastapi.testclient import TestClient

from src.api.dashboard_service import DashboardService
from src.api.routes import set_service
from src.api.main import app
from src.ledger.domain_models import (
    SecurityTradeEvent, EventType, TradeCategory, Market,
)


# =========================================================================
# 輔助函數
# =========================================================================


def _make_buy_event(
    event_id: str, stock_id: str, event_date: date,
    quantity: int, price: float, fee: float = 0.0,
) -> SecurityTradeEvent:
    return SecurityTradeEvent(
        event_id=event_id,
        event_date=event_date,
        sequence_in_day=1,
        event_type=EventType.SECURITY_BUY,
        cash_impact=-quantity * price - fee,
        source_ref=f"test:{event_id}",
        stock_id=stock_id,
        stock_name=f"Stock-{stock_id}",
        quantity=quantity,
        price=price,
        fee=fee,
        tax=0.0,
        trade_category=TradeCategory.BOARD_LOT,
        market=Market.TWSE,
        settlement_date=event_date,
    )


def _make_sell_event(
    event_id: str, stock_id: str, event_date: date,
    quantity: int, price: float,
) -> SecurityTradeEvent:
    return SecurityTradeEvent(
        event_id=event_id,
        event_date=event_date,
        sequence_in_day=2,
        event_type=EventType.SECURITY_SELL,
        cash_impact=quantity * price,
        source_ref=f"test:{event_id}",
        stock_id=stock_id,
        stock_name=f"Stock-{stock_id}",
        quantity=quantity,
        price=price,
        fee=0.0,
        tax=0.0,
        trade_category=TradeCategory.BOARD_LOT,
        market=Market.TWSE,
        settlement_date=event_date,
    )


def _make_market_data(
    stock_id: str,
    dates: list,
    prices: list,
    price_col: str = "adj_close",
) -> pd.DataFrame:
    return pd.DataFrame({
        "date": pd.to_datetime(dates),
        price_col: prices,
    })


def _create_initialized_service() -> DashboardService:
    """建立已初始化的 DashboardService 實例。"""
    service = DashboardService()
    events = [
        _make_buy_event("EVT-001", "2330", date(2024, 1, 2), 1000, 580.0),
        _make_buy_event("EVT-002", "2317", date(2024, 1, 3), 2000, 100.0),
    ]
    market_data = {
        "2330": _make_market_data(
            "2330",
            ["2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05"],
            [580.0, 590.0, 585.0, 600.0],
        ),
        "2317": _make_market_data(
            "2317",
            ["2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05"],
            [100.0, 105.0, 110.0, 115.0],
        ),
    }
    service.load_from_data(events, market_data, initial_cash=1_000_000.0)
    return service


# =========================================================================
# 1. DashboardService 整合測試
# =========================================================================


class TestDashboardService:
    """DashboardService 整合測試。"""

    def test_load_from_data_initializes_pipeline(self):
        """load_from_data 應正確初始化管線。"""
        service = _create_initialized_service()
        assert service._loaded is True
        assert len(service.events) == 2
        assert "2330" in service.engine.accountant.get_all_stock_ids()
        assert "2317" in service.engine.accountant.get_all_stock_ids()
        assert service.initial_cash == 1_000_000.0

    def test_get_summary_returns_correct_structure(self):
        """get_summary 應回傳正確的結構與數值。"""
        service = _create_initialized_service()
        result = service.get_summary()

        # 驗證鍵值存在（含 health_score）
        expected_keys = {
            "total_market_value", "cash_balance", "total_nav",
            "unrealized_pnl", "realized_pnl", "total_return_pct",
            "allocation", "health_score", "calculation_date",
        }
        assert expected_keys.issubset(result.keys())

        # 2330: 1000 * 600 = 600_000
        # 2317: 2000 * 115 = 230_000
        # 總市值 = 830_000
        assert result["total_market_value"] == 830_000.0

        # 現金 = 1_000_000 - 580_000 - 200_000 = 220_000
        assert result["cash_balance"] == 220_000.0

        # 總淨值 = 830_000 + 220_000 = 1_050_000
        assert result["total_nav"] == 1_050_000.0

        # 未實現損益 = 830_000 - (580_000 + 200_000) = 50_000
        assert result["unrealized_pnl"] == 50_000.0

        # 已實現損益 = 0（無賣出）
        assert result["realized_pnl"] == 0.0

        # 總報酬率 = (1_050_000 - 1_000_000) / 1_000_000 * 100 = 5.0%
        assert result["total_return_pct"] == 5.0

        # 資產配置應有 2 筆
        assert len(result["allocation"]) == 2

    def test_get_summary_with_target_date(self):
        """指定目標日期時，應使用 LOCF 補值計算。"""
        service = _create_initialized_service()
        result = service.get_summary(target_date=date(2024, 1, 4))

        # 1/4: 2330 價格 = 585, 2317 價格 = 110
        # 2330 市值 = 585_000, 2317 市值 = 220_000
        # 總市值 = 805_000
        assert result["total_market_value"] == 805_000.0

    def test_get_summary_with_realized_pnl(self):
        """有賣出事件時，已實現損益應正確。"""
        service = DashboardService()
        events = [
            _make_buy_event("EVT-001", "2330", date(2024, 1, 2), 1000, 580.0),
            _make_sell_event("EVT-002", "2330", date(2024, 1, 10), 500, 600.0),
        ]
        market_data = {
            "2330": _make_market_data(
                "2330",
                ["2024-01-02", "2024-01-10", "2024-01-15"],
                [580.0, 600.0, 610.0],
            ),
        }
        service.load_from_data(events, market_data, initial_cash=1_000_000.0)

        result = service.get_summary()

        # 已實現損益 = 500 * (600 - 580) = 10_000
        assert result["realized_pnl"] == 10_000.0

        # 剩餘 500 股，未實現損益 = 500 * (610 - 580) = 15_000
        assert result["unrealized_pnl"] == 15_000.0

    def test_get_allocation_returns_correct_structure(self):
        """get_allocation 應回傳正確的結構。"""
        service = _create_initialized_service()
        result = service.get_allocation()

        assert "allocations" in result
        assert "total_market_value" in result
        assert "cash_equivalent" in result
        assert "calculation_date" in result

        assert len(result["allocations"]) == 2
        # 2330 權重較大
        assert result["allocations"][0]["stock_id"] == "2330"

    def test_get_nav_history_returns_correct_structure(self):
        """get_nav_history 應回傳正確的結構。"""
        service = _create_initialized_service()
        result = service.get_nav_history(
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 5),
        )

        assert "nav_series" in result
        assert "start_date" in result
        assert "end_date" in result
        assert "total_return_pct" in result

        # 1/1 ~ 1/5 共 5 天
        assert len(result["nav_series"]) == 5

        # 驗證每日記錄的欄位
        first_day = result["nav_series"][0]
        expected_keys = {
            "date", "cash", "market_value", "total_nav",
            "daily_return_pct", "cumulative_return_pct",
        }
        assert expected_keys.issubset(first_day.keys())

        # 1/1: 只有現金
        assert first_day["cash"] == 1_000_000.0
        assert first_day["market_value"] == 0.0
        assert first_day["total_nav"] == 1_000_000.0

        # 最後一天應有個股市值欄位
        last_day = result["nav_series"][-1]
        assert "2330" in last_day
        assert "2317" in last_day

    def test_get_nav_history_total_return(self):
        """get_nav_history 的總報酬率應正確。"""
        service = _create_initialized_service()
        result = service.get_nav_history(
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 5),
        )

        # 1/5 總淨值 = 420_000 + 600_000 + 230_000 = 1_050_000
        # 期初淨值 = 1_000_000
        # 總報酬率 = 5.0%
        assert result["total_return_pct"] == pytest.approx(5.0, rel=0.01)

    def test_uninitialized_service_raises_error(self):
        """未初始化的 Service 應拋出 RuntimeError。"""
        service = DashboardService()
        with pytest.raises(RuntimeError, match="尚未初始化"):
            service.get_summary()

        with pytest.raises(RuntimeError, match="尚未初始化"):
            service.get_allocation()

        with pytest.raises(RuntimeError, match="尚未初始化"):
            service.get_nav_history(
                start_date=date(2024, 1, 1),
                end_date=date(2024, 1, 5),
            )

    def test_empty_portfolio_summary(self):
        """空投資組合的摘要應正確。"""
        service = DashboardService()
        service.load_from_data([], {}, initial_cash=1_000_000.0)

        result = service.get_summary()

        assert result["total_market_value"] == 0.0
        assert result["cash_balance"] == 1_000_000.0
        assert result["total_nav"] == 1_000_000.0
        assert result["unrealized_pnl"] == 0.0
        assert result["realized_pnl"] == 0.0
        assert result["total_return_pct"] == 0.0
        assert result["allocation"] == []

    def test_single_stock_summary(self):
        """單一股票的摘要應正確。"""
        service = DashboardService()
        events = [
            _make_buy_event("EVT-001", "2330", date(2024, 1, 2), 1000, 580.0),
        ]
        market_data = {
            "2330": _make_market_data(
                "2330",
                ["2024-01-02", "2024-01-15"],
                [580.0, 600.0],
            ),
        }
        service.load_from_data(events, market_data, initial_cash=1_000_000.0)

        result = service.get_summary()

        assert result["total_market_value"] == 600_000.0
        assert result["cash_balance"] == 420_000.0
        assert result["total_nav"] == 1_020_000.0
        assert result["unrealized_pnl"] == 20_000.0
        assert len(result["allocation"]) == 1
        assert result["allocation"][0]["weight_pct"] == 100.0


# =========================================================================
# 2. FastAPI 路由測試
# =========================================================================


class TestApiRoutes:
    """FastAPI 路由集成測試。"""

    @pytest.fixture(autouse=True)
    def setup_and_teardown(self):
        """每個測試前重置 Service 實例。"""
        # 建立已初始化的 Service
        service = _create_initialized_service()
        set_service(service)
        yield
        # 測試後清除
        set_service(None)

    @pytest.fixture
    def client(self):
        """建立 TestClient。"""
        return TestClient(app)

    def test_health_check(self, client):
        """健康檢查端點應回傳 200。"""
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"

    def test_summary_endpoint_returns_200(self, client):
        """GET /api/v1/dashboard/summary 應回傳 200。"""
        response = client.get("/api/v1/dashboard/summary")
        assert response.status_code == 200

        body = response.json()
        assert body["status"] == "ok"
        assert "data" in body

        data = body["data"]
        assert "total_market_value" in data
        assert "cash_balance" in data
        assert "total_nav" in data
        assert "unrealized_pnl" in data
        assert "realized_pnl" in data
        assert "total_return_pct" in data
        assert "allocation" in data
        assert "calculation_date" in data

        # 驗證數值
        assert data["total_market_value"] == 830_000.0
        assert data["cash_balance"] == 220_000.0
        assert data["total_nav"] == 1_050_000.0
        assert data["unrealized_pnl"] == 50_000.0
        assert data["realized_pnl"] == 0.0
        assert data["total_return_pct"] == 5.0

    def test_summary_with_target_date(self, client):
        """指定 target_date 參數時應回傳 200。"""
        response = client.get(
            "/api/v1/dashboard/summary",
            params={"target_date": "2024-01-04"},
        )
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["total_market_value"] == 805_000.0
        assert data["calculation_date"] == "2024-01-04"

    def test_summary_with_invalid_date(self, client):
        """無效的日期格式應回傳 400。"""
        response = client.get(
            "/api/v1/dashboard/summary",
            params={"target_date": "invalid-date"},
        )
        assert response.status_code == 400

    def test_allocation_endpoint_returns_200(self, client):
        """GET /api/v1/dashboard/allocation 應回傳 200。"""
        response = client.get("/api/v1/dashboard/allocation")
        assert response.status_code == 200

        body = response.json()
        assert body["status"] == "ok"
        assert "data" in body

        data = body["data"]
        assert "allocations" in data
        assert "total_market_value" in data
        assert "cash_equivalent" in data
        assert "calculation_date" in data

        # 驗證配置明細
        allocations = data["allocations"]
        assert len(allocations) == 2
        assert allocations[0]["stock_id"] == "2330"
        assert allocations[1]["stock_id"] == "2317"

        # 驗證權重總和約等於 100%
        total_weight = sum(a["weight_pct"] for a in allocations)
        assert total_weight == pytest.approx(100.0, rel=0.01)

    def test_allocation_with_target_date(self, client):
        """指定 target_date 參數時應回傳 200。"""
        response = client.get(
            "/api/v1/dashboard/allocation",
            params={"target_date": "2024-01-04"},
        )
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["calculation_date"] == "2024-01-04"

    def test_nav_history_endpoint_returns_200(self, client):
        """GET /api/v1/dashboard/nav-history 應回傳 200。"""
        response = client.get(
            "/api/v1/dashboard/nav-history",
            params={
                "start_date": "2024-01-01",
                "end_date": "2024-01-05",
            },
        )
        assert response.status_code == 200

        body = response.json()
        assert body["status"] == "ok"
        assert "data" in body

        data = body["data"]
        assert "nav_series" in data
        assert "start_date" in data
        assert "end_date" in data
        assert "total_return_pct" in data

        # 驗證時間序列長度
        assert len(data["nav_series"]) == 5

        # 驗證每日記錄結構
        first = data["nav_series"][0]
        assert "date" in first
        assert "cash" in first
        assert "market_value" in first
        assert "total_nav" in first
        assert "daily_return_pct" in first
        assert "cumulative_return_pct" in first

        # 驗證總報酬率
        assert data["total_return_pct"] == pytest.approx(5.0, rel=0.01)

    def test_nav_history_missing_params(self, client):
        """缺少必要參數時應回傳 422。"""
        # 缺少 start_date
        response = client.get(
            "/api/v1/dashboard/nav-history",
            params={"end_date": "2024-01-05"},
        )
        assert response.status_code == 422

        # 缺少 end_date
        response = client.get(
            "/api/v1/dashboard/nav-history",
            params={"start_date": "2024-01-01"},
        )
        assert response.status_code == 422

        # 兩個都缺少
        response = client.get("/api/v1/dashboard/nav-history")
        assert response.status_code == 422

    def test_nav_history_invalid_date_range(self, client):
        """start_date 晚於 end_date 時應回傳 400。"""
        response = client.get(
            "/api/v1/dashboard/nav-history",
            params={
                "start_date": "2024-01-10",
                "end_date": "2024-01-01",
            },
        )
        assert response.status_code == 400

    def test_nav_history_invalid_date_format(self, client):
        """無效的日期格式應回傳 400。"""
        response = client.get(
            "/api/v1/dashboard/nav-history",
            params={
                "start_date": "not-a-date",
                "end_date": "2024-01-05",
            },
        )
        assert response.status_code == 400

    def test_uninitialized_service_returns_503(self, client):
        """Service 未初始化時應回傳 503。"""
        # 清除 Service 實例
        set_service(None)

        response = client.get("/api/v1/dashboard/summary")
        assert response.status_code == 503

        response = client.get("/api/v1/dashboard/allocation")
        assert response.status_code == 503

        response = client.get(
            "/api/v1/dashboard/nav-history",
            params={
                "start_date": "2024-01-01",
                "end_date": "2024-01-05",
            },
        )
        assert response.status_code == 503

    def test_summary_json_structure(self, client):
        """驗證 summary 回傳的 JSON 結構完整性。"""
        response = client.get("/api/v1/dashboard/summary")
        data = response.json()["data"]

        # 驗證數值型別
        assert isinstance(data["total_market_value"], float)
        assert isinstance(data["cash_balance"], float)
        assert isinstance(data["total_nav"], float)
        assert isinstance(data["unrealized_pnl"], float)
        assert isinstance(data["realized_pnl"], float)
        assert isinstance(data["total_return_pct"], float)

        # 驗證 allocation 結構
        for alloc in data["allocation"]:
            assert "stock_id" in alloc
            assert "quantity" in alloc
            assert "price" in alloc
            assert "market_value" in alloc
            assert "weight_pct" in alloc

    def test_allocation_json_structure(self, client):
        """驗證 allocation 回傳的 JSON 結構完整性。"""
        response = client.get("/api/v1/dashboard/allocation")
        data = response.json()["data"]

        for alloc in data["allocations"]:
            assert "stock_id" in alloc
            assert "quantity" in alloc
            assert "price" in alloc
            assert "market_value" in alloc
            assert "weight_pct" in alloc

    def test_nav_history_json_structure(self, client):
        """驗證 nav-history 回傳的 JSON 結構完整性。"""
        response = client.get(
            "/api/v1/dashboard/nav-history",
            params={
                "start_date": "2024-01-01",
                "end_date": "2024-01-05",
            },
        )
        data = response.json()["data"]

        for record in data["nav_series"]:
            assert isinstance(record["date"], str)
            assert isinstance(record["cash"], float)
            assert isinstance(record["market_value"], float)
            assert isinstance(record["total_nav"], float)
            assert isinstance(record["daily_return_pct"], float)
            assert isinstance(record["cumulative_return_pct"], float)
