# 第九層｜Repository Layer

> **依賴章節**：`00-overview.md`（架構原則）

---

## 第十四章　第九層｜Repository Layer（解決 P10）

### 14.1 Repository Interface

```python
# src/repository/interface.py
from abc import ABC, abstractmethod

class EventRepository(ABC):
    @abstractmethod
    def save_events(self, events: list[FinancialEvent]) -> None: ...
    @abstractmethod
    def load_all_events(self) -> list[FinancialEvent]: ...
    @abstractmethod
    def load_events_until(self, target_date: date) -> list[FinancialEvent]: ...

class PriceRepository(ABC):
    @abstractmethod
    def save_prices(self, prices: list[HistoricalPrice]) -> None: ...
    @abstractmethod
    def load_prices(self, stock_id: str, start: date, end: date) -> list[HistoricalPrice]: ...

class SnapshotRepository(ABC):
    """快取已計算的時序矩陣切片，避免全量重算"""
    @abstractmethod
    def save_timeline_matrix(self, matrix: dict, as_of_date: date) -> None: ...
    @abstractmethod
    def load_timeline_matrix(self, as_of_date: date) -> dict | None: ...
```

### 14.2 預設實作與切換

```python
# config/settings.py
REPOSITORY_BACKEND = "csv"  # "csv" | "sqlite" | "duckdb"

# main.py 工廠函式
def create_repositories(backend: str) -> tuple[EventRepository, PriceRepository]:
    if backend == "csv":
        return CsvEventRepository(), CsvPriceRepository()
    elif backend == "sqlite":
        return SqliteEventRepository(), SqlitePriceRepository()
    elif backend == "duckdb":
        return DuckDBEventRepository(), DuckDBPriceRepository()
```

---
