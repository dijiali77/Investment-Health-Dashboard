# Antigravity 專案規則

## 1. 檔案歸位規則（既有）
- 核心原始碼 → /src/{模組名稱}/
- 測試 → /tests/
- 人類可讀文件/報告 → /docs/YYYY-MM/
- 實驗/暫存 → /sandbox/（嚴禁進 /src/）

## 2. 執行權限與安全限制（既有）
- 限制於 Workspace 範圍內，禁止存取專案外系統檔案。

## 3. 技術棧與風格（既有，依專案填寫）

## 4. AI 記憶庫使用規則（新增，來自方案三）
- 開始任何任務前，必須先讀取：
  1. docs/.ai/architecture.md（理解全局）
  2. docs/.ai/session_logs/_LATEST.md（找到上一棒交接內容）
  3. 該交接內容指向的 session log 全文
- **若 docs/.ai/architecture.md 不存在或內容為空**：
  視為專案尚未初始化，Agent 不得逕行開始開發任務，須先執行「初始化流程」——
  向使用者索取專案目標、技術棧、核心業務邏輯，填入 architecture.md 後才可繼續。
  嚴禁在沒有 architecture.md 的情況下自行假設專案內容並開始寫程式碼。
- **若 docs/.ai/session_logs/ 為空（尚無任何交接日誌）**：
  視為第一棒任務，不需要讀交接內容，但仍須在任務結束時依規則建立第一份 001 號日誌。
- **任務完成的定義（不得由 Agent 自行認定）**：
  1. 任務指派時（不論由人類下達，或由上一棒 Agent 在交接日誌的 Pending Tasks 中列出），
     必須附上明確的「驗收條件」；沒有驗收條件的任務，視為指派不完整。
  2. 若接到的任務**沒有**明確驗收條件，Agent 不得自行推測範圍後逕自宣告完成，
     必須先向使用者確認驗收標準，再開始工作。
  3. Agent 只能在**逐項核對驗收條件皆已達成**後，才可將任務視為完成、進入交接流程；
     未達成的項目一律寫入交接日誌的 Pending Tasks，不得略過或自行判定「已經夠好」。
- 完成任務、準備結束對話前，**必須**：
  1. 在 docs/.ai/session_logs/ 新增一份編號遞增的交接日誌，
     格式須完全比照 docs/.ai/session_logs/_TEMPLATE.md 的欄位結構，不得省略任何欄位
     （若該欄位無內容，填寫「無」），且須包含驗收條件逐項核對結果
  2. 覆寫 _LATEST.md，格式須完全比照該檔案既有的 YAML frontmatter 結構
     （`latest`、`previous`、`updated_at`、`updated_by` 四個欄位缺一不可）
  3. 若有新增模組規則，更新 docs/.ai/rules/ 對應檔案
- 未完成交接日誌前，不得視為任務結束，不得執行 Commit。

## 5. Git 版本控制與 Commit 規範（既有）
- Commit 前確認：程式碼無語法錯誤 + 交接日誌已更新。
- Commit Message 採 Conventional Commits：<type>(<scope>): <description>
- 禁止未經授權自動 git push。

## 6. .gitignore 使用規範（新增）
- 專案根目錄的 `.gitignore` 內容定義見 3.6 節，由人類於初始化階段建立。
- **嚴禁將以下路徑加入 `.gitignore`**：`docs/.ai/`、`.agents/`——
  這兩個目錄是整套記憶庫與規則系統的核心，一旦被忽略，
  交接機制會在沒有任何錯誤訊息的情況下悄悄失效，且極難察覺。
- Agent 若基於任務需要新增 `.gitignore` 項目（例如新增了某個框架特有的暫存目錄），
  只能「新增」不可「刪除既有規則」，且不得於同一次 Commit 中順帶修改 `.gitignore`
  與程式碼——`.gitignore` 的變更必須獨立成一次 Commit，方便日後追蹤。