# Antigravity 整合方案：檔案歸位系統 + 記憶庫交接法（Repo-First）

## 0. 整合邏輯

原本兩份資料各自解決不同問題：

| 方案 | 解決什麼 | 對應到 |
|---|---|---|
| 方案一 + 方案二（Antigravity Rules + Workspace） | **空間問題**：東西該放哪裡、Agent 權限邊界在哪 | `.agents/rules.md`、`src/`、`tests/`、`sandbox/` |
| 方案三（Repo-First 記憶庫） | **時間軸問題**：上一個 Agent 做了什麼、下一個該接什麼 | `docs/.ai/` |

整合原則只有一條：**不另開一套平行資料夾系統，把記憶庫直接掛在既有的 `docs/` 底下**，讓 `.agents/rules.md` 從「單純的歸位規則」升級為「歸位規則 + 交接憲法」。這樣未來 clone 這個 repo 的人或新 Agent，只要打開 Antigravity，讀一份 rules.md 就能同時知道「東西放哪」和「該去哪裡讀記憶」。

---

## 1. 修訂後的資料夾架構

**先釐清一個命名觀念**：`antigravity-workspace` 這個名稱只是「範例代稱」，實際上這一層資料夾**就是你的專案本身**，資料夾名稱應該是專案的真實名稱（例如 `my-ecommerce-app`），而不是固定寫死叫 `antigravity-workspace`。

各家 AI 工具（Antigravity、Cursor、Codex、Claude Code/Cowork）判斷「工作根目錄在哪」，靠的不是資料夾名稱，而是**你把哪個資料夾開啟成專案（Open Folder / Open Project）**。也就是說：
- 在 Antigravity 裡，你把這個專案資料夾載入為主專案，Agent 權限邊界就自動框在這層以下。
- 在 Cursor 裡，你 `Open Folder` 開啟這個目錄，`.cursor/rules/` 才會被讀到。
- 在 Codex / Claude Code / Cowork 裡，你在這個目錄下啟動指令列或載入專案，`AGENTS.md` / `CLAUDE.md` 才會被自動抓取。

所以下方架構圖中最外層的資料夾，請直接替換成你專案的實際名稱，其餘的內部結構（`.agents/`、`docs/.ai/`、`src/` 等）**維持不動**，這才是真正跨工具都認得的部分：

```
{你的專案名稱}/                    # ← 這一層＝實際專案資料夾，名稱由你決定，不是固定的 antigravity-workspace
├── .gitignore                    # 【新增】排除清單,定義見 3.6 節
├── AGENTS.md                     # 【新增】Codex 及其他相容工具的入口（薄檔，導引至下方）
├── CLAUDE.md                     # 【新增】Claude Code / Claude Cowork 的入口
├── .cursor/
│   └── rules/
│       └── 00-handover.mdc       # 【新增】Cursor Agent 模式的入口
│
├── .agents/
│   └── rules.md                  # 【最高憲法】歸位規則 + Commit 規則 + 交接規則（三合一，規則本體）
│
├── .github/
│   └── workflows/
│       └── ai_guardrail.yml      # CI：檢查 commit 是否有更新 session_logs
│
├── docs/
│   ├── .ai/                      # 🧠 AI 專屬記憶庫（新增，來自方案三）
│   │   ├── architecture.md       # 靜態上下文：專案目標、技術棧、業務邏輯（極少變動）
│   │   ├── rules/                # 細分模組規則
│   │   │   ├── frontend.md
│   │   │   ├── backend.md
│   │   │   └── api_spec.md
│   │   └── session_logs/         # 動態交接日誌（每個工作階段一份）
│   │       ├── _TEMPLATE.md      # 交接日誌固定範本（規則本體，非參考）
│   │       ├── 001_db_schema.md
│   │       ├── 002_backend_api.md
│   │       ├── 003_frontend_cart.md
│   │       └── _LATEST.md        # 指標檔（YAML frontmatter），永遠指向「目前最新一份」
│   │
│   └── 2026-07/                  # 📄 人類可讀的一般文件、報告、規格書（既有的方案二用途）
│       └── auth_api.md
│
├── src/
│   ├── frontend/
│   └── backend/
│
├── tests/
└── sandbox/
```

### 關鍵差異說明：`docs/.ai/` vs `docs/YYYY-MM/`

這兩個資料夾常被搞混，務必在 rules.md 中寫清楚：

- **`docs/.ai/`**：寫給 **AI 自己**看的，內容是「狀態」與「待辦」，語氣像交接筆記，不必修飾。
- **`docs/YYYY-MM/`**：寫給 **人類** 看的，內容是「產出物」，例如正式 API 文件、架構簡報，語氣正式、可對外。

判斷準則：這份文件如果拿掉，下一個 Agent 會不知道接下來要做什麼 → 放 `.ai/`；如果拿掉，只是少了一份參考資料，不影響接手 → 放 `YYYY-MM/`。

---

## 2. `_LATEST.md` 指標檔（解決方案三原本的小漏洞）

方案三原文只靠檔名編號（001、002...）讓下一個 Agent 找最新日誌，但沒規定「怎麼找」——人多手雜時容易漏讀。加一個永遠只有一份、內容極簡的指標檔。

**格式必須固定，且採 YAML frontmatter**（而非純敘述句），原因是 `_LATEST.md` 不只給 Agent 讀，將來 `ai_guardrail.yml`（CI）也要能自動解析這個檔案，判斷「這次 commit 有沒有正確更新交接指標」。純敘述句（例如「最新交接日誌：xxx」）對人友善，但寫 CI 腳本時很難穩定抓取字串，容易因為 Agent 措辭稍微不同就解析失敗。固定為以下格式：

```markdown
---
latest: session_logs/003_frontend_cart.md
previous: session_logs/002_backend_api.md
updated_at: 2026-07-07T14:30:00+08:00
updated_by: Agent C (frontend)
---

# _LATEST.md
本檔案由 Agent 自動維護，請勿手動編輯內容以外的欄位。
最新交接內容請開啟 `latest` 欄位指向的檔案。
```

**規則（必須寫進 `.agents/rules.md`，不能只當範例）**：
- 每次新增 session log 時，Agent 必須同步覆寫 `_LATEST.md` 的 frontmatter 三個欄位（`latest`、`previous`、`updated_at`、`updated_by`），缺一不可。
- `latest` 與 `previous` 的路徑必須是實際存在的檔案，Agent 寫入前應自我檢查檔案是否已建立成功。
- 人類或 CI 可透過解析 frontmatter，機械化比對「本次 commit 變更的檔案」與「`latest` 欄位指向的檔案」是否一致，藉此判斷交接是否確實完成。

---

## 3. 各檔案的定義與撰寫規則

### 3.1 `.agents/rules.md`（最高憲法，三合一）

在你原本方案二的 rules.md 基礎上，新增第 4、5 節：

```markdown
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

## 6. `.gitignore` 使用規範（新增）
- 專案根目錄的 `.gitignore` 內容定義見 3.6 節，由人類於初始化階段建立。
- **嚴禁將以下路徑加入 `.gitignore`**：`docs/.ai/`、`.agents/`——
  這兩個目錄是整套記憶庫與規則系統的核心，一旦被忽略，
  交接機制會在沒有任何錯誤訊息的情況下悄悄失效，且極難察覺。
- Agent 若基於任務需要新增 `.gitignore` 項目（例如新增了某個框架特有的暫存目錄），
  只能「新增」不可「刪除既有規則」，且不得於同一次 Commit 中順帶修改 `.gitignore`
  與程式碼——`.gitignore` 的變更必須獨立成一次 Commit，方便日後追蹤。
```

### 3.2 `docs/.ai/architecture.md`（靜態上下文）

**建立時機**：在專案第一次啟動、任何 Agent 動手寫程式碼**之前**建立，由人類在「階段一：專案初始化」（見第 5 節）下達指令時，或由第一個接手的 Agent 依 `rules.md` 第 4 節的規定主動向人類索取資訊後建立——兩種路徑都可以，但**不能沒有這一步就開始開發**，這點已經寫進 `rules.md` 本體（見上方「若 architecture.md 不存在」條款），不是只靠提示詞提醒。

只在專案目標、技術棧、業務邏輯**真的改變**時才更新，平常不動。

```markdown
# 專案架構總覽

## 專案目標
（一句話講清楚：例如「電商平台，含購物車與金流串接，目標 3 步驟內結帳」）

## 技術棧
- 前端：
- 後端：
- 資料庫：
- 部署：

## 核心業務邏輯
（條列關鍵規則，例如訂單與使用者的關聯限制、金流狀態機等）

## 模組地圖
- /src/frontend → 對應功能
- /src/backend → 對應功能
```

### 3.3 `docs/.ai/rules/*.md`（模組細則）

當某個模組有 architecture.md 裝不下的細節時才拆出來，例如：

```markdown
# backend.md
- API 一律回傳 { success, data, error } 格式
- 資料庫操作一律透過 Repository 層，禁止在 Controller 直接寫 SQL
- 錯誤碼定義：見 error_codes.md
```

### 3.4 `docs/.ai/session_logs/_TEMPLATE.md`（交接日誌範本，必須是實體檔案）

**這份模板必須真的存成一個檔案放進 repo**（路徑：`docs/.ai/session_logs/_TEMPLATE.md`），而不是只寫在這份規劃文件裡當參考——因為 Agent 執行任務時只會讀 repo 裡的檔案，不會讀這份規劃書。`rules.md` 第 4 節已明確要求新交接日誌「格式須完全比照 `_TEMPLATE.md`」，所以這個檔案是被規則直接引用的對象，不可省略。

固定模板，每個欄位都要填滿，不可省略：

```markdown
# Session Log {編號} — {主題}

## Agent 身份
（例如：前端專家 / Agent C）

## 驗收條件逐項核對
（列出接手時確認過的驗收條件，逐項標記是否達成；未達成者必須同時出現在下方 Pending Tasks）
- [ ]

## 完成事項
-

## 目前阻塞（Blockers）
（若無，填寫「無」）

## 給下一個 Agent 的上下文
-

## 待辦事項（Pending Tasks for Next Agent）
1.

## 本次變更檔案
-

## Commit
```

實際產生日誌時（例如 `003_frontend_cart.md`），就是複製這份 `_TEMPLATE.md`、填入內容、改檔名。範例填寫結果：

```markdown
# Session Log 003 — Frontend Cart

## Agent 身份
前端專家（Agent C）

## 驗收條件逐項核對
- [x] 購物車頁面可正確顯示已加入商品
- [x] 可呼叫 /api/orders 取得訂單資料
- [ ] 庫存不足時應阻擋結帳（後端尚未支援，已列入 Pending Tasks）

## 完成事項
- 實作購物車頁面 UI（/src/frontend/cart/）
- 串接 /api/orders GET 端點

## 目前阻塞（Blockers）
- 後端 /api/orders POST 尚未回傳庫存驗證結果，前端暫時 mock

## 給下一個 Agent 的上下文
- 購物車數量變更是即時呼叫 API，沒有做 debounce，如果要優化效能可以加

## 待辦事項（Pending Tasks for Next Agent）
1. 後端補上庫存驗證邏輯
2. 前端移除 mock，改接真實回傳

## 本次變更檔案
- src/frontend/cart/CartPage.tsx（新增）
- src/frontend/cart/api.ts（新增）

## Commit
feat(frontend): 新增購物車頁面並串接訂單查詢 API
```

### 3.5 `.github/workflows/ai_guardrail.yml`（CI 守門）

邏輯上只需比對：本次 PR/commit 是否有新增 `docs/.ai/session_logs/` 底下的檔案，`_LATEST.md` 的 frontmatter 是否有同步更新，且 `latest` 欄位指向的檔案確實存在。若無 → CI 失敗，退回。（實際 workflow 腳本可再依你的 CI 平台補上，這裡先確立規則層級。）

### 3.6 `.gitignore`（排除清單，由人類於初始化階段建立）

之前的規劃漏掉了這一項——沒有明講「哪些東西不該進 git」，容易出現兩種相反的事故：Agent 把不該提交的本機檔案（例如個人層級的記憶檔）誤 commit 進去，或是反過來，Agent 誤把記憶庫本身排除掉導致交接系統悄悄失效。分四類規範：

```gitignore
# === 1. 語言/框架標準忽略項（依專案技術棧調整）===
node_modules/
dist/
build/
__pycache__/
.env
.env.local

# === 2. AI 工具本機專屬檔案（不可共用，也不該進 git）===
CLAUDE.local.md              # Claude Code 個人層記憶，僅限本機
.cursor/cache/                # Cursor 本機快取（非 rules，rules 要留著）

# === 3. 實驗與暫存區：內容不進 git，但保留資料夾結構 ===
/sandbox/*
!/sandbox/.gitkeep

# === 4. 作業系統與 IDE 雜訊 ===
.DS_Store
.vscode/
.idea/
```

**必須被排除**：`/sandbox/` 的內容（本來就是拋棄式實驗區，不該累積進版本紀錄）、各工具的個人層/本機層記憶檔（`CLAUDE.local.md` 等）、標準的建置產物與環境變數檔。

**絕對不可被排除**：`docs/.ai/`（含 `architecture.md`、`session_logs/`、`_LATEST.md`）與 `.agents/rules.md`——這是整套交接系統的骨幹，必須隨每次 commit 一起進版本控制，才能讓下一個 Agent 或下一個人類看到。這條規則已同步寫進 `rules.md` 第 6 節，作為雙重防護（既在 rules 裡禁止 Agent 這樣做，也建議在 `.gitignore` 建立當下就不要留這個誤觸的可能）。

---

## 4. 跨工具交接：Codex / Cursor / Claude Code / Claude Cowork

這套架構目前只考慮了「Antigravity 內部」的 Agent 交接。但如果專案未來會換手給 Codex、Cursor 或 Claude Code / Cowork 接手，會遇到一個現實問題：**每個工具讀取規則的檔案名稱與格式都不一樣**，而且不是每個都吃 `.cursorrules` 這種舊格式。

### 4.1 現況：三種工具讀不同的檔案

| 工具 | 讀什麼檔案 | 現況重點 |
|---|---|---|
| **Codex** | `AGENTS.md`（根目錄，支援巢狀路徑分層） | 開放標準（已捐給 Linux Foundation），Cursor、Copilot、Gemini CLI、Aider、Windsurf 也都原生支援，是最保底的跨工具選擇 |
| **Cursor** | `.cursor/rules/*.mdc`（新格式） | 舊的 `.cursorrules` **在 Agent 模式下已被忽略**，不能再當成主要交接檔；新格式需要 YAML frontmatter（`description`、`globs`、`alwaysApply`）控制載入時機 |
| **Claude Code / Claude Cowork** | `CLAUDE.md`（根目錄）+ `.claude/rules/`（模組化細則） | Anthropic 的三層記憶模型：專案層 `CLAUDE.md`、個人層 `~/.claude/CLAUDE.md`、本機層 `CLAUDE.local.md`（不進 git）；另外還有 Auto Memory 會自動寫筆記，但那份記憶只有 Claude Code 自己看得到，換到其他工具就讀不到 |

### 4.2 整合原則：單一真相來源 + 各工具的薄入口檔

**不要把 `.agents/rules.md` 的內容複製五份、分別改格式**——那樣三個月後一定會 drift（各家規則寫得不一樣，互相矛盾）。正確做法是分兩層：

- **本體層（不變）**：`.agents/rules.md` 與 `docs/.ai/` 整套維持原樣。這些是純 Markdown，跟工具無關，任何 Agent 只要「被要求去讀」就讀得懂。
- **入口層（新增，依工具而異）**：在根目錄放各工具原生會自動載入的檔案，內容盡量薄，只做兩件事：①宣告該工具格式特有的東西（如 Cursor 的 frontmatter）②導引它去讀 `.agents/rules.md` 與 `docs/.ai/`。

這樣以後若再冒出第四個工具（例如 Windsurf、Gemini CLI），只要照抄 `AGENTS.md` 的內容再包一層入口檔即可，`docs/.ai/` 和 `.agents/rules.md` 完全不用動。

### 4.3 各入口檔內容

**`AGENTS.md`（給 Codex，也是跨工具的底線保障）**

```markdown
# AGENTS.md

本專案規則詳見 /.agents/rules.md（歸位規則、Commit 規範）
與 /docs/.ai/architecture.md（架構總覽）。

## 開始任何任務前必讀
1. docs/.ai/architecture.md
2. docs/.ai/session_logs/_LATEST.md 指向的最新交接日誌
3. .agents/rules.md 第 4 節（交接規則）

## 結束任務前必做
新增 docs/.ai/session_logs/ 交接日誌並更新 _LATEST.md，
細節格式見 .agents/rules.md。
```

**`.cursor/rules/00-handover.mdc`（給 Cursor，注意 frontmatter 是必要的）**

```markdown
---
description: 交接記憶庫規則，每次 Agent 任務都要套用
alwaysApply: true
---
# 交接規則
開始前讀 docs/.ai/architecture.md 與 session_logs/_LATEST.md。
結束前依 .agents/rules.md 第 4 節新增交接日誌並更新 _LATEST.md。
```

`alwaysApply: true` 確保每次對話都會自動載入這份規則，不用手動用 `@` 呼叫；一定要放在 `.cursor/rules/` 底下，放在根目錄的 `.cursorrules` 在 Agent 模式已經失效。

**`CLAUDE.md`（給 Claude Code / Claude Cowork）**

```markdown
# CLAUDE.md

專案架構詳見 docs/.ai/architecture.md，歸位與交接規則詳見 .agents/rules.md。

## 交接流程
開始任務前先讀 docs/.ai/session_logs/_LATEST.md 找到最新交接日誌。
結束任務前依 .agents/rules.md 規則寫入新的交接日誌並更新 _LATEST.md。

## 關於 Auto Memory
Auto Memory 僅供輔助（例如記住除錯細節、個人偏好），
不可取代 docs/.ai/session_logs/ 的正式交接流程——
因為 Auto Memory 只有 Claude Code 看得到，換手給 Codex 或 Cursor 時完全讀不到。
```

### 4.4 小結：跨工具部分改了什麼

- 新增三個「入口檔」（`AGENTS.md`、`.cursor/rules/00-handover.mdc`、`CLAUDE.md`），各自符合該工具的原生格式。
- `.agents/rules.md` 的角色從「被工具直接讀取的檔案」升級為「被三個入口檔共同引用的規則本體庫」。
- `docs/.ai/` 完全不受影響，因為它本來就是工具無關的純檔案交接機制——這也是方案三原本設計最大的優勢。

---

## 5. 各階段的提示詞（System Prompt / 任務開頭指令）

### 階段一：專案初始化（只做一次，人類下達）

這一版是給「AI 自行從規劃書一次建置整套資料夾與檔案」的情境使用，已納入審查時提出的六項防護要點：

```
請閱讀 /reference/Antigravity_記憶庫整合方案.md（以下稱「規劃書」），
依照裡面第 1 節的資料夾架構圖，以及第 3 節、第 4 節各檔案的定義，
在目前這個資料夾（即為本專案，資料夾名稱本身就是專案名稱，不需另外詢問或建立新的外層資料夾）
建立以下所有檔案與資料夾骨架：

- .gitignore
- AGENTS.md
- CLAUDE.md
- .cursor/rules/00-handover.mdc
- .agents/rules.md
- .github/workflows/ai_guardrail.yml
- docs/.ai/architecture.md
- docs/.ai/rules/（資料夾，暫不需建立內容檔案）
- docs/.ai/session_logs/_TEMPLATE.md
- src/frontend/, src/backend/, tests/, sandbox/

執行時請遵守以下限制：
1. 只萃取規劃書中「各檔案的定義」小節裡的程式碼區塊（模板本體）作為檔案內容，
   不要把規劃書中的說明文字、審查對話、範例填寫結果一併寫入實際檔案。
2. docs/.ai/architecture.md 只建立空骨架（保留標題：專案目標、技術棧、核心業務邏輯、模組地圖），
   內文留白，不可自行假設或編造專案內容。
3. docs/.ai/session_logs/ 底下這次只建立 _TEMPLATE.md，不要生成任何編號日誌（001 等），
   也不要建立 _LATEST.md——這兩者要等第一個實質開發任務結束後才會產生。
4. 全部建立完成後，列出你實際建立的完整檔案清單給我核對，
   不要自行執行 git commit。
```

建完之後，請對照規劃書第 1 節的架構圖手動檢查一次，尤其是 `.agents/`、`.cursor/`、`.github/`、`.gitignore` 這幾個隱藏檔案／資料夾容易被忽略，確認 AI 真的都建對了再開工。

### 階段二：每次新 Agent 接手任務開始時（固定開場白）

```
在開始任何工作之前，請先依序完成：
1. 讀取 docs/.ai/architecture.md，理解專案全局
2. 讀取 docs/.ai/session_logs/_LATEST.md，找到最新交接日誌路徑
3. 完整讀取該交接日誌，理解上一棒的 Pending Tasks 與 Blockers
4. 讀取 .agents/rules.md 確認歸位與 Commit 規則
讀完後，用一句話跟我確認你要接手的任務是什麼，
並列出你認為這次任務的「驗收條件」給我確認——
若我沒有明確給過驗收條件，你必須先提出草案讓我確認，不可自行認定後就開始動工。
```

### 階段三：Agent 工作結束、準備交接時（固定收尾指令）

```
在宣告任務完成前，請先逐項核對階段二確認過的驗收條件是否都已達成，
未達成的項目不可視為完成，必須列入 Pending Tasks。
確認完成後，請依照 .agents/rules.md 第 4、6 節規則：
1. 在 docs/.ai/session_logs/ 新增一份編號遞增的交接日誌，
   格式須完全比照 _TEMPLATE.md，包含驗收條件逐項核對結果
2. 覆寫 docs/.ai/session_logs/_LATEST.md 的 YAML frontmatter
3. 確認所有程式碼與文件都放在正確路徑（依歸位規則自我檢查一次）
4. 確認沒有誤將 docs/.ai/ 或 .agents/ 加入 .gitignore
完成以上四步後，才可以執行 git commit。
```

### 階段四：人類做 Code Review / 抽查時

```
請比對本次變更是否符合 .agents/rules.md：
1. 程式碼是否都在正確路徑（/src、/tests、/sandbox 分離是否確實）
2. docs/.ai/session_logs/ 是否有新增對應日誌，且 _LATEST.md 是否同步更新
3. Commit message 是否符合 Conventional Commits
若有缺漏，列出具體缺漏項目，不要直接幫忙補上。
```

### 階段五：需要回滾（rollback）時

```
專案在 session_logs/00X 這個階段出了問題，請執行以下操作：
1. git revert 到 00X 對應的 commit
2. 將 docs/.ai/session_logs/_LATEST.md 改回指向 00(X-1) 的日誌
3. 刪除或標記 00X 之後（若有）的日誌為「已作廢（Deprecated）」，不要直接刪檔，保留紀錄供之後參考
```

---

## 6. 小結：這套整合方案解決了什麼

- **原方案二的弱點**：只管檔案放哪裡，Agent 之間沒有記憶，每次都要人類重新口頭交代進度 → 現在有 `docs/.ai/session_logs/` 補上。
- **原方案三的弱點**：`session_logs` 只靠編號讓下一個 Agent 猜最新進度 → 現在用 `_LATEST.md` 指標檔解決。
- **整合後的單一入口（Antigravity 內部）**：不管是新開發者、新 Agent，只要打開 `.agents/rules.md` 一份檔案，就能同時掌握「規則」「歸位邏輯」「該去哪裡讀記憶」三件事，不需要在兩套文件系統之間切換。
- **跨工具交接（Codex / Cursor / Claude Code / Cowork）**：靠三個薄入口檔（`AGENTS.md`、`.cursor/rules/00-handover.mdc`、`CLAUDE.md`）各自對應工具的原生格式，但內容都導引回同一份 `.agents/rules.md` 與 `docs/.ai/`，避免五套規則各自漂移、互相矛盾。
- **「完成任務」不再靠 Agent 自由心證**：驗收條件在任務指派時（階段二）就必須明確，交接日誌新增「驗收條件逐項核對」欄位，未達成的項目強制進 Pending Tasks，不能自行判定「已經夠好」。
- **`.gitignore` 補上明確定義與保護機制**：分四類列出該排除的內容，並在 `rules.md` 第 6 節與 `.gitignore` 建立規則中雙重強調「`docs/.ai/` 與 `.agents/` 絕對不可被忽略」，避免記憶庫在無聲無息間失效。
