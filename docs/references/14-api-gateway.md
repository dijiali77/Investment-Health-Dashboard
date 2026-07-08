# 第十層｜API Gateway（FastAPI）

> **依賴章節**：`00-overview.md`、`13-repository.md`、`06-market-data.md`（PriceProvider 介面）

---

## 第十五章　【v3.0 新增】第十層｜API Gateway（FastAPI）

### 15.1 設計動機

第十層的存在理由：第九層 Repository 輸出的是 Python Domain Object，React 前端需要的是 JSON over HTTP。API Gateway 是這兩者之間唯一的橋接層，職責邊界嚴格限定為「序列化 + 路由 + 認證」，禁止任何業務計算。

### 15.2 FastAPI 應用架構

```python
# src/api/main.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .routers import snapshot, timeline, evidence, drilldown, positions, health

app = FastAPI(title="Investment Health Dashboard API", version="3.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],  # 生產期替換為實際域名
    allow_methods=["GET"],                    # 唯讀 API，禁止 POST/PUT/DELETE
    allow_headers=["*"],
)

app.include_router(snapshot.router,  prefix="/api/v1")
app.include_router(timeline.router,  prefix="/api/v1")
app.include_router(evidence.router,  prefix="/api/v1")
app.include_router(drilldown.router, prefix="/api/v1")
app.include_router(positions.router, prefix="/api/v1")
app.include_router(health.router,    prefix="/api/v1")
```

### 15.3 REST API 端點完整規格

| 端點 | 方法 | 查詢參數 | 回傳型別 | 說明 |
|---|---|---|---|---|
| `/api/v1/snapshot` | GET | `as_of_date: date`（必填）| `SnapshotResponse` | 指定日期的三表快照 + 健康評分 |
| `/api/v1/timeline` | GET | `start: date`、`end: date` | `TimelineResponse` | 連續 BalanceSheetSnapshot[] 時序矩陣 |
| `/api/v1/evidence` | GET | `as_of_date: date` | `EvidenceResponse` | EvidenceEntry[] + FinancialEventSignal[] |
| `/api/v1/positions` | GET | `as_of_date: date` | `PositionsResponse` | 持倉明細 + FifoLot 列表 |
| `/api/v1/events/drilldown` | GET | `event_id: str` | `DrillDownResponse` | 單一事件的完整血緣鏈（含 source_ref）|
| `/api/v1/lineage/metric` | GET | `metric_id: str`、`as_of_date: date` | `MetricLineageResponse` | 指定指標的 DAG 血緣展開 |
| `/api/v1/health` | GET | — | `PipelineHealthResponse` | Pipeline 狀態 + 最近一次執行 telemetry |

### 15.4 API Response Schema

```python
# src/api/schemas/snapshot_response.py
from pydantic import BaseModel
from datetime import date
from typing import Any

class SnapshotResponse(BaseModel):
    as_of_date:          date
    pipeline_version:    str
    balance_sheet:       dict[str, Any]
    income_statement:    dict[str, Any]
    cash_flow_statement: dict[str, Any]
    metrics_summary:     dict[str, float]
    health_score:        dict[str, Any]
    data_quality:        dict[str, Any]   # { confidence, errors_count, cache_hit_rate }

# src/api/schemas/drilldown_response.py
class DrillDownResponse(BaseModel):
    event_id:        str
    event_type:      str
    event_date:      date
    source_ref:      str             # e.g. "transactions.csv:row_42"
    cash_impact:     float
    stock_id:        str | None
    quantity:        int | None
    price:           float | None
    open_lots:       list[dict]      # FifoLot 列表
    affects_metrics: list[str]       # 此事件影響的 metric_id 列表

# src/api/schemas/timeline_response.py
class TimelineResponse(BaseModel):
    start_date:      date
    end_date:        date
    daily_nav:       list[dict]      # [{ date, net_worth, cash, stock_value }]
    daily_returns:   list[dict]      # [{ date, daily_return }]
    cashflow_events: list[dict]      # [{ date, amount, type }]
```

### 15.5 依賴注入設計

```python
# src/api/dependencies.py
from functools import lru_cache
from fastapi import Depends

@lru_cache(maxsize=1)
def get_event_repository() -> EventRepository:
    return create_repositories(REPOSITORY_BACKEND)[0]

@lru_cache(maxsize=1)
def get_price_provider() -> PriceProvider:
    return create_price_provider(PRICE_PROVIDER)

async def get_pipeline_runner(
    repo: EventRepository = Depends(get_event_repository),
    provider: PriceProvider = Depends(get_price_provider),
) -> PipelineRunner:
    """
    PipelineRunner 封裝：API 路由層只呼叫 runner，
    不直接接觸 src/projections 或 src/analytics。
    """
    return PipelineRunner(repo=repo, provider=provider)
```

### 15.6 Error Code 新增（v3.0）

```
ERR013  ApiDateOutOfRange     WARNING   請求的 as_of_date 早於最早事件日期或晚於今日
ERR014  ApiTimelineTooBroad   WARNING   timeline 請求跨度 > 10 年，建議分段查詢
ERR015  ApiEventNotFound      FATAL     drilldown 的 event_id 查無對應事件
ERR016  ApiPipelineNotReady   FATAL     Repository 尚未初始化，Pipeline 無法執行
```

---
