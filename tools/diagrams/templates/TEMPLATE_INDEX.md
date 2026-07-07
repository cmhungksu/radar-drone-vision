# TEMPLATE_INDEX.md

本文件說明 `tools/diagrams/templates/` 內各 PPTX 模板的用途。

## 1. base_blank_tw.pptx
**用途：** 通用空白模板  
**適用：** 沒有完全對應模板時  
**注意：** 只能作為回退，不應優先使用

## 2. flow_layout_tw.pptx
**用途：** 流程圖、SOP、審查流程  
**適用：**
- concept review flow
- SOP
- 教學流程
- 申請與核准流程

## 3. stack_arch_layout_tw.pptx
**用途：** 系統架構圖、軟體堆疊圖、平台分層圖  
**適用：**
- 前端 / 後端 / API / DB
- layered architecture
- software stack
- 平台整體分層

## 4. chart_layout_tw.pptx
**用途：** 一般統計圖表  
**適用：**
- 長條圖
- 圓餅圖 / 環圈圖
- 折線圖
- KPI 數值圖表
- 比例結構圖

## 5. survey_chart_tw.pptx
**用途：** 問卷圖表與 Likert 分析  
**適用：**
- 五點量表
- 滿意度分布
- 使用者態度分析
- 教學評量

## 6. proposal_compare_tw.pptx
**用途：** 提案頁、比較頁、圖文混合頁  
**適用：**
- 方案 A / B 比較
- 現況 vs 導入後
- 概念說明頁
- 情境圖 + 文字說明頁

## 模板選擇原則

1. 若需求為數值資料，優先判斷是否為統計圖表
2. 若為問卷或 Likert，優先使用 `survey_chart_tw.pptx`
3. 若為一般統計圖表，優先使用 `chart_layout_tw.pptx`
4. 若為流程圖，使用 `flow_layout_tw.pptx`
5. 若為堆疊架構圖，使用 `stack_arch_layout_tw.pptx`
6. 若為提案型圖文混排頁，使用 `proposal_compare_tw.pptx`
7. 若都不符合，回退到 `base_blank_tw.pptx`
