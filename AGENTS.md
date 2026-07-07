# AGENTS 工作指令（{{PROJECT_NAME}}）

> **使用說明**：將此模板複製為專案根目錄的 `AGENTS.md`，
> 並將 `{{PROJECT_NAME}}` 替換為實際專案名稱，
> 再依需求填寫 B~E 各區段。

---

## A. 共用規則引用（不可修改）

本專案的圖形、文件、簡報產出規則，引用共用工具包：

**圖形工作**：必須先讀取並遵守：
1. `tools/diagrams/rules/DIAGRAM_RULES.md`（或 `~/.claude/shared/doc_report_toolkit/DIAGRAM_RULES.md`）
2. `tools/diagrams/rules/DIAGRAM_TEMPLATES.md`（或 `~/.claude/shared/doc_report_toolkit/DIAGRAM_TEMPLATES.md`）

優先使用以下程式骨架（若存在）：
- `tools/diagrams/scripts/diagram_router.py`
- `tools/diagrams/scripts/diagram_pipeline.py`

**正式文件工作**：必須遵守 `~/.claude/shared/doc_report_toolkit/REPORT_RULES.md`

**寫作語氣**：必須遵守 `~/.claude/shared/doc_report_toolkit/WRITING_RULES.md`

---

## B. 專案主要輸出物（請填寫）

- 主文件：`{{主要文件路徑}}`（例：`10_final_proposal/計畫書.docx`）
- 主簡報：`{{主要簡報路徑}}`（例：`11_presentation/計畫書簡報.pptx`）
- 報告目錄：`{{report_dir}}`

---

## C. 開機必讀與必跑流程（每次進入本目錄）

1. 先閱讀本檔 `AGENTS.md`
2. 確認主要輸出物存在（見 B 區）
3. 若有驗證腳本，執行：`python tools/verify_submission.py`
4. 若有 FAIL，先修正再進行新任務

---

## D. 未完成事項（保留直到明確完成）

<!-- 範例格式：
- [ ] 2026-03-31：待補文件 XXX，來源：YYY
- [x] 2026-03-20：已完成任務 AAA
-->

---

## E. 交付前最後檢查清單

- [ ] 主文件與來源 .md 同步
- [ ] 驗證報告已更新且無 FAIL
- [ ] 無流程痕跡用語（見共用寫作規則）
- [ ] 字型已套用（標楷體 / Times New Roman）
- [ ] 表格標題緊貼表格
- [ ] 圖說存在且圖號連續
- [ ] 簡報每頁有 speaker notes
- [ ] 首頁示意圖不與文字重疊

---

## F. 圖形工作（繼承共用規則，可依專案追加）

本專案圖形路徑：`{{diagram_dir}}`（例：`04_diagrams/` 或 `tools/diagrams/`）

涉及圖形任務時，**必須**依序：
1. 判斷圖種（流程/架構/拓樸/組織/時序/甘特/提案/統計）
2. 讀取 DIAGRAM_RULES.md
3. 讀取 DIAGRAM_TEMPLATES.md
4. 使用 diagram_router.py 決定策略
5. 輸出：原始描述檔 + PNG/SVG + PPTX
6. 若需 Word，輸出裁邊後 PNG + 圖說 + 交互參考

禁止跳過規則直接畫圖。

---

## G. 專案特定規則（依需求填寫）

<!--
在此填寫本專案獨有的規則，例如：
- 特定欄位不可修改
- 特定送審日期
- 特定格式要求
- 特定對象（委員、審查機關）的語氣要求
-->
