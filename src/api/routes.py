"""
FastAPI 路由（Endpoints）

提供儀表板 API 的三個主要端點：
- GET /api/v1/dashboard/summary
- GET /api/v1/dashboard/allocation
- GET /api/v1/dashboard/nav-history
"""

from datetime import date, datetime
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from src.api.dashboard_service import DashboardService

router = APIRouter(prefix="/api/v1/dashboard", tags=["dashboard"])

# 全域 Service 實例（由應用程式生命週期管理）
_service: Optional[DashboardService] = None


def get_service() -> DashboardService:
    """取得 DashboardService 實例。"""
    global _service
    if _service is None:
        _service = DashboardService()
    return _service


def set_service(service: DashboardService) -> None:
    """設定 DashboardService 實例（用於測試注入）。"""
    global _service
    _service = service


# ── Endpoints ────────────────────────────────────────────────────


@router.get("/summary")
def get_summary(
    target_date: Optional[str] = Query(
        None, description="目標計算日期（ISO 格式，如 2024-01-15）。若未指定，使用最新價格。"
    ),
):
    """
    回傳總資產市值、現金、未實現總損益、已實現總損益、最新資產配置比例。
    """
    service = get_service()
    try:
        parsed_date = _parse_date(target_date)
        result = service.get_summary(target_date=parsed_date)
        return {"status": "ok", "data": result}
    except HTTPException:
        raise
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"內部錯誤: {e}")


@router.get("/allocation")
def get_allocation(
    target_date: Optional[str] = Query(
        None, description="目標計算日期（ISO 格式）。若未指定，使用最新價格。"
    ),
):
    """
    回傳詳細的資產配置權重清單。
    """
    service = get_service()
    try:
        parsed_date = _parse_date(target_date)
        result = service.get_allocation(target_date=parsed_date)
        return {"status": "ok", "data": result}
    except HTTPException:
        raise
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"內部錯誤: {e}")


@router.get("/nav-history")
def get_nav_history(
    start_date: str = Query(..., description="起始日期（ISO 格式，如 2024-01-01）。"),
    end_date: str = Query(..., description="結束日期（ISO 格式，如 2024-01-31）。"),
):
    """
    回傳歷史淨值與報酬率時間序列（用於前端畫 K 線/折線圖）。
    """
    service = get_service()
    try:
        parsed_start = _parse_date(start_date)
        parsed_end = _parse_date(end_date)

        if parsed_start is None or parsed_end is None:
            raise HTTPException(
                status_code=400,
                detail="start_date 與 end_date 為必填參數，格式須為 ISO 日期（YYYY-MM-DD）。",
            )

        if parsed_start > parsed_end:
            raise HTTPException(
                status_code=400,
                detail="start_date 不得晚於 end_date。",
            )

        result = service.get_nav_history(
            start_date=parsed_start,
            end_date=parsed_end,
        )
        return {"status": "ok", "data": result}
    except HTTPException:
        raise
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"內部錯誤: {e}")


# ── 輔助函數 ────────────────────────────────────────────────────


def _parse_date(date_str: Optional[str]) -> Optional[date]:
    """解析 ISO 格式日期字串。"""
    if date_str is None:
        return None
    try:
        return datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"無效的日期格式: '{date_str}'。請使用 ISO 格式（YYYY-MM-DD）。",
        )
