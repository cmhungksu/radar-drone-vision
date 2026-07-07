"""
diagram_router.py

用途：
1. 根據需求文字判斷圖種
2. 決定建議的結構描述語言
3. 套用固定美學規則
4. 提供 Word / PNG / 字型 / 圖表檢查清單
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List


class DiagramType(str, Enum):
    FLOW = "flow"
    ARCH = "arch"
    TOPOLOGY = "topology"
    ORG = "org"
    SEQUENCE = "sequence"
    GANTT = "gantt"
    PROPOSAL = "proposal"
    CHART = "chart"


class ChartType(str, Enum):
    PIE = "pie"
    DONUT = "donut"
    BAR = "bar"
    HBAR = "horizontal_bar"
    LINE = "line"
    STACKED_BAR = "stacked_bar"
    GROUPED_BAR = "grouped_bar"
    SCATTER = "scatter"


@dataclass
class DiagramDecision:
    diagram_type: DiagramType
    source_format: str
    primary_output: str
    secondary_outputs: List[str]
    notes: List[str] = field(default_factory=list)


@dataclass
class StyleRules:
    title_top_center: bool = True
    uniform_same_level_size: bool = True
    max_nodes_per_row: int = 4
    primary_flow_direction: str = "LR"
    support_flow_style: str = "dashed"
    max_main_colors: int = 3
    arrow_style_consistent: bool = True
    rounded_corners: bool = True
    max_chars_per_node: int = 12
    legend_position: str = "bottom-right"
    use_traditional_chinese: bool = True
    preferred_font_family: str = "DFKai-SB/BiauKai-style"
    meaning_color_grouping: bool = True
    trim_whitespace_before_word: bool = True
    require_word_cross_reference: bool = True
    chart_no_3d: bool = True
    chart_show_meaningful_colors_only: bool = True


KEYWORD_MAP: Dict[DiagramType, List[str]] = {
    DiagramType.FLOW: ["流程", "sop", "review flow", "審查流程", "申請流程", "核准流程", "pdca"],
    DiagramType.ARCH: ["架構", "architecture", "模組", "平台", "component", "deployment"],
    DiagramType.TOPOLOGY: ["拓樸", "topology", "network", "ceph", "pve", "lxc", "vm", "vpn", "gateway"],
    DiagramType.ORG: ["組織", "階層", "樹狀", "分工", "角色"],
    DiagramType.SEQUENCE: ["時序", "sequence", "api 呼叫", "request", "response", "交握"],
    DiagramType.GANTT: ["甘特", "時程", "里程碑", "timeline", "schedule", "roadmap"],
    DiagramType.PROPOSAL: ["提案", "比較圖", "概念圖", "方案圖", "價值鏈", "特色總覽"],
    DiagramType.CHART: ["圓餅圖", "長條圖", "柱狀圖", "折線圖", "趨勢圖", "百分比", "統計圖", "問卷", "kpi", "數據"],
}


DECISION_TABLE: Dict[DiagramType, DiagramDecision] = {
    DiagramType.FLOW: DiagramDecision(DiagramType.FLOW, "mermaid", "pptx", ["png", "svg", "mmd"], ["主流程左到右"]),
    DiagramType.ARCH: DiagramDecision(DiagramType.ARCH, "plantuml_or_mermaid", "pptx", ["png", "svg", "puml"], ["依層分區"]),
    DiagramType.TOPOLOGY: DiagramDecision(DiagramType.TOPOLOGY, "graphviz", "pptx", ["svg", "png", "dot"], ["核心節點置中"]),
    DiagramType.ORG: DiagramDecision(DiagramType.ORG, "mermaid_or_json", "pptx", ["png", "json", "mmd"], ["SmartArt 風格"]),
    DiagramType.SEQUENCE: DiagramDecision(DiagramType.SEQUENCE, "plantuml_sequence", "svg", ["png", "pptx", "puml"], ["技術文件優先 SVG"]),
    DiagramType.GANTT: DiagramDecision(DiagramType.GANTT, "mermaid_gantt", "pptx", ["png", "mmd"], ["PPTX 以表格與色條呈現"]),
    DiagramType.PROPOSAL: DiagramDecision(DiagramType.PROPOSAL, "json_layout", "pptx", ["png", "json"], ["優先簡報美觀"]),
    DiagramType.CHART: DiagramDecision(DiagramType.CHART, "json_or_csv", "pptx", ["png", "svg", "csv", "json"], ["依資料特性自動選擇圖表"]),
}


def detect_diagram_type(request_text: str) -> DiagramType:
    text = request_text.lower()
    for diagram_type, keywords in KEYWORD_MAP.items():
        if any(k.lower() in text for k in keywords):
            return diagram_type
    return DiagramType.PROPOSAL


def recommend_chart_type(
    *,
    is_ratio: bool = False,
    is_time_series: bool = False,
    is_ranking: bool = False,
    is_likert: bool = False,
    category_count: int = 0,
) -> ChartType:
    if is_likert:
        return ChartType.STACKED_BAR
    if is_time_series:
        return ChartType.LINE
    if is_ranking or category_count > 6:
        return ChartType.HBAR
    if is_ratio and 2 <= category_count <= 5:
        return ChartType.DONUT
    if is_ratio and category_count > 5:
        return ChartType.BAR
    return ChartType.BAR


def choose_diagram_strategy(request_text: str) -> DiagramDecision:
    diagram_type = detect_diagram_type(request_text)
    return DECISION_TABLE[diagram_type]


def default_style_rules() -> StyleRules:
    return StyleRules()


def word_export_checklist() -> List[str]:
    return [
        "PNG 已先裁掉四周空白",
        "所有圖都有圖說標題",
        "圖號連續且順序正確",
        "正文至少引用每張圖一次",
        "圖號引用使用 Word 交互參考",
        "更新欄位後圖號仍正確",
    ]


def font_fallback_checklist() -> List[str]:
    return [
        "先檢查 DFKai-SB / BiauKai / 標楷體相容字型是否存在",
        "若不存在，尋找合法免費且支援繁體中文的替代字型",
        "記錄實際使用字型、來源、授權",
        "禁止使用來源不明字型",
    ]


def color_semantic_rules() -> Dict[str, str]:
    return {
        "核心流程或主系統": "深藍",
        "決策點或人工介入": "橘色",
        "支援模組或資料流": "藍綠",
        "備註或外部系統": "灰色",
    }


def chart_design_checklist() -> List[str]:
    return [
        "是否選用合適的圖表類型",
        "是否避免使用 3D 圖表",
        "是否有標題、單位、圖例",
        "是否依語義使用固定色彩",
        "若為比例圖且類別太多，是否改用長條圖",
        "若為排名，是否已排序",
        "若為問卷 Likert，是否改用堆疊長條圖",
    ]


if __name__ == "__main__":
    sample = "請幫我畫一張滿意度長條圖，最後要進 PPTX 和 Word。"
    decision = choose_diagram_strategy(sample)
    print("diagram_type =", decision.diagram_type.value)
    print("source_format =", decision.source_format)
    print("primary_output =", decision.primary_output)
    print("secondary_outputs =", ", ".join(decision.secondary_outputs))
    print("notes =", " / ".join(decision.notes))
    print("recommended_chart =", recommend_chart_type(category_count=5).value)
from pathlib import Path
import json


def load_template_manifest(project_dir: str = ".") -> dict:
    manifest_path = Path(project_dir) / "tools" / "diagrams" / "templates" / "template_manifest.json"
    if not manifest_path.exists():
        return {"default_template": "base_blank_tw.pptx", "templates": []}
    return json.loads(manifest_path.read_text(encoding="utf-8"))


def choose_template(
    diagram_type: str,
    *,
    project_dir: str = ".",
    scene: str = "",
    is_survey: bool = False,
    is_chart: bool = False,
    is_stack_arch: bool = False,
) -> str:
    manifest = load_template_manifest(project_dir)
    templates = manifest.get("templates", [])
    default_template = manifest.get("default_template", "base_blank_tw.pptx")

    if is_survey:
        for item in templates:
            if item.get("type") == "survey":
                return str(Path(project_dir) / "tools" / "diagrams" / "templates" / item["file"])

    if is_chart or diagram_type == "chart":
        for item in templates:
            if item.get("type") == "chart":
                return str(Path(project_dir) / "tools" / "diagrams" / "templates" / item["file"])

    if is_stack_arch or diagram_type == "arch":
        for item in templates:
            if item.get("type") == "arch":
                return str(Path(project_dir) / "tools" / "diagrams" / "templates" / item["file"])

    if diagram_type == "flow":
        for item in templates:
            if item.get("type") == "flow":
                return str(Path(project_dir) / "tools" / "diagrams" / "templates" / item["file"])

    if diagram_type == "proposal":
        for item in templates:
            if item.get("type") == "proposal":
                return str(Path(project_dir) / "tools" / "diagrams" / "templates" / item["file"])

    return str(Path(project_dir) / "tools" / "diagrams" / "templates" / default_template)
