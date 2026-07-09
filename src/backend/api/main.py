"""
FastAPI 應用程式入口

提供儀表板 API 的 FastAPI 應用程式實例。
可透過 `uvicorn src.backend.api.main:app` 啟動。
"""

from fastapi import FastAPI

from .routes import router

app = FastAPI(
    title="Investment Health Dashboard API",
    description="投資組合健康儀表板後端 API",
    version="0.1.0",
)

app.include_router(router)


@app.get("/health")
def health_check():
    """健康檢查端點。"""
    return {"status": "ok", "service": "Investment Health Dashboard API"}
