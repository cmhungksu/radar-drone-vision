"""
diagram_pipeline.py

用途：
1. 作為可執行版骨架，串接圖種判斷、模板、輸出前檢查
2. 預留統計圖表、流程圖、架構圖的共同入口
3. 預留 PNG trim、Word caption / cross-reference 的整合點

注意：
- 這是骨架版，不含完整 PPTX / DOCX 實作
- 適合交給 Codex 持續擴充
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict

from diagram_router import (
    DiagramType,
    choose_diagram_strategy,
    recommend_chart_type,
    word_export_checklist,
    chart_design_checklist,
)


@dataclass
class PipelineRequest:
    title: str
    request_text: str
    data: Dict[str, Any] | None = None
    need_pptx: bool = True
    need_word: bool = False
    output_dir: str = "output"


def ensure_output_dir(path: str) -> Path:
    out = Path(path)
    out.mkdir(parents=True, exist_ok=True)
    return out


def build_source_definition(req: PipelineRequest) -> Dict[str, Any]:
    decision = choose_diagram_strategy(req.request_text)
    source = {
        "title": req.title,
        "diagram_type": decision.diagram_type.value,
        "source_format": decision.source_format,
        "primary_output": decision.primary_output,
        "secondary_outputs": decision.secondary_outputs,
        "data": req.data or {},
    }

    if decision.diagram_type == DiagramType.CHART:
        data = req.data or {}
        chart_type = recommend_chart_type(
            is_ratio=data.get("is_ratio", False),
            is_time_series=data.get("is_time_series", False),
            is_ranking=data.get("is_ranking", False),
            is_likert=data.get("is_likert", False),
            category_count=len(data.get("categories", [])),
        )
        source["chart_type"] = chart_type.value

    return source


def save_source_json(source: Dict[str, Any], output_dir: Path) -> Path:
    import json
    filename = output_dir / "source_definition.json"
    filename.write_text(json.dumps(source, ensure_ascii=False, indent=2), encoding="utf-8")
    return filename


def trim_png_whitespace(png_path: Path) -> Path:
    """
    預留：日後可在此串接 PIL / OpenCV 進行四周白邊裁切
    """
    return png_path


def export_word_with_crossrefs(docx_path: Path) -> Path:
    """
    預留：日後可在此串接 docx 生成、caption、交互參考、圖號排序
    """
    return docx_path


def run_pipeline(req: PipelineRequest) -> Dict[str, Any]:
    output_dir = ensure_output_dir(req.output_dir)
    source = build_source_definition(req)
    source_file = save_source_json(source, output_dir)

    result = {
        "source_file": str(source_file),
        "decision": source["diagram_type"],
        "checks": [],
    }

    if source["diagram_type"] == "chart":
        result["checks"].extend(chart_design_checklist())

    if req.need_word:
        result["checks"].extend(word_export_checklist())

    return result


if __name__ == "__main__":
    req = PipelineRequest(
        title="平台滿意度比較",
        request_text="請幫我做一張滿意度長條圖，最後要進 PPTX 和 Word",
        data={
            "categories": ["平台A", "平台B", "平台C"],
            "series": [{"name": "滿意度", "values": [4.2, 3.8, 4.5]}],
            "unit": "分",
        },
        need_word=True,
        output_dir="output_demo",
    )
    result = run_pipeline(req)
    print(result)
ALLOWED_FONT_SIZES = {16, 20, 24, 28, 32, 36}
ZH_FONT = "標楷體風格"
EN_FONT = "Times New Roman"


def validate_font_sizes(font_sizes: list[int]) -> list[str]:
    errors = []
    for size in font_sizes:
        if size not in ALLOWED_FONT_SIZES:
            errors.append(f"不允許的字級: {size}")
    return errors


def validate_font_families(font_map: dict[str, str]) -> list[str]:
    errors = []
    zh_font = font_map.get("zh", "")
    en_font = font_map.get("en", "")

    if not zh_font:
        errors.append("缺少中文字型設定")
    if not en_font:
        errors.append("缺少英文字型設定")

    if "Times New Roman" not in en_font:
        errors.append(f"英文字型不符合規範: {en_font}")

    return errors


def validate_text_not_overlapped(shape_checks: list[dict]) -> list[str]:
    errors = []
    for item in shape_checks:
        if not item.get("text_fits", True):
            errors.append(f"{item.get('name', 'unknown')} 文字未完整落入容器")
        if item.get("overlapped", False):
            errors.append(f"{item.get('name', 'unknown')} 發生文字覆蓋")
        if item.get("clipped", False):
            errors.append(f"{item.get('name', 'unknown')} 文字被裁切")
    return errors


def validate_supporting_visuals(meta: dict) -> list[str]:
    errors = []
    if not meta.get("has_supporting_visual", False):
        errors.append("缺少陪襯示意圖或情境圖")
    return errors
