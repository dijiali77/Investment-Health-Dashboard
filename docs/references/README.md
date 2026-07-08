# 投資健康度儀表板 — 軟體設計規格書 v3.0（模組化拆分版）

本資料夾為原始單檔規格書（20章、約2000行）依「方案 B：按層拆分」原則重組後的結果，對應 `src/` 套件結構與 Cline 的 Phase 實作順序。每個檔案頂部標明其依賴的其他檔案，建議依編號順序閱讀與實作。

## 為什麼拆分

- **AI 閱讀效率**：Cline 被指派實作某一層時，只需載入對應檔案 + 其宣告的依賴檔案，避免整份 2000+ 行文件造成的 token 浪費與跨層雜訊干擾。
- **VS Code 體驗**：大綱（Outline）視圖恢復清晰、Git diff 精準到單一關注點、可平行編輯不同層級降低 merge conflict。
- **橫切關注點集中**：`90-crosscutting.md` 獨立收斂 Versioning / Telemetry / Error Domain 等全域約束，避免分散重複。

## 檔案索引

| 檔案 | 內容 | 對應原章節 | 對應 Phase |
|---|---|---|---|
| [`00-overview.md`](./00-overview.md) | 架構總覽、十層管線圖、設計原則、v2.0→v2.1→v3.0 升級摘要、系統範疇與邊界 | 第一、二章 | — |
| [`03-input-data-model.md`](./03-input-data-model.md) | 輸入 CSV Schema（transactions / bank_ledger / opening_snapshot）| 第四章 | — |
| [`04-domain-models.md`](./04-domain-models.md) | 全部 Pydantic v2 領域模型（Event 繼承體系、Market Data、Portfolio/Accounting、Evidence、Rule Schema、Error Domain）| 第五章 | — |
| [`05-ledger.md`](./05-ledger.md) | 第一層｜Ledger Layer：CSV→Event 轉換、排序規則、不可變性原則 | 第六章 | Phase 1 |
| [`06-market-data.md`](./06-market-data.md) | 第二層｜Market Data Layer：PriceProvider 介面、LOCF 算子、股利重複計算陷阱 | 第七章 | Phase 2 |
| [`07-portfolio-engine.md`](./07-portfolio-engine.md) | 第三層｜Portfolio Engine：FIFO 撮合、Lots 稀釋算子 | 第八章 | Phase 3 |
| [`08-accounting-engine.md`](./08-accounting-engine.md) | 第四層｜Accounting Engine：權責發生制應收股利雙階段分錄 | 第九章 | Phase 4 |
| [`09-timeline-projection.md`](./09-timeline-projection.md) | 第五層｜Timeline Projection Layer：單次線性掃描 $O(N+D)$ | 第十章 | Phase 5 |
| [`10-analytics-dag.md`](./10-analytics-dag.md) | 第六層｜Analytics Layer：Metric DAG 引擎、關鍵公式、健康評分 | 第十一章 | Phase 6 |
| [`11-evidence-layer.md`](./11-evidence-layer.md) | 第七層｜Evidence Layer：邊界血緣壓縮、規則版本選擇邏輯 | 第十二章 | Phase 7 |
| [`12-decision-llm.md`](./12-decision-llm.md) | 第八層｜Decision & Report Layer：decision_rules.yaml、LLM system instructions | 第十三章 | Phase 9 |
| [`13-repository.md`](./13-repository.md) | 第九層｜Repository Layer：Repository Interface、CSV/SQLite/DuckDB 切換 | 第十四章 | Phase 8 |
| [`14-api-gateway.md`](./14-api-gateway.md) | 【v3.0】第十層｜API Gateway：FastAPI 路由、Response Schema、依賴注入 | 第十五章 | Phase 10 |
| [`15-frontend.md`](./15-frontend.md) | 【v3.0】第十一層｜互動式報表前端：五大頁面規格、TypeScript 型別契約、Docker 部署 | 第十六章 | Phase 11 |
| [`90-crosscutting.md`](./90-crosscutting.md) | 橫切關注點：Versioning、Telemetry Layer、Error Domain（全層級適用）| 第十七章 | 全 Phase |
| [`95-output-schema.md`](./95-output-schema.md) | 最終 OutputPayload 完整 JSON 範例 | 第十八章 | Phase 9 驗收 |
| [`99-roadmap.md`](./99-roadmap.md) | Cline 分階段實作指南（Phase 1～11 對應目錄、重點、驗收標準）| 第十九章 | 主索引 |
| [`99-appendix.md`](./99-appendix.md) | requirements.txt、未來擴充規則、v2.0→v2.1 遷移指南、架構決策記錄（ADR）| 第二十章 | — |

## 建議閱讀／實作順序

1. 先讀 `00-overview.md` 掌握十一層架構全貌與不可違反的設計原則。
2. 讀 `90-crosscutting.md`，這是所有層級都必須遵守的全域約束（版本化、錯誤分類、可觀察性），務必先建立認知再進入個別層級。
3. 依 `99-roadmap.md` 的 Phase 順序，逐一打開對應檔案（`05-ledger.md` → `06-market-data.md` → … → `15-frontend.md`）。
4. 每個 Phase 完成後，對照該檔案內的驗收標準與 `95-output-schema.md` 進行整合驗證。
5. 遇到舊版本概念或遷移問題時查閱 `99-appendix.md`。

## 維護規則

- 任何層級的 Schema 變更（例如新增 Pydantic 欄位）必須同步更新 `04-domain-models.md` 與該欄位实際使用的層級檔案，並在 `99-appendix.md` 的遷移指南區塊記錄。
- 任何新增 API 端點，必須同步更新 `14-api-gateway.md`（後端契約）與 `15-frontend.md`（前端型別），兩者欄位定義須保持逐一對應，禁止前端自行推算其中差異。
- 跨檔案引用一律使用檔名（如 `06-market-data.md`），不使用舊版「第七章」之類的章節編號，避免拆分後編號失效。
