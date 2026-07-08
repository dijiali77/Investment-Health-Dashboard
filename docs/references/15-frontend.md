# 第十一層｜互動式報表前端（React + TypeScript）

> **依賴章節**：`00-overview.md`、`14-api-gateway.md`（REST 端點與 Response Schema）

---

## 第十六章　【v3.0 新增】第十一層｜互動式報表前端（React + TypeScript）

### 16.1 前端鐵則（不可違反）

1. **零計算原則**：前端禁止實作任何財務計算（XIRR、MDD、NAV、FIFO 等），所有數值直接渲染 API 回傳結果。
2. **型別契約**：`frontend/src/types/` 中的 TypeScript 介面必須與後端 Pydantic Schema 完全對應，後端欄位變更必須同步更新前端型別。
3. **狀態最小化**：React 元件狀態只保存 UI 互動狀態（篩選條件、選中行、展開節點），業務資料全從 API 取得。

### 16.2 技術棧規格

```json
{
  "dependencies": {
    "react": "^18.3.0",
    "react-router-dom": "^6.24.0",
    "recharts": "^2.12.0",
    "@tanstack/react-table": "^8.17.0",
    "@tanstack/react-query": "^5.0.0",
    "axios": "^1.7.0",
    "date-fns": "^3.6.0"
  },
  "devDependencies": {
    "typescript": "^5.5.0",
    "vite": "^5.3.0",
    "@vitejs/plugin-react": "^4.3.0",
    "vitest": "^1.6.0"
  }
}
```

### 16.3 五大頁面規格

#### 頁面一：總覽儀表板（`Overview.tsx`）

功能需求：頂部日期選擇器（切換後重新呼叫 `/api/v1/snapshot`）、健康評分圓形圖與七大模組雷達圖、財富三卡（淨資產/現金/持倉市值）、損益摘要、現金流量三大活動摘要、`detected_events` 里程碑/警示訊號列表。

互動規格：點擊任一數值卡 → 路由至對應詳細頁面。若 `data_quality.errors_count > 0`，頂部顯示 Banner 說明哪些資料降級處理（LOCF 延用、Provider 切換等）。

#### 頁面二：NAV 時序圖（`NAVChart.tsx`）

功能需求：Recharts `ComposedChart`，X 軸日期、Y 軸 NAV 折線 + 外部資金流柱狀圖。次要折線顯示 GrowthIndex。現金流事件在 X 軸顯示標記點（CASH_DEPOSIT / CASH_WITHDRAW）。

互動規格：
- 日期範圍選擇器調整後呼叫 `/api/v1/timeline?start=&end=`
- Recharts 內建 `<Brush>` 元件支援拖拉縮放
- Hover tooltip 顯示 `{ date, net_worth, daily_return, cashflow_event }`
- 點擊資金流標記 → 呼叫 `/api/v1/events/drilldown?event_id=` → 開啟 DrillDownPanel

#### 頁面三：Evidence 健康矩陣（`EvidenceMatrix.tsx`）

功能需求：TanStack Table 呈現 `evidence_layer`，欄位：指標名稱 / 數值 / 狀態 / 基準 / 優先度 / 模組 / 規則版本 / Confidence。狀態 Badge（Excellent=綠 / Good=藍 / Warning=橙 / Critical=紅）。

互動規格：
- 多欄篩選：模組下拉（七大模組）、狀態多選（Excellent/Good/Warning/Critical）、優先度篩選（High/Medium/Low）
- 欄位點擊排序（客戶端排序，data 已完整從 API 取得）
- 點擊任一行 → 右側展開 `LineageExplorer` Panel，顯示 `lineage.derived_from` DAG
- 點擊 `source_event_range` 的 start/end 邊界 → 呼叫 `/api/v1/events/drilldown` 展示邊界事件

#### 頁面四：持倉鑽取（`PositionDrilldown.tsx`）

功能需求：上半部持倉總覽表（股票代號 / 股數 / 平均成本 / 現價 / 市值 / 未實現損益 / 持倉比重），下半部選中股票的 FifoLot 明細（Lot ID / 開倉日期 / 股數 / 單位成本 / 對應損益）。

互動規格：
- 點擊持倉行 → 展開該股票所有 FifoLot 明細
- 點擊 FifoLot 的 `open_event_id` → 呼叫 `/api/v1/events/drilldown` → 顯示原始 CSV 行號（`source_ref`），完整追溯至原始交易
- 可依未實現損益、市值、持倉比重排序（客戶端排序）

#### 頁面五：血緣追溯器（`LineageExplorer.tsx`）

功能需求：輸入 `metric_id` → 呼叫 `/api/v1/lineage/metric?metric_id=&as_of_date=` → 視覺化呈現 `MetricLineage.derived_from` DAG（純 SVG 樹狀圖或 react-flow 套件）。

- 全域時序型指標（有 `source_event_range`）顯示：「基於 EVT-001 ~ EVT-347，共 347 筆事件計算（formula_version: 1.0）」
- 點對點型指標（有 `source_event_ids`）：每個 event_id 顯示為可點擊節點，點擊展開 DrillDownPanel

互動規格：DAG 節點可點擊，遞迴展開上游 lineage；支援縮放 / 拖拉；「匯出血緣報告」按鈕呼叫 `window.print()` 輸出目前 DAG 狀態。

### 16.4 TypeScript 型別定義（資料契約）

```typescript
// frontend/src/types/snapshot.ts
export interface BalanceSheet {
  as_of_date: string;
  cash_balance: number;
  dividend_receivable: number;
  total_stock_value: number;
  total_etf_value: number;
  net_worth: number;
}

export interface HealthScore {
  total_score: number;
  grade: 'A' | 'B' | 'C' | 'D' | 'E';
  breakdown: Record<string, number>;
  score_version: string;
}

export interface SnapshotResponse {
  as_of_date: string;
  pipeline_version: string;
  balance_sheet: BalanceSheet;
  income_statement: IncomeStatement;
  cash_flow_statement: CashFlowStatement;
  metrics_summary: Record<string, number>;
  health_score: HealthScore;
  data_quality: DataQuality;
}

// frontend/src/types/evidence.ts
export interface MetricLineage {
  derived_from: string[];
  source_event_ids: string[];
  source_event_range: {
    start_id: string;
    end_id: string;
    count: number;
  } | null;
  formula_id: string;
  formula_version: string;
  computed_at: string;
}

export interface EvidenceEntry {
  metric_id: string;
  metric_name: string;
  module: string;
  value: number;
  formatted_value: string;
  status: 'Excellent' | 'Good' | 'Warning' | 'Critical';
  benchmark: string;
  priority: 'High' | 'Medium' | 'Low';
  confidence: 'High' | 'Medium' | 'Low';
  rule_id: string;
  rule_version: string;
  lineage: MetricLineage;
}

// frontend/src/types/drilldown.ts
export interface DrillDownResponse {
  event_id: string;
  event_type: string;
  event_date: string;
  source_ref: string;              // "transactions.csv:row_42"
  cash_impact: number;
  stock_id: string | null;
  quantity: number | null;
  price: number | null;
  open_lots: FifoLotSummary[];
  affects_metrics: string[];
}
```

### 16.5 React Query 數據層

```typescript
// frontend/src/api/snapshot.ts
import { useQuery } from '@tanstack/react-query';

export const useSnapshot = (asOfDate: string) =>
  useQuery<SnapshotResponse>({
    queryKey: ['snapshot', asOfDate],
    queryFn: () =>
      client.get('/api/v1/snapshot', { params: { as_of_date: asOfDate } }).then(r => r.data),
    staleTime: 5 * 60 * 1000,   // 5 分鐘快取，避免重複觸發 Pipeline
    enabled: !!asOfDate,
  });

export const useDrillDown = (eventId: string | null) =>
  useQuery<DrillDownResponse>({
    queryKey: ['drilldown', eventId],
    queryFn: () =>
      client.get('/api/v1/events/drilldown', { params: { event_id: eventId } }).then(r => r.data),
    enabled: !!eventId,
  });
```

### 16.6 部署規格（Docker Compose）

```yaml
# docker/docker-compose.yml
version: '3.9'
services:
  api:
    build:
      context: ..
      dockerfile: docker/Dockerfile.api
    ports:
      - "8000:8000"
    volumes:
      - ../data:/app/data:ro
      - ../config:/app/config:ro
    environment:
      - REPOSITORY_BACKEND=duckdb
      - PRICE_PROVIDER=yahoo
    command: uvicorn src.api.main:app --host 0.0.0.0 --port 8000

  frontend:
    build:
      context: ../frontend
      dockerfile: ../docker/Dockerfile.frontend
    ports:
      - "80:80"
    depends_on:
      - api
```

---
