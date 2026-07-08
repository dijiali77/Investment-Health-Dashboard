# 投資健康度儀表板（Investment Health Dashboard）
# 軟體設計規格書 v3.0（模組化拆分版）

**架構代號**：十層矩陣式時序事件流帳本架構 + 互動式報表層（Ten-Layer Matrix Time-Series Event Ledger Architecture with Interactive Dashboard）

**文件定位**：本文件為可直接交付 Cline（或任何 AI 工程師）逐步實作的工程規格書。所有檔案皆以「零偏差實作」為目標撰寫，禁止實作者自行發明資料結構、會計分錄或計算公式。

**拆分說明**：v3.0 規格書自本版起依「方案 B：按層拆分」原則，拆解為多個獨立檔案，對應 `src/` 套件結構與 Cline 的 Phase 實作順序。每個檔案頂部標明其依賴的其他檔案，完整索引見 `README.md`。

---

## v2.0 → v2.1 → v3.0 升級摘要

### v2.0 原始解決問題（相較 v1.0）

| 編號 | 問題類型 | v1.0 缺失 | v2.0 解法 |
|---|---|---|---|
| P1 | Critical | Projection Layer 為 God Object | 拆分為 Portfolio Engine + Accounting Engine |
| P2 | Critical | FinancialEvent 貧血模型 | 引入 Event 繼承體系（SecurityTradeEvent / DividendEvent 等）|
| P3 | Critical | Analytics 無 Dependency Graph | 建立 Metric Registry + DAG Resolver |
| P4 | High | YAML 淪為失控 DSL | 引入強型別 Rule Schema（Pydantic）|
| P5 | High | 無 Versioning 機制 | 所有規則、公式加入版本與有效期 |
| P6 | High | yfinance 單點故障 | 建立 PriceProvider 抽象介面，支援多資料源 |
| P7 | High | 無 Error Domain 分類 | 建立結構化 ErrorCode 體系（Recoverable / Fatal / Warning）|
| P8 | Medium | Evidence 缺 Trace/Lineage | EvidenceEntry 增加 derived_from / source_event_ids |
| P9 | Medium | 無 Observability | 引入 TelemetryLayer（OpenTelemetry 相容介面）|
| P10 | Medium | 無 Repository Layer | 加入 Repository Interface，解耦儲存層 |

### v2.1 新修訂（解決 v2.0 的財務工程與架構漏洞）

| 編號 | 漏洞類型 | v2.0 缺失 | v2.1 升級方案 |
|---|---|---|---|
| **E1** | Critical | $O(N \times D)$ 重複重放導致效能雪崩 | **重構為 Timeline Projector**：採單次線性掃描（Single-pass Sweep），一次性產出狀態時序矩陣，複雜度降至 $O(N + D)$ |
| **E2** | Critical | 除權息日至發放日跳空導致 NAV 虛擬暴跌 | **權責發生制應收模組**：除權息日自動計入「應收股利（Dividend Receivable）」，維持 NAV 穩定性與風險指標真實性 |
| **E3** | Critical | 股票股利於佇列尾端 append 導致 FIFO 損益扭曲 | **Lots 稀釋算子（Dilution Operator）**：取消追加 Lot 邏輯，遭遇除權或分割時，原位（In-place）依比例稀釋所有未平倉 Lots |
| **E4** | High | 全域時序指標導致 `source_event_ids` 空間爆炸吃空 Token | **邊界血緣壓縮技術（Lineage Aggregation）**：累積型指標改採「事件影響邊界區間（Event Horizon Bound）」，限制 Evidence JSON 體積 ≤ 50KB |
| **E5** | High | 週末與休市期間市價缺失導致時序指標計算中斷 | **標準化 LOCF 算子**：在 Market Data Layer 強制落實 `get_aligned_daily_prices` 向量對齊補值 |

### v3.0 新增（互動式報表層，相較 v2.1）

| 編號 | 新增項目 | 說明 |
|---|---|---|
| **F1** | 第十層：FastAPI Gateway | 新增 `src/api/` 套件，作為前端與九層 Pipeline 的橋接層，符合單向管線原則 |
| **F2** | REST API 端點設計 | 完整定義 `/api/v1/` 路由：`/snapshot`、`/timeline`、`/evidence`、`/events/drilldown`、`/health` 等 |
| **F3** | 前端目錄結構（React + TypeScript）| `frontend/` 套件：Vite + React 18 + Recharts + TanStack Table |
| **F4** | 五大互動式報表頁面規格 | 總覽儀表板、NAV 時序圖、Evidence 健康矩陣、持倉鑽取、血緣追溯器 |
| **F5** | 前端↔API 資料契約（TypeScript 型別）| 與後端 Pydantic Schema 一一對應的 TS 介面，禁止前端自行推算任何財務數值 |
| **F6** | 血緣鑽取 API（Lineage Drill-Down）| 點擊 EvidenceEntry → 展開 MetricLineage DAG → 定位原始 FifoLot → 連結至 CSV 行號 |
| **F7** | CORS / 認證 / 部署規格 | 開發期 localhost，生產期 Docker Compose（FastAPI + Nginx + DuckDB）|

**設計脈絡**：本規格整合三份前置構想——(1)「九層 + 規則引擎分離」的可維護性設計，(2)「事件溯源與時序帳本」的時間軸分析能力，(3)「多 Provider 市場資料抽象層」。v3.0 加入第四條主張：

> **Python 負責「確定性計算」，YAML（強型別 Schema 約束）負責「業務規則」，LLM 負責「因果推理」，React 負責「互動視覺化」——四者互不侵犯彼此的職責。前端禁止重新計算任何財務數值，一律從 API 取得。**

---

## 第一章　系統範疇與邊界（Scope & Boundaries）

### 1.1 支援範疇（In-Scope, v2.1）

| 類別 | 範圍 |
|---|---|
| 資產標的 | 台灣上市櫃股票、台股 ETF（架構已預留基金、債券、海外股票插槽）|
| 交易與公司行動類型 | 現股買進（整張/零股）、現股賣出、現金股利（**權責發生制應收與付現**）、股票股利（**Lots 稀釋變更**）、公司行動（股票分割/合併/減資）、本金轉入/轉出交割戶 |
| 成本會計 | 精確 FIFO（先進先出法）搭配 **Lots 稀釋算子** |
| 時間維度 | 自期初至截止日 $T$ 的**連續日線時序狀態矩陣**重建（單次線性掃描，$O(N+D)$）|
| 風險指標 | 基於連續日線 NAV 與 Dietz 報酬率計算之真實現金流調整 MDD、年化波動度、Sharpe/Sortino |
| 報酬指標 | XIRR（金額加權報酬率）、CAGR、已實現/未實現損益 |
| 架構能力 | 歷史報告重建（Versioned Rules）、可觀察性（Telemetry）、多儲存後端、**Evidence JSON ≤ 50KB** |

### 1.2 非本版範疇（Out-of-Scope, v2.1）

❌ 信用交易（融資、融券、借券）
❌ 衍生性金融商品（期權、選擇權、權證、期貨）
❌ 海外券商多幣別外匯轉換（架構已預留插槽，實作列入 v2.2+）
❌ 加密貨幣
❌ Time-Weighted Return（列入 v2.2+ 規劃）

### 1.3 關鍵資料前提

| 前提 | 說明 |
|---|---|
| 市場資料源 | v2.1 採 PriceProvider 介面，預設實作為 `YahooFinanceProvider`，可在 `config/settings.py` 切換為其他 Provider。**所有 Provider 必須實作 LOCF 算子**，確保時序向量無斷點 |
| 歷史股價 | 免費、免 Token，**僅作市值估算，股利資訊不採用調整後價格**（理由見 `06-market-data.md` § 股利重複計算陷阱）|
| 台股代碼格式 | 上市加 `.TW`、上櫃加 `.TWO` |
| 資料完整性假設 | 全部歷史 or 提供期初快照 |

---

## 第二章　架構總覽：十層矩陣式時序事件流帳本（v3.0）

### 2.1 整體資料流（v2.1）

```
[ Raw CSV：交易明細 / 銀行交割 / 期初快照 ]
                │
                ▼
        ┌───────────────────────────────────────┐
        │  1. Ledger Layer（事件帳本）             │
        │  FinancialEvent 繼承體系                 │
        └───────────────────┬───────────────────┘
                            │ FinancialEvent[] (不可變、依時間與權重嚴格排序)
                            ▼
        ┌───────────────────────────────────────┐
        │  2. Market Data Layer（多 Provider）     │
        │  PriceProvider Interface + LOCF 算子   │
        └───────────────────┬───────────────────┘
                            │ AlignedDailyPrices (連續日線向量，無休市斷點)
                            ▼
        ┌───────────────────────────────────────┐
        │  3. Portfolio Engine                  │
        │  FIFO 內建 Dilution Operator 稀釋算子  │
        └───────────────────┬───────────────────┘
                            │ PortfolioState
                            ▼
        ┌───────────────────────────────────────┐
        │  4. Accounting Engine                 │
        │  權責發生制分錄、應收股利與時間差調整     │
        └───────────────────┬───────────────────┘
                            │ FinancialStatements
                            ▼
        ┌───────────────────────────────────────┐
        │  5. Timeline Projection Layer（重構）  │
        │  generate_timeline(T) ─► 單次線性掃描   │
        └───────────────────┬───────────────────┘
                            │ State Time-Series Matrix (O(N+D) 高效矩陣)
                            ▼
        ┌───────────────────────────────────────┐
        │  6. Analytics Layer（Metric DAG）        │
        │  接收連續時序矩陣，一次性計算 XIRR/MDD/Sharpe │
        └───────────────────┬───────────────────┘
                            │ MetricsBundle
                            ▼
        ┌───────────────────────────────────────┐
        │  7. Evidence Layer                    │
        │  強型別 Rule Schema + 邊界血緣壓縮技術  │
        └───────────────────┬───────────────────┘
                            │ Compressed Evidence JSON (≤ 50KB)
                            ▼
        ┌───────────────────────────────────────┐
        │  8. Decision & Report Layer（LLM）      │
        │  依據有血緣基礎的證據鏈進行 C-Level 因果推理 │
        └───────────────────┬───────────────────┘
                            ▼
        ┌───────────────────────────────────────┐
        │  9. Repository Layer                   │
        │  CSV / SQLite / DuckDB / PostgreSQL    │
        └───────────────────┬───────────────────┘
                            │ Domain Objects（read-only）
                            ▼
        ┌───────────────────────────────────────┐
        │  10. API Gateway Layer【v3.0 新增】    │
        │  FastAPI + Pydantic Response Schema    │
        │  /api/v1/snapshot / timeline / evidence│
        └───────────────────┬───────────────────┘
                            │ JSON over HTTP（REST）
                            ▼
        ┌───────────────────────────────────────┐
        │  11. Interactive Dashboard【v3.0 新增】│
        │  React 18 + TypeScript + Recharts      │
        │  動態篩選 / 排序 / 鑽取 / 血緣視覺化   │
        └───────────────────────────────────────┘

═══ 橫切關注點（Crosscutting Concerns）════════════════════
  Telemetry Layer（OpenTelemetry）
  Error Domain（ErrorCode 體系）
  Versioning（Rule / Formula / Score 版本管理）
  CORS Policy / JWT Authentication（v3.0 新增）
```

### 2.2 九層職責界線（嚴格禁止事項）

| 層級 | 套件 | 執行者 | 輸入 | 輸出 | 嚴格禁止事項 |
|---|---|---|---|---|---|
| 1. Ledger | `src/ledger/` | Python | 原始 CSV | `FinancialEvent[]` | 禁止計算任何衍生指標；禁止感知上層概念 |
| 2. Market Data | `src/market_data/` | Python | 股票代號 + 日期區間 | `AlignedDailyPrices`（連續日線，無斷點）| 禁止涉入投資組合邏輯；禁止直接依賴任何特定 Provider；**禁止輸出有休市斷點的原始向量** |
| 3. Portfolio Engine | `src/portfolio/` | Python | Event[] + AlignedPrices | `PortfolioState` | 禁止建構三表；只負責持倉、FIFO、Lots；**股票股利與公司行動必須呼叫 Dilution Operator，禁止 append 新 Lot** |
| 4. Accounting Engine | `src/accounting/` | Python | `PortfolioState` + Event[] | `FinancialStatements` | 禁止感知持倉細節；**除權息日必須建立應收股利分錄，禁止等到現金入帳才認列** |
| 5. Timeline Projection | `src/projections/` | Python | Events + AlignedPrices | 連續狀態時序矩陣 | 禁止輸出評語；**禁止任何雙重迴圈重放（O(N×D) 模式）；嚴格採單次線性掃描** |
| 6. Analytics | `src/analytics/` | Python | 時序矩陣（BalanceSheetSnapshot[]）| `MetricsBundle` | 禁止輸出 Excellent/Warning 等狀態；透過 DAG 計算；**禁止重新呼叫重放引擎** |
| 7. Evidence | `src/evidence/` | Python | `MetricsBundle` + Versioned Rule | `EvidenceEntry[]`（壓縮血緣）| 禁止做因果推論；禁止寫死門檻值於程式碼；**全域時序型指標必須使用 source_event_range，禁止列舉所有事件 ID** |
| 8. Decision & Report | `prompts/` | **LLM** | `EvidenceEntry[]` | 結構化建議 + 摘要 | **禁止重新計算或臆測未出現在 Evidence 中的數值** |
| 9. Repository | `src/repository/` | Python | 任意 Domain Object | 持久化儲存 | 禁止包含業務邏輯；只做 I/O 抽象 |
| **10. API Gateway** | **`src/api/`** | **Python（FastAPI）** | **Repository Layer 輸出 + Pipeline 觸發** | **JSON REST Response** | **【v3.0 新增】禁止包含業務計算邏輯；只做序列化、路由、認證；禁止直接存取 src/analytics 或 src/evidence** |
| **11. Interactive Dashboard** | **`frontend/`** | **TypeScript（React）** | **API JSON** | **瀏覽器互動介面** | **【v3.0 新增】禁止在前端重新計算任何財務數值（XIRR、MDD 等）；所有數值必須從 API 取得；禁止直接存取後端資料庫** |

### 2.3 設計原則（不可違反）

1. **資料純度（Data Purity）**：Ledger Layer 只接受原始輸入，所有衍生資料必須從 Event 重建。
2. **不可變事件（Immutable Events）**：`FinancialEvent` 一旦建立不可修改，錯誤更正透過沖銷事件處理。
3. **確定性計算（Deterministic Computation）**：相同輸入恆產生相同輸出，禁止任何隨機或時間依賴邏輯。
4. **LLM 職責隔離（LLM Boundary）**：LLM 只負責因果推理與語言生成，禁止數值計算。
5. **單向資料管線（Unidirectional Pipeline）**：資料只能從 Layer N 流向 Layer N+1，嚴禁跨層回呼或循環依賴。
6. **事件語義豐富性（Rich Domain Event）**：`FinancialEvent` 子類別必須攜帶足以重建業務意圖的欄位，不依賴上層邏輯補充推斷。
7. **Metric DAG 優先（Metric as First-Class）**：任何指標只能由其依賴的上游指標衍生，禁止在多個模組中各自重算同一中間值。
8. **規則版本化（Versioned Rules）**：任何規則、公式、門檻值的變更必須新建版本記錄，舊版本保留。
9. **時序對齊強制（Aligned Time-Series）**：Market Data Layer 輸出的價格向量必須涵蓋每一日曆日（含週末與國定假日），以 LOCF 填補無交易日空值。
10. **Evidence 體積約束（Evidence Size Constraint）**：Evidence JSON 體積恆定 ≤ 50KB，全域時序型指標使用邊界壓縮技術。
11. **【v3.0】前端零計算原則（Frontend Zero-Computation）**：React 前端禁止實作任何財務計算邏輯，所有數值（包含格式化顯示）均從 API 端點取得，確保 Python Pipeline 為唯一計算來源。
12. **【v3.0】API 單一職責（API Single Responsibility）**：FastAPI Gateway 只負責「序列化 Domain Object 為 JSON」與「路由請求至正確 Pipeline 入口」，不得包含業務規則、財務計算或 Evidence 評估邏輯。

---
