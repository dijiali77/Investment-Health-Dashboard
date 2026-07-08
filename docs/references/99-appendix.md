# 附錄

> **依賴章節**：`00-overview.md`；附錄內容（requirements.txt、遷移指南、ADR）橫跨全部章節

---

## 第二十章　附錄

### 18.1 `requirements.txt`（v2.1）

```
pandas>=2.0
pydantic>=2.0
scipy>=1.11
yfinance>=0.2.40
pyyaml>=6.0
pyarrow>=14.0
pytest>=7.4
opentelemetry-api>=1.20   # Telemetry Layer（開發期用 InMemoryTracer）
```

### 18.2 未來擴充規則（v2.1 架構下更簡單）

新增資產類別時，僅需：

1. 在 `EventType` Enum 新增對應事件類型，並建立對應子類別。
2. 在 `Portfolio Engine` 的 `fifo_engine.py` 新增處理邏輯（若有持倉，確認是否需要 Dilution Operator）。
3. 在 `market_data/providers/` 新增對應 Provider（若有新資料源），確保實作 `get_aligned_daily_prices`。
4. 在 `metric_dag.yaml` 新增相關指標節點。

**Accounting Engine / Timeline Projection / Evidence / Decision 四層完全不需改動**。

### 18.3 v2.0 → v2.1 遷移指南

| 遷移項目 | 動作 |
|---|---|
| `src/projections/replay_engine.py` | 重命名為 `timeline_engine.py`，核心邏輯替換為單次線性掃描 |
| `src/portfolio/fifo_engine.py`（股票股利處理）| 移除 `deque.append(FifoLot(new_shares, unit_cost=0))` 邏輯，替換為 `apply_dilution_operator` 呼叫 |
| `src/market_data/provider_interface.py` | 新增 `get_aligned_daily_prices` 抽象方法，所有 Provider 實作此方法並內建 LOCF |
| `src/accounting/journal.py` | 新增除息日應收股利分錄邏輯（`ex_dividend_date` 觸發第一段；`DIVIDEND_RECEIVE` 事件觸發第二段沖銷）|
| `src/accounting/models.py` | `BalanceSheetSnapshot` 新增 `dividend_receivable: float = 0.0` 欄位，`net_worth` 計算式含入此欄位 |
| `src/evidence/models.py` | `MetricLineage` 新增 `source_event_range: Optional[dict] = None` 欄位 |
| `src/evidence/builder.py` | 新增 `compress_lineage_horizon()` 函式，全域時序型指標呼叫此函式填入 `source_event_range` |
| `schema_version` 欄位 | 所有 FinancialEvent 子類別的 `schema_version` 預設值由 `"2.0"` 更新為 `"2.1"` |
| `pipeline_version` 欄位 | `OutputPayload.pipeline_version` 值由 `"2.0"` 更新為 `"2.1"` |

### 18.4 架構決策記錄（ADR，v2.1 新增）

| ADR | 決策 | 原因 | 取捨 |
|---|---|---|---|
| ADR-001 | 採用事件繼承體系而非 Union type | 未來擴充不需修改基底類別 | 序列化需 discriminated union |
| ADR-002 | Metric DAG 定義於 YAML 而非程式碼 | 非工程人員可閱讀與審核 | 需 cycle detection 防護 |
| ADR-003 | Repository 預設為 CSV | 零外部依賴，最低摩擦力上線 | 大資料量下效能較差 |
| ADR-004 | Telemetry 預設為 InMemory | 開發期不需基礎設施 | 生產需替換為 OTLP exporter |
| ADR-005 | 規則版本化採「有效日期區間」 | 與財務報告日期自然對齊 | 跨版本合併較複雜 |
| **ADR-006** | **Dilution Operator 取代 append 新 Lot** | 正確反映台股除權 FIFO 語義，成本基礎精確守恆 | 需額外成本守恆驗證（ERR012）|
| **ADR-007** | **權責發生制雙階段股利分錄** | 防止除息日 NAV 跳空失真，確保 MDD/波動度計算準確 | 需追蹤 ex_dividend_date 外部資料 |
| **ADR-008** | **LOCF 強制對齊至所有日曆日** | 時序指標計算不中斷，無假日空值污染 | 週末與假日使用非當日最新價 |
| **ADR-009** | **Timeline Projector 單次掃描取代多次重放** | $O(N+D)$ 效能，支援長期歷史資料 | 需管理掃描狀態機，程式碼複雜度略高 |
| **ADR-010** | **全域時序型指標採邊界血緣壓縮** | 確保 Evidence JSON ≤ 50KB，LLM Token 不溢位 | 精確 event_id 追溯需透過 start/end 邊界重建 |
