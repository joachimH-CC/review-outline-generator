# -*- coding: utf-8 -*-
"""
Build Markdown review outlines from a filled template spec or a natural-language
spec file that points at local course materials.

Usage:
    python build_review_outline.py <spec_path> [--output-dir DIR] [--work-dir DIR] [--refresh]
"""
from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple


SCRIPT_DIR = Path(__file__).resolve().parent
SUPPORTED_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp"}
DIAGRAM_TERMS = (
    "用例图",
    "用例表",
    "顺序图",
    "活动图",
    "状态机图",
    "状态表",
    "数据流图",
    "类图",
    "实体关系模型",
    "业务数据图",
    "组织结构图",
    "角色权限矩阵",
    "数据字典",
    "数据字典表",
)
STOP_TOKENS = {
    "什么", "哪些", "如何", "为什么", "以及", "一个", "进行", "可以",
    "系统", "需求", "用户", "使用", "创建", "描述", "包括", "应该",
    "其中", "分别", "说明", "举例", "本章", "相关", "时候", "还有",
    "主要", "管理", "模型", "图中", "软件", "课程", "流程", "数据",
    "对象", "类型", "方法", "图表", "信息", "功能", "如果", "通过",
    "需要", "项目", "内容", "用户故事", "图书馆", "在线", "应用程序",
    "系统中",
}
CHINESE_NUMERAL = {
    "一": 1, "二": 2, "三": 3, "四": 4, "五": 5,
    "六": 6, "七": 7, "八": 8, "九": 9, "十": 10,
    "十一": 11, "十二": 12, "十三": 13, "十四": 14, "十五": 15,
    "十六": 16, "十七": 17, "十八": 18, "十九": 19, "二十": 20,
}


@dataclass
class ChapterAssets:
    chapter: int
    title: str
    ppt_file: Optional[Path] = None
    exercise_file: Optional[Path] = None
    ppt_text_file: Optional[Path] = None
    exercise_text_file: Optional[Path] = None
    textbook_text_file: Optional[Path] = None
    ppt_image_files: List[Path] = field(default_factory=list)
    exercise_image_files: List[Path] = field(default_factory=list)
    textbook_image_files: List[Path] = field(default_factory=list)
    focus_points: List[str] = field(default_factory=list)


@dataclass
class QuestionSegment:
    index: int
    prompt: str
    body: str
    start_line: int = 0
    end_line: int = 0


@dataclass
class StyleConfig:
    section_heading: str = "####"
    question_heading: str = "#####"
    supplement_title: str = "PPT补充"
    image_section_title: str = "相关图示"
    image_caption_prefix: str = "图"
    analysis_heading: str = "######"


@dataclass
class SpecConfig:
    spec_path: Path
    output_dir: Path
    slides_dir: Optional[Path] = None
    slides_format: str = "pptx"
    exercises_dir: Optional[Path] = None
    textbook_pdf: Optional[Path] = None
    reference_format: Optional[Path] = None
    keypoints_path: Optional[Path] = None
    chapter_numbers: List[int] = field(default_factory=list)
    question_source: str = "exercises"
    include_images: bool = True
    generate_overview: bool = True
    chapter_question_map: Dict[int, List[int]] = field(default_factory=dict)
    chapter_focus_map: Dict[int, List[str]] = field(default_factory=dict)
    analysis_keywords: Dict[int, List[str]] = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)
    style: StyleConfig = field(default_factory=StyleConfig)


def run_extractor(script_name: str, source_dir: Path, text_dir: Path, image_dir: Path) -> None:
    cmd = [
        sys.executable,
        str(SCRIPT_DIR / script_name),
        str(source_dir),
        str(text_dir),
        str(image_dir),
    ]
    subprocess.run(cmd, check=True)


def normalize_path(raw: str, base_dir: Path) -> Path:
    raw = raw.strip().strip('"').strip("'").strip('"').strip("'")  # 多次strip处理嵌套引号
    candidate = Path(raw)
    if candidate.is_absolute():
        return candidate
    return (base_dir / candidate).resolve()


def parse_bool(value: str, default: bool) -> bool:
    token = value.strip().lower()
    if token in {"true", "yes", "1"}:
        return True
    if token in {"false", "no", "0"}:
        return False
    return default


def clean_scalar(value: str) -> str:
    value = re.split(r"\s+#", value, 1)[0].strip()
    if value in {'""', "''"}:
        return ""
    return value.strip().strip('"').strip("'")


def parse_focus_list(text: str) -> List[str]:
    cleaned = clean_scalar(text)
    cleaned = cleaned.strip("[]")
    pieces = re.split(r"[，、,]+", cleaned)
    return [piece.strip().strip('"').strip("'") for piece in pieces if piece.strip().strip('"').strip("'")]


def chapter_label_to_int(label: str) -> Optional[int]:
    match = re.search(r"第\s*([一二三四五六七八九十0-9]+)\s*章", label)
    if not match:
        match = re.search(r"^([0-9]+)\s*[章、.]", label)
        if match:
            return int(match.group(1))
        return None
    token = match.group(1)
    if token.isdigit():
        return int(token)
    return CHINESE_NUMERAL.get(token)


def parse_number_list(text: str) -> List[int]:
    return [int(token) for token in re.findall(r"\d+", text)]


def parse_chapter_range(text: str) -> List[int]:
    match = re.search(r"(\d+)\s*-\s*(\d+)", text)
    if match:
        start = int(match.group(1))
        end = int(match.group(2))
        if start <= end:
            return list(range(start, end + 1))
    singles = parse_number_list(text)
    return sorted(set(singles))


def split_analysis_keywords(text: str) -> List[str]:
    pieces = re.split(r"[、。\s]+", text.strip())
    return [piece for piece in pieces if piece and piece not in {"看描述表述", "文字一画图", "例子一补表"}]


def parse_keypoints_file(path: Path) -> Tuple[Dict[int, List[int]], Dict[int, List[str]]]:
    question_map: Dict[int, List[int]] = {}
    analysis_map: Dict[int, List[str]] = {}
    mode = ""
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line:
            continue
        if "问答" in line:
            mode = "question"
            continue
        if "分析题" in line:
            mode = "analysis"
            continue
        if mode == "question" and line.startswith("-"):
            chapter = chapter_label_to_int(line)
            if chapter is None:
                continue
            number_text = line.split(maxsplit=1)[-1]
            question_map[chapter] = parse_number_list(number_text)
        elif mode == "analysis" and "第" in line:
            chapter = chapter_label_to_int(line)
            if chapter is None:
                continue
            keywords = split_analysis_keywords(re.sub(r"^第[一二三四五六七八九十0-9]+章", "", line).strip())
            if keywords:
                analysis_map[chapter] = keywords
    return question_map, analysis_map


def parse_natural_focus_map(text: str) -> Dict[int, List[str]]:
    focus_map: Dict[int, List[str]] = {}
    for raw in text.splitlines():
        line = raw.strip().lstrip("-* ")
        if not line or "第" not in line:
            continue
        chapter = chapter_label_to_int(line)
        if chapter is None:
            continue
        if not any(token in line for token in ("重点", "考点", "知识点", "复习点")):
            continue
        if re.search(r"第[一二三四五六七八九十0-9]+章", line):
            _, rest = line.split("：", 1) if "：" in line else (None, line)
        elif ":" in line:
            _, rest = line.split(":", 1)
        else:
            rest = re.sub(r"^第[一二三四五六七八九十0-9]+\s*章", "", line)
            rest = re.sub(r"^(重点|考点|知识点|复习点)", "", rest).strip()
        items = parse_focus_list(rest)
        if items:
            focus_map[chapter] = items
    return focus_map


def parse_template_spec(spec_path: Path, text: str) -> Optional[SpecConfig]:
    if (
        "slides_dir:" not in text
        and "textbook_pdf:" not in text
        and "chapter_question_map:" not in text
        and "chapter_focus_map:" not in text
    ):
        return None

    cfg = SpecConfig(spec_path=spec_path, output_dir=spec_path.parent)
    in_block = False
    current_parent = ""
    for raw in text.splitlines():
        line = raw.rstrip()
        stripped = line.strip()
        if stripped.startswith("```"):
            in_block = not in_block
            current_parent = ""
            continue
        if not in_block or not stripped or stripped.startswith("#"):
            continue
        indent = len(line) - len(line.lstrip(" "))
        if indent == 0:
            if ":" not in stripped:
                continue
            key, value = stripped.split(":", 1)
            key = key.strip()
            value = clean_scalar(value)
            current_parent = key if value == "" else ""
            if key == "output_dir" and value:
                cfg.output_dir = normalize_path(value, spec_path.parent)
            elif key == "slides_dir" and value:
                cfg.slides_dir = normalize_path(value, spec_path.parent)
            elif key == "slides_format" and value:
                cfg.slides_format = value.strip().strip('\\"').strip('"')
            elif key == "exercises_dir" and value:
                cfg.exercises_dir = normalize_path(value, spec_path.parent)
            elif key == "textbook_pdf" and value:
                cfg.textbook_pdf = normalize_path(value, spec_path.parent)
            elif key == "reference_format" and value:
                cfg.reference_format = normalize_path(value, spec_path.parent)
            elif key == "question_source" and value:
                cfg.question_source = value
            elif key == "include_images" and value:
                cfg.include_images = parse_bool(value, True)
            elif key == "generate_overview" and value:
                cfg.generate_overview = parse_bool(value, True)
            elif key == "chapter_range" and value:
                cfg.chapter_numbers = parse_chapter_range(value)
        else:
            if ":" not in stripped:
                continue
            key, value = stripped.split(":", 1)
            key = key.strip()
            value = clean_scalar(value)
            chapter = chapter_label_to_int(key)
            if chapter is None:
                continue
            if current_parent == "chapter_question_map":
                cfg.chapter_question_map[chapter] = parse_number_list(value)
            elif current_parent == "chapter_focus_map":
                cfg.chapter_focus_map[chapter] = parse_focus_list(value)
            elif current_parent == "analysis_questions":
                cfg.analysis_keywords[chapter] = split_analysis_keywords(value)
    return cfg


def parse_natural_spec(spec_path: Path, text: str) -> SpecConfig:
    cfg = SpecConfig(spec_path=spec_path, output_dir=spec_path.parent)
    link_pattern = re.compile(r"\[([^\]]+)\]\(([^)]+)\)|\[([^\]]+)\]\(\"([^\"]+)\"\)")
    for match in link_pattern.finditer(text):
        raw = match.group(2) or match.group(4)
        resolved = normalize_path(raw, spec_path.parent)

        # Fallback: if absolute path doesn't exist, try relative to spec_path.parent
        if not resolved.exists():
            # Strip quotes again for is_absolute check
            clean_raw = raw.strip().strip('"').strip("'").strip('"').strip("'")
            if Path(clean_raw).is_absolute():
                filename = Path(clean_raw).name
                fallback = spec_path.parent / filename
                if fallback.exists():
                    resolved = fallback

        lower_name = resolved.name.lower()
        if resolved.is_dir() and resolved.name == "ppt":
            cfg.slides_dir = resolved
        elif resolved.is_dir() and "课后习题" in resolved.name:
            cfg.exercises_dir = resolved
        elif resolved.suffix.lower() == ".md" and "考点" in resolved.name:
            cfg.keypoints_path = resolved
        elif resolved.suffix.lower() == ".pdf":
            cfg.textbook_pdf = resolved
        elif resolved.suffix.lower() == ".md" and resolved != spec_path:
            cfg.reference_format = resolved

    for raw in re.findall(r"(?:[A-Za-z]:\\|\.{1,2}\\)?[^\s\"<>|]+?\.pdf", text):
        candidate = normalize_path(raw, spec_path.parent)
        if candidate.exists():
            cfg.textbook_pdf = candidate

    range_match = re.search(r"(\d+)\s*-\s*(\d+)章", text)
    if range_match:
        cfg.chapter_numbers = list(range(int(range_match.group(1)), int(range_match.group(2)) + 1))
    else:
        explicit_line = None
        for raw_line in text.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            if any(token in line for token in ("按章节生成", "生成", "章", "章节", "章节")):
                explicit_line = line
                break
        if explicit_line:
            explicit_range = re.search(r"(\d+)\s*-\s*(\d+)", explicit_line)
            if explicit_range:
                cfg.chapter_numbers = list(range(int(explicit_range.group(1)), int(explicit_range.group(2)) + 1))

    if "整理图示" in text or "整理相关图" in text:
        cfg.include_images = True
    if "只用课后习题" in text or "只用习题" in text or "只用题" in text:
        cfg.question_source = "keypoints"

    cfg.chapter_focus_map = parse_natural_focus_map(text)
    if cfg.chapter_focus_map and not cfg.chapter_numbers:
        cfg.chapter_numbers = sorted(cfg.chapter_focus_map)

    return cfg


def parse_spec(spec_path: Path, output_dir: Optional[Path]) -> SpecConfig:
    text = spec_path.read_text(encoding="utf-8")
    cfg = parse_template_spec(spec_path, text) or parse_natural_spec(spec_path, text)
    explicit_range = re.search(r"(?<!\d)(\d+)\s*-\s*(\d+)\s*章", text)
    if explicit_range:
        start = int(explicit_range.group(1))
        end = int(explicit_range.group(2))
        if start <= end:
            cfg.chapter_numbers = list(range(start, end + 1))
    if output_dir is not None:
        cfg.output_dir = output_dir
    if cfg.keypoints_path and cfg.keypoints_path.exists():
        question_map, analysis_map = parse_keypoints_file(cfg.keypoints_path)
        if not cfg.chapter_question_map:
            cfg.chapter_question_map = question_map
        else:
            cfg.chapter_question_map.update(question_map)
        if not cfg.analysis_keywords:
            cfg.analysis_keywords = analysis_map
        else:
            for chapter, keywords in analysis_map.items():
                cfg.analysis_keywords.setdefault(chapter, []).extend(
                    keyword for keyword in keywords if keyword not in cfg.analysis_keywords[chapter]
                )
    if not cfg.chapter_numbers:
        chapter_set = set(cfg.chapter_question_map) | set(cfg.analysis_keywords) | set(cfg.chapter_focus_map)
        cfg.chapter_numbers = sorted(chapter_set)
    if cfg.exercises_dir is None and (cfg.slides_dir is not None or cfg.textbook_pdf is not None):
        cfg.question_source = "keypoints"
    return cfg


def infer_style(reference_path: Optional[Path]) -> StyleConfig:
    style = StyleConfig()
    if reference_path is None or not reference_path.exists():
        return style
    lines = reference_path.read_text(encoding="utf-8").splitlines()
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        if re.match(r"^#+\s+\{.*题型.*\}", stripped):
            level = len(stripped) - len(stripped.lstrip("#"))
            style.section_heading = "#" * level
            continue
        if re.match(r"^#+\s+\{.*题号.*\}", stripped):
            level = len(stripped) - len(stripped.lstrip("#"))
            style.question_heading = "#" * level
            continue
        supplement_match = re.match(r"^>\s+\*\*(.+?)补充?\*\*", stripped)
        if supplement_match:
            style.supplement_title = supplement_match.group(1).strip()
            continue
        if re.match(r"^\*图\d+.*\*?$", stripped) or stripped.startswith("*图"):
            style.image_caption_prefix = "图"
    return style


def _detect_slides_format(slides_dir: Path) -> str:
    """Detect slides format from first matching file in directory. Returns "pptx" or "pdf"."""
    for ext in (".pptx", ".pdf"):
        for path in sorted(slides_dir.iterdir()):
            if path.suffix.lower() != ext or path.name.startswith("~$"):
                continue
            if re.search(r"第\s*\d+\s*章", path.name):
                return ext.lstrip(".")
    return "pptx"  # fallback default


def scan_assets(cfg: SpecConfig) -> Dict[int, ChapterAssets]:
    assets: Dict[int, ChapterAssets] = {}
    if cfg.slides_dir and cfg.slides_dir.exists():
        for path in sorted(cfg.slides_dir.iterdir()):
            if path.suffix.lower() != ".pptx" or path.name.startswith("~$"):
                continue
            match = re.search(r"第\s*(\d+)\s*章\s*(.+)\.pptx$", path.name)
            if not match:
                continue
            chapter = int(match.group(1))
            title = match.group(2).strip()
            assets.setdefault(chapter, ChapterAssets(chapter=chapter, title=title)).ppt_file = path
    if cfg.exercises_dir and cfg.exercises_dir.exists():
        for path in sorted(cfg.exercises_dir.iterdir()):
            if path.suffix.lower() != ".docx" or path.name.startswith("~$"):
                continue
            match = re.match(r"(\d+)_", path.name)
            if not match:
                continue
            chapter = int(match.group(1))
            title = assets.get(chapter).title if chapter in assets else f"第{chapter}章"
            assets.setdefault(chapter, ChapterAssets(chapter=chapter, title=title)).exercise_file = path
    if cfg.textbook_pdf:
        for chapter in cfg.chapter_numbers:
            assets.setdefault(chapter, ChapterAssets(chapter=chapter, title="教材重点"))
    for chapter, focus_points in cfg.chapter_focus_map.items():
        entry = assets.setdefault(chapter, ChapterAssets(chapter=chapter, title="教材重点"))
        entry.focus_points = focus_points
    return assets


def ensure_extracted(cfg: SpecConfig, assets: Dict[int, ChapterAssets], work_dir: Path, refresh: bool) -> None:
    ppt_text_dir = work_dir / "ppt_text"
    ppt_image_dir = work_dir / "ppt_images"
    exercise_text_dir = work_dir / "exercise_text"
    exercise_image_dir = work_dir / "exercise_images"
    textbook_text_dir = work_dir / "textbook_text"
    textbook_image_dir = work_dir / "textbook_images"
    ppt_text_dir.mkdir(parents=True, exist_ok=True)
    ppt_image_dir.mkdir(parents=True, exist_ok=True)
    exercise_text_dir.mkdir(parents=True, exist_ok=True)
    exercise_image_dir.mkdir(parents=True, exist_ok=True)
    textbook_text_dir.mkdir(parents=True, exist_ok=True)
    textbook_image_dir.mkdir(parents=True, exist_ok=True)

    if cfg.slides_dir and (refresh or not any(ppt_text_dir.glob("*.txt"))):
        run_extractor("extract_pptx.py", cfg.slides_dir, ppt_text_dir, ppt_image_dir)
    if cfg.exercises_dir and (refresh or not any(exercise_text_dir.glob("*.txt"))):
        run_extractor("extract_docx.py", cfg.exercises_dir, exercise_text_dir, exercise_image_dir)
    if cfg.textbook_pdf and (refresh or not any(textbook_text_dir.glob("*.txt"))):
        run_extractor("extract_pdf.py", cfg.textbook_pdf, textbook_text_dir, textbook_image_dir)

    textbook_text_file: Optional[Path] = None
    textbook_images: List[Path] = []
    if cfg.textbook_pdf:
        textbook_text_file = textbook_text_dir / f"{cfg.textbook_pdf.stem}.txt"
        if not textbook_text_file.exists():
            matches = sorted(textbook_text_dir.glob("*.txt"))
            textbook_text_file = matches[0] if matches else None
        textbook_images = sorted(
            path for path in textbook_image_dir.glob(f"{cfg.textbook_pdf.stem}_*") if path.suffix.lower() in SUPPORTED_IMAGE_EXTS
        )

    for chapter, entry in assets.items():
        if entry.ppt_file is not None:
            stem = entry.ppt_file.stem
            text_file = ppt_text_dir / f"{stem}.txt"
            if text_file.exists():
                entry.ppt_text_file = text_file
            entry.ppt_image_files = sorted(
                path for path in ppt_image_dir.glob(f"{stem}_*") if path.suffix.lower() in SUPPORTED_IMAGE_EXTS
            )
        if entry.exercise_file is not None:
            stem = entry.exercise_file.stem
            text_file = exercise_text_dir / f"{stem}.txt"
            if text_file.exists():
                entry.exercise_text_file = text_file
            entry.exercise_image_files = sorted(
                path for path in exercise_image_dir.glob(f"{stem}_*") if path.suffix.lower() in SUPPORTED_IMAGE_EXTS
            )
        if textbook_text_file is not None and textbook_text_file.exists():
            entry.textbook_text_file = textbook_text_file
            entry.textbook_image_files = textbook_images
            if entry.title == "教材重点":
                entry.title = infer_textbook_chapter_title(textbook_text_file, chapter) or entry.title


def preflight(cfg: SpecConfig, assets: Dict[int, ChapterAssets]) -> None:
    if (cfg.slides_dir is None or not cfg.slides_dir.exists()) and (
        cfg.textbook_pdf is None or not cfg.textbook_pdf.exists()
    ):
        raise FileNotFoundError("Either slides_dir or textbook_pdf must exist")
    if cfg.question_source == "exercises" and (cfg.exercises_dir is None or not cfg.exercises_dir.exists()):
        raise FileNotFoundError("exercises_dir is missing or does not exist for exercises mode")
    if cfg.textbook_pdf and not cfg.textbook_pdf.exists():
        cfg.warnings.append(f"Textbook PDF not found: {cfg.textbook_pdf}")
        cfg.textbook_pdf = None
    if cfg.reference_format and not cfg.reference_format.exists():
        cfg.warnings.append(f"Reference format not found, fallback to default structure: {cfg.reference_format}")
        cfg.reference_format = None
    if cfg.keypoints_path and not cfg.keypoints_path.exists():
        cfg.warnings.append(f"Keypoints file not found: {cfg.keypoints_path}")
        cfg.keypoints_path = None
    for chapter in cfg.chapter_numbers:
        entry = assets.get(chapter)
        if entry is None:
            cfg.warnings.append(f"Chapter {chapter} is in range but no PPT or exercise file was found.")
            continue
        if entry.ppt_file is None and cfg.textbook_pdf is None:
            cfg.warnings.append(f"Chapter {chapter} is missing PPT source.")
        if cfg.question_source == "keypoints" and entry.ppt_file is None and cfg.textbook_pdf is None:
            cfg.warnings.append(f"Chapter {chapter} has no PPT source and no textbook PDF source.")
        if cfg.question_source == "exercises" and entry.exercise_file is None:
            cfg.warnings.append(f"Chapter {chapter} is missing exercise source.")


def read_ppt_slides(path: Optional[Path]) -> List[Tuple[int, str]]:
    if path is None or not path.exists():
        return []
    text = path.read_text(encoding="utf-8")
    parts = re.split(r"--- Slide \d+ ---\s*", text)
    return [(idx, part.strip()) for idx, part in enumerate(parts[1:], 1) if part.strip()]


def chapter_markers(chapter: int) -> List[str]:
    markers = [f"第{chapter}章", f"第 {chapter} 章"]
    for label, value in CHINESE_NUMERAL.items():
        if value == chapter:
            markers.extend([f"第{label}章", f"第 {label} 章"])
            break
    return markers


def read_textbook_pages(path: Optional[Path]) -> List[Tuple[int, str]]:
    if path is None or not path.exists():
        return []
    text = path.read_text(encoding="utf-8")
    parts = re.split(r"--- Page (\d+) ---\s*", text)
    if len(parts) <= 1:
        return [(1, text.strip())] if text.strip() else []
    pages: List[Tuple[int, str]] = []
    for idx in range(1, len(parts), 2):
        page_no = int(parts[idx])
        page_text = parts[idx + 1].strip()
        if page_text:
            pages.append((page_no, page_text))
    return pages


def page_has_marker(page_text: str, markers: Sequence[str]) -> bool:
    compact = re.sub(r"\s+", "", page_text)
    return any(re.sub(r"\s+", "", marker) in compact for marker in markers)


def textbook_chapter_pages(path: Optional[Path], chapter: int) -> List[Tuple[int, str]]:
    pages = read_textbook_pages(path)
    if not pages:
        return []
    current_markers = chapter_markers(chapter)
    next_markers = chapter_markers(chapter + 1)
    selected: List[Tuple[int, str]] = []
    started = False
    for page_no, page_text in pages:
        if not started and page_has_marker(page_text, current_markers):
            started = True
        if started and selected and page_has_marker(page_text, next_markers):
            break
        if started:
            selected.append((page_no, page_text))
    return selected or pages


def infer_textbook_chapter_title(path: Optional[Path], chapter: int) -> Optional[str]:
    for _page_no, page_text in textbook_chapter_pages(path, chapter)[:3]:
        for line in page_text.splitlines():
            compact = re.sub(r"\s+", "", line)
            for marker in chapter_markers(chapter):
                compact_marker = re.sub(r"\s+", "", marker)
                if compact_marker not in compact:
                    continue
                tail = compact.split(compact_marker, 1)[-1].strip(" 　.·-")
                if 2 <= len(tail) <= 24 and not tail.isdigit():
                    return tail
    return None


def parse_question_segments(text: str) -> List[QuestionSegment]:
    """
    Parse question segments from exercise text.
    Supports two formats:
    1. Explicit markers: "问题1." or "题目1、" or "第1题"
    2. Implicit format: lines with question keywords (什么/如何/列举/说明/阐述) are questions
    """
    segments: List[QuestionSegment] = []
    lines = text.splitlines()

    # Try explicit marker pattern first
    explicit_pattern = re.compile(r"^(?:问题|题目|第?)(\d+)[、.。:：]\s*(.+)", re.IGNORECASE)
    current_segment: Optional[QuestionSegment] = None
    found_explicit = False

    for idx, line in enumerate(lines, 1):
        stripped = line.strip()
        if not stripped:
            if current_segment is not None:
                current_segment.body += "\n"
            continue
        match = explicit_pattern.match(stripped)
        if match:
            found_explicit = True
            if current_segment is not None:
                current_segment.end_line = idx - 1
                segments.append(current_segment)
            question_index = int(match.group(1))
            prompt = match.group(2).strip()
            current_segment = QuestionSegment(index=question_index, prompt=prompt, body="", start_line=idx)
        elif current_segment is not None:
            current_segment.body += line + "\n"

    if current_segment is not None:
        current_segment.end_line = len(lines)
        segments.append(current_segment)

    # If explicit markers found, return them
    if found_explicit and segments:
        for segment in segments:
            segment.body = segment.body.strip()
        return segments

    # Otherwise, use implicit format: identify questions by keywords
    QUESTION_KEYWORDS = ('什么', '如何', '列举', '说明', '阐述', '举例', '简述', '描述', '分别', '区别', '联系', '主要包含', '包含哪')
    question_num = 0
    current_segment = None
    skip_header = True

    for idx, line in enumerate(lines, 1):
        stripped = line.strip()
        if not stripped:
            continue

        # Skip header lines (title, reminder)
        if skip_header and any(kw in stripped for kw in ('提醒', '参考', '答案仅', '章节')):
            continue
        skip_header = False

        # Check if this is a question line
        is_question = any(kw in stripped for kw in QUESTION_KEYWORDS) and len(stripped) > 15

        if is_question:
            # Save previous segment
            if current_segment is not None:
                current_segment.end_line = idx - 1
                segments.append(current_segment)

            # Start new segment
            question_num += 1
            current_segment = QuestionSegment(
                index=question_num,
                prompt=stripped,
                body="",
                start_line=idx
            )
        elif current_segment is not None:
            # Append to current answer body
            current_segment.body += stripped + "\n"

    # Save last segment
    if current_segment is not None:
        current_segment.end_line = len(lines)
        segments.append(current_segment)

    for segment in segments:
        segment.body = segment.body.strip()

    return segments


def keywords(text: str, max_count: int = 10) -> List[str]:
    cleaned = re.sub(r"[^一-龥a-zA-Z0-9]+", " ", text)
    tokens = cleaned.split()
    freq: Dict[str, int] = {}
    for token in tokens:
        if len(token) < 2 or token in STOP_TOKENS:
            continue
        freq[token] = freq.get(token, 0) + 1
    ranked = sorted(freq.items(), key=lambda x: x[1], reverse=True)
    return [token for token, _ in ranked[:max_count]]


def slide_score(query_keywords: List[str], slide_text: str) -> float:
    slide_lower = slide_text.lower()
    matches = sum(1 for kw in query_keywords if kw.lower() in slide_lower)
    return matches / len(query_keywords) if query_keywords else 0.0


def pick_slide_matches(query: str, slides: List[Tuple[int, str]], max_matches: int = 3, threshold: float = 0.2) -> List[Tuple[int, str]]:
    query_kw = keywords(query, max_count=10)
    scored = [(slide_no, text, slide_score(query_kw, text)) for slide_no, text in slides]
    scored = [(slide_no, text, score) for slide_no, text, score in scored if score >= threshold]
    scored.sort(key=lambda x: x[2], reverse=True)
    return [(slide_no, text) for slide_no, text, _score in scored[:max_matches]]


def pick_textbook_matches(query: str, pages: List[Tuple[int, str]], max_matches: int = 3, threshold: float = 0.15) -> List[Tuple[int, str]]:
    query_kw = keywords(query, max_count=10)
    scored = [(page_no, text, slide_score(query_kw, text)) for page_no, text in pages]
    scored = [(page_no, text, score) for page_no, text, score in scored if score >= threshold]
    scored.sort(key=lambda x: x[2], reverse=True)
    return [(page_no, text) for page_no, text, _score in scored[:max_matches]]


def split_ppt_into_readable_lines(text: str) -> List[str]:
    segment = text.strip()
    segment = re.sub(r"(?<!^)(?=(?:（\d+）|[A-D]、|[一二三四五六七八九十]+、|\d+[、.]|[A-Za-z]\.))", "\n", segment)
    lines = segment.splitlines()
    return [line.strip() for line in lines if line.strip()]


def format_ppt_supplement(matches: List[Tuple[int, str]], style: StyleConfig, max_lines: int = 200) -> str:
    if not matches:
        return ""
    lines = []
    total_lines = 0
    for slide_no, text in matches:
        lines.append(f"> **{style.supplement_title}（Slide {slide_no}）：**")
        ppt_lines = split_ppt_into_readable_lines(text)
        for ppt_line in ppt_lines:
            if total_lines >= max_lines:
                lines.append("> [截断：PPT内容过长]")
                return "\n".join(lines)
            lines.append(f"> - {ppt_line}")
            total_lines += 1
        lines.append(">")
    return "\n".join(lines)


def format_textbook_supplement(matches: List[Tuple[int, str]], max_chars: int = 600) -> str:
    if not matches:
        return ""
    lines = ["> **教材整理：**"]
    for page_no, text in matches:
        excerpt = text[:max_chars].strip()
        if len(text) > max_chars:
            excerpt += "..."
        lines.append(f"> - p.{page_no} {excerpt}")
        lines.append(">")
    return "\n".join(lines)


def render_question(segment: QuestionSegment, assets: ChapterAssets, cfg: SpecConfig, style: StyleConfig) -> List[str]:
    lines = [f"{style.question_heading} {segment.index}. {segment.prompt}", ""]
    if segment.body.strip():
        lines.extend([segment.body.strip(), ""])
    else:
        lines.extend(["[课后习题文件中未提取到答案内容]", ""])
    query = segment.prompt + " " + segment.body[:200]
    ppt_matches = pick_slide_matches(query, read_ppt_slides(assets.ppt_text_file), max_matches=3)
    if ppt_matches:
        lines.extend([format_ppt_supplement(ppt_matches, style), ""])
    has_diagram_keyword = any(term in segment.prompt for term in DIAGRAM_TERMS)
    if cfg.include_images and has_diagram_keyword and assets.exercise_image_files:
        lines.extend(["", f"{style.section_heading} {style.image_section_title}", ""])
        for img_path in assets.exercise_image_files:
            rel_path = f"images/{img_path.name}"
            lines.append(f"![{style.image_caption_prefix}]({rel_path})")
            lines.append("")
    return lines


def render_keypoint_sections(assets: ChapterAssets, cfg: SpecConfig, style: StyleConfig) -> List[str]:
    lines = [f"{style.section_heading} 重点概念", ""]
    focus_points = assets.focus_points or []
    ppt_slides = read_ppt_slides(assets.ppt_text_file)
    textbook_pages = textbook_chapter_pages(assets.textbook_text_file, assets.chapter)
    used = 0
    for idx, focus in enumerate(focus_points, 1):
        lines.extend([f"{style.question_heading} 重点{idx}. {focus}", ""])
        matches = pick_slide_matches(focus, ppt_slides, max_matches=2)
        if matches:
            lines.extend([format_ppt_supplement(matches, style), ""])
        textbook_matches = pick_textbook_matches(focus, textbook_pages, max_matches=2)
        if textbook_matches:
            lines.extend([format_textbook_supplement(textbook_matches), ""])
        used += 1
    if textbook_pages and len(textbook_pages) > 0:
        for page_no, page_text in textbook_pages[:5]:
            excerpt = page_text[:400].strip()
            if len(excerpt) < 50:
                continue
            if len(page_text) > 400:
                excerpt += "..."
            lines.extend([f"{style.question_heading} 重点{used + 1}. 教材 p.{page_no}", "", excerpt, ""])
            used += 1
            if used >= 10:
                break
    if cfg.include_images and assets.ppt_image_files:
        for img_path in assets.ppt_image_files[:5]:
            title = img_path.stem.split("_")[-1]
            if title in {f"{assets.chapter}章{assets.title}", "目录", "CONTENTS"}:
                continue
            if any(term in title for term in DIAGRAM_TERMS):
                rel_path = f"images/{img_path.name}"
                lines.extend([f"{style.question_heading} 重点{used + 1}. {title}", "", f"![{style.image_caption_prefix}]({rel_path})", ""])
                used += 1
                if used >= 15:
                    break
    if used == 0:
        lines.extend(["[课件中未提取到可用的重点概念内容]", ""])
    return lines


def render_analysis_section(keywords_list: List[str], assets: ChapterAssets, cfg: SpecConfig, style: StyleConfig) -> List[str]:
    if not keywords_list:
        return []
    lines = [f"{style.section_heading} 分析题", ""]
    ppt_slides = read_ppt_slides(assets.ppt_text_file)
    for keyword in keywords_list:
        lines.extend([f"{style.question_heading} {keyword}", ""])
        matches = pick_slide_matches(keyword, ppt_slides, max_matches=2, threshold=0.1)
        if matches:
            lines.extend([format_ppt_supplement(matches, style), ""])
        else:
            lines.extend(["[PPT中未找到对应内容]", ""])
        if cfg.include_images:
            found_images = [img for img in assets.ppt_image_files if keyword in img.stem]
            for img_path in found_images[:2]:
                rel_path = f"images/{img_path.name}"
                lines.append(f"![{style.image_caption_prefix}]({rel_path})")
                lines.append("")
    return lines


def build_chapter_file(assets: ChapterAssets, cfg: SpecConfig, style: StyleConfig) -> None:
    lines = [
        f"# 第{assets.chapter}章 {assets.title}",
        "",
    ]
    question_numbers = cfg.chapter_question_map.get(assets.chapter, [])
    analysis_keywords_list = cfg.analysis_keywords.get(assets.chapter, [])
    if cfg.question_source == "exercises" and question_numbers:
        if assets.exercise_text_file and assets.exercise_text_file.exists():
            text = assets.exercise_text_file.read_text(encoding="utf-8")
            segments = parse_question_segments(text)
            segment_map = {seg.index: seg for seg in segments}
            lines.extend([f"{style.section_heading} 问答", ""])
            for qnum in question_numbers:
                segment = segment_map.get(qnum)
                if segment is None:
                    lines.extend([f"{style.question_heading} {qnum}. [未找到]", "", "[题目未提取到]", ""])
                    continue
                lines.extend(render_question(segment, assets, cfg, style))
        else:
            lines.extend([f"{style.section_heading} 问答", "", "[课后习题文件缺失]", ""])
        if analysis_keywords_list:
            lines.extend(render_analysis_section(analysis_keywords_list, assets, cfg, style))
    elif cfg.question_source == "keypoints":
        lines.extend(render_keypoint_sections(assets, cfg, style))
        if analysis_keywords_list:
            lines.extend(render_analysis_section(analysis_keywords_list, assets, cfg, style))
    else:
        lines.extend(["[本章未在考点映射中列出问答题号或分析题关键字，因此未展开复习正文。]", ""])
    out_path = cfg.output_dir / f"第{assets.chapter}章 {assets.title}.md"
    out_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"Generated: {out_path}")


def copy_images_to_output(assets: Dict[int, ChapterAssets], cfg: SpecConfig) -> None:
    if not cfg.include_images:
        return
    image_dir = cfg.output_dir / "images"
    image_dir.mkdir(parents=True, exist_ok=True)
    for entry in assets.values():
        for img_path in entry.ppt_image_files + entry.exercise_image_files + entry.textbook_image_files:
            if img_path.exists():
                shutil.copy(img_path, image_dir / img_path.name)


def build_overview(cfg: SpecConfig, assets: Dict[int, ChapterAssets]) -> None:
    if not cfg.generate_overview:
        return
    lines = ["# 复习提纲总览", ""]
    for chapter in sorted(cfg.chapter_numbers):
        entry = assets.get(chapter)
        if entry is None:
            lines.append(f"- 第{chapter}章 [未生成]")
            continue
        file_name = f"第{entry.chapter}章 {entry.title}.md"
        lines.append(f"- [第{entry.chapter}章 {entry.title}]({file_name})")
    overview_path = cfg.output_dir / "复习提纲总览.md"
    overview_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"Generated: {overview_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build Markdown review outlines from a spec file.")
    parser.add_argument("spec_path", type=Path, help="Path to the spec file")
    parser.add_argument("--output-dir", type=Path, help="Override output directory")
    parser.add_argument("--work-dir", type=Path, help="Working directory for extraction outputs")
    parser.add_argument("--refresh", action="store_true", help="Force re-extraction even if cached files exist")
    args = parser.parse_args()

    spec_path: Path = args.spec_path.resolve()
    if not spec_path.exists():
        print(f"Error: Spec file not found: {spec_path}", file=sys.stderr)
        sys.exit(1)

    cfg = parse_spec(spec_path, args.output_dir)
    work_dir = args.work_dir or spec_path.parent / ".work"
    work_dir.mkdir(parents=True, exist_ok=True)

    assets = scan_assets(cfg)
    preflight(cfg, assets)
    if cfg.warnings:
        print("[Warnings]")
        for warning in cfg.warnings:
            print(f"  - {warning}")

    ensure_extracted(cfg, assets, work_dir, args.refresh)
    cfg.style = infer_style(cfg.reference_format)
    cfg.output_dir.mkdir(parents=True, exist_ok=True)

    for chapter in cfg.chapter_numbers:
        entry = assets.get(chapter)
        if entry is None:
            print(f"Skipping chapter {chapter}: no assets found")
            continue
        build_chapter_file(entry, cfg, cfg.style)

    copy_images_to_output(assets, cfg)
    build_overview(cfg, assets)
    print("\nAll done.")


if __name__ == "__main__":
    main()

