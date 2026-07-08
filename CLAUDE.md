# CLAUDE.md

專案架構詳見 docs/.ai/architecture.md，歸位與交接規則詳見 .agents/rules.md。

## 交接流程
開始任務前先讀 docs/.ai/session_logs/_LATEST.md 找到最新交接日誌路徑
結束任務前依 .agents/rules.md 規則寫入新的交接日誌並更新 _LATEST.md。

## 關於 Auto Memory
Auto Memory 僅供輔助（例如記住除錯細節、個人偏好），
不可取代 docs/.ai/session_logs/ 的正式交接流程——
因為 Auto Memory 只有 Claude Code 看得到，換手給 Codex 或 Cursor 時完全讀不到。