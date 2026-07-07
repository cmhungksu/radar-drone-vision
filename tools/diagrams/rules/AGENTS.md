# AGENTS.md（圖形規則）

本目錄為圖形工作規則區，所有圖形任務必須先讀取：

1. `DIAGRAM_RULES.md` - 圖種判斷、輸出格式、美學規範
2. `DIAGRAM_TEMPLATES.md` - 11 種標準圖形模板

骨架腳本位於 `../scripts/`：
- `diagram_router.py` - 圖種判斷與策略選擇
- `diagram_pipeline.py` - 圖形生成流程骨架

若本目錄規則過舊，可重新執行：
  bash ~/.claude/shared/doc_report_toolkit/scripts/setup_project_tools.sh
