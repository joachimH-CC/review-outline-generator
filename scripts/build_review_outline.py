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
from typing import Dict, Iterable, List, Optional, Sequence, Tuple


SCRIPT_DIR = Path(__file__).resolve().parent
SUPPORTED_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp"}
DIAGRAM_TERMS = (
    "鐢ㄤ緥鍥?,
    "鐢ㄤ緥琛?,
    "椤哄簭鍥?,
    "娲诲姩鍥?,
    "鐘舵€佹満鍥?,
    "鐘舵€佽〃",
    "鏁版嵁娴佸浘",
    "绫诲浘",
    "瀹炰綋鍏崇郴妯″瀷",
    "涓氬姟鏁版嵁鍥?,
    "缁勭粐缁撴瀯鍥?,
    "瑙掕壊鏉冮檺鐭╅樀",
    "鏁版嵁瀛楀吀",
    "鏁版嵁瀛楀吀琛?,
)
STOP_TOKENS = {
    "浠€涔?,
    "鍝簺",
    "濡備綍",
    "涓轰粈涔?,
    "浠ュ強",
    "涓€涓?,
    "杩涜",
    "鍙互",
    "绯荤粺",
    "闇€姹?,
    "鐢ㄦ埛",
    "浣跨敤",
    "鍒涘缓",
    "鎻忚堪",
    "鍖呮嫭",
    "搴旇",
    "鍏朵腑",
    "鍒嗗埆",
    "璇存槑",
    "涓句緥",
    "鏈珷",
    "鐩稿叧",
    "鏃跺€?,
    "杩樻湁",
    "涓昏",
    "绠＄悊",
    "妯″瀷",
    "鍥句腑",
    "杞欢",
    "璇剧▼",
    "娴佺▼",
    "鏁版嵁",
    "瀵硅薄",
    "绫诲瀷",
    "鏂规硶",
    "鍥捐〃",
    "淇℃伅",
    "鍔熻兘",
    "濡傛灉",
    "閫氳繃",
    "闇€瑕?,
    "椤圭洰",
    "鍐呭",
    "鐢ㄦ埛鏁呬簨",
    "鍥句功棣?,
    "鍦ㄧ嚎",
    "搴旂敤绋嬪簭",
    "绯荤粺涓?,
}
CHINESE_NUMERAL = {
    "涓€": 1,
    "浜?: 2,
    "涓?: 3,
    "鍥?: 4,
    "浜?: 5,
    "鍏?: 6,
    "涓?: 7,
    "鍏?: 8,
    "涔?: 9,
    "鍗?: 10,
    "鍗佷竴": 11,
    "鍗佷簩": 12,
    "鍗佷笁": 13,
    "鍗佸洓": 14,
    "鍗佷簲": 15,
    "鍗佸叚": 16,
    "鍗佷竷": 17,
    "鍗佸叓": 18,
    "鍗佷節": 19,
    "浜屽崄": 20,
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
    question_heading: str = "######"
    supplement_title: str = "PPT琛ュ厖"
    image_section_title: str = "鐩稿叧鍥剧ず"
    image_caption_prefix: str = "鍥?


@dataclass
class SpecConfig:
    spec_path: Path
    output_dir: Path
    slides_dir: Optional[Path] = None
    slides_format: str = "pptx"  # "pptx", "pdf", or "auto" (detect from first matching file)
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
    raw = raw.strip().strip('"').strip("'")
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
    pieces = re.split(r"[锛?銆?锛?]+", cleaned)
    return [piece.strip().strip('"').strip("'") for piece in pieces if piece.strip().strip('"').strip("'")]


def chapter_label_to_int(label: str) -> Optional[int]:
    match = re.search(r"绗琝s*([涓€浜屼笁鍥涗簲鍏竷鍏節鍗?-9]+)\s*绔?, label)
    if not match:
        match = re.search(r"^([0-9]+)\s*[銆?锛嶿", label)
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
    pieces = re.split(r"[锛?銆?\s]+", text.strip())
    return [piece for piece in pieces if piece and piece not in {"鐪嬫弿杩拌〃杈?, "鏂囧瓧涓€鐢诲浘", "渚嬪瓙涓€琛ヨ〃"}]


def parse_keypoints_file(path: Path) -> Tuple[Dict[int, List[int]], Dict[int, List[str]]]:
    question_map: Dict[int, List[int]] = {}
    analysis_map: Dict[int, List[str]] = {}
    mode = ""
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line:
            continue
        if "闂瓟" in line:
            mode = "question"
            continue
        if "鍒嗘瀽棰? in line:
            mode = "analysis"
            continue
        if mode == "question" and line.startswith("-"):
            chapter = chapter_label_to_int(line)
            if chapter is None:
                continue
            number_text = line.split(maxsplit=1)[-1]
            question_map[chapter] = parse_number_list(number_text)
        elif mode == "analysis" and "绗? in line:
            chapter = chapter_label_to_int(line)
            if chapter is None:
                continue
            keywords = split_analysis_keywords(re.sub(r"^绗琜涓€浜屼笁鍥涗簲鍏竷鍏節鍗?-9]+绔?, "", line).strip())
            if keywords:
                analysis_map[chapter] = keywords
    return question_map, analysis_map


def parse_natural_focus_map(text: str) -> Dict[int, List[str]]:
    focus_map: Dict[int, List[str]] = {}
    for raw in text.splitlines():
        line = raw.strip().lstrip("-* ")
        if not line or "绗? not in line:
            continue
        chapter = chapter_label_to_int(line)
        if chapter is None:
            continue
        if not any(token in line for token in ("閲嶇偣", "鑰冪偣", "鐭ヨ瘑鐐?, "澶嶄範鐐?)):
            continue
        if "锛? in line:
            _, rest = line.split("锛?, 1)
        elif ":" in line:
            _, rest = line.split(":", 1)
        else:
            rest = re.sub(r"^绗琜涓€浜屼笁鍥涗簲鍏竷鍏節鍗?-9]+\s*绔?, "", line)
            rest = re.sub(r"^(閲嶇偣|鑰冪偣|鐭ヨ瘑鐐箌澶嶄範鐐?", "", rest).strip()
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
                cfg.slides_format = value.strip().strip('\"').strip('"')
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
    link_pattern = re.compile(r"\[[^\]]+\]\(([^)]+)\)|\[[^\]]+\]\(\"([^\"]+)\"\)")
    for match in link_pattern.finditer(text):
        raw = match.group(1) or match.group(2)
        resolved = normalize_path(raw, spec_path.parent)
        lower_name = resolved.name.lower()
        if resolved.is_dir() and resolved.name == "ppt":
            cfg.slides_dir = resolved
        elif resolved.is_dir() and "璇惧悗涔犻" in resolved.name:
            cfg.exercises_dir = resolved
        elif resolved.suffix.lower() == ".md" and "鑰冪偣" in resolved.name:
            cfg.keypoints_path = resolved
        elif resolved.suffix.lower() == ".pdf":
            cfg.textbook_pdf = resolved
        elif resolved.suffix.lower() == ".md" and resolved != spec_path:
            cfg.reference_format = resolved

    for raw in re.findall(r"(?:[A-Za-z]:\\|\.{1,2}\\)?[^\s\"<>|]+?\.pdf", text):
        candidate = normalize_path(raw, spec_path.parent)
        if candidate.exists():
            cfg.textbook_pdf = candidate

    range_match = re.search(r"(\d+)\s*-\s*(\d+)绔?, text)
    if range_match:
        cfg.chapter_numbers = list(range(int(range_match.group(1)), int(range_match.group(2)) + 1))
    else:
        explicit_line = None
        for raw_line in text.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            if any(token in line for token in ("鏈€鍚庣殑鐢熸垚缁撴灉", "鍏?, "绗?绔?, "绗琗绔?, "绗瑇绔?)):
                explicit_line = line
                break
        if explicit_line:
            explicit_range = re.search(r"(\d+)\s*-\s*(\d+)", explicit_line)
            if explicit_range:
                cfg.chapter_numbers = list(range(int(explicit_range.group(1)), int(explicit_range.group(2)) + 1))

    if "涓嶈鑷繁鐢熸垚" in text or "涓ユ牸鏍规嵁" in text:
        cfg.include_images = True
    if "娌℃湁璇惧悗涔犻" in text or "鏃犺鍚庝範棰? in text or "娌℃湁涔犻" in text:
        cfg.question_source = "keypoints"

    cfg.chapter_focus_map = parse_natural_focus_map(text)
    if cfg.chapter_focus_map and not cfg.chapter_numbers:
        cfg.chapter_numbers = sorted(cfg.chapter_focus_map)

    return cfg


def parse_spec(spec_path: Path, output_dir: Optional[Path]) -> SpecConfig:
    text = spec_path.read_text(encoding="utf-8")
    cfg = parse_template_spec(spec_path, text) or parse_natural_spec(spec_path, text)
    explicit_range = re.search(r"(?<!\d)(\d+)\s*-\s*(\d+)\s*绔?, text)
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
        if re.match(r"^#+\s+\{棰樺瀷鏍囩\}", stripped):
            level = len(stripped) - len(stripped.lstrip("#"))
            style.section_heading = "#" * level
            continue
        if re.match(r"^#+\s+\{棰樺彿\}", stripped):
            level = len(stripped) - len(stripped.lstrip("#"))
            style.question_heading = "#" * level
            continue
        supplement_match = re.match(r"^>\s+\*\*(.+?)锛歕*\*", stripped)
        if supplement_match:
            style.supplement_title = supplement_match.group(1).strip()
            continue
        if re.match(r"^\*鍥綷{?.+\*?$", stripped) or stripped.startswith("*鍥?):
            style.image_caption_prefix = "鍥?
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
            match = re.search(r"绗琝s*(\d+)\s*绔燶s*(.+)\.pptx$", path.name)
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
            title = assets.get(chapter).title if chapter in assets else f"绗瑊chapter}绔?
            assets.setdefault(chapter, ChapterAssets(chapter=chapter, title=title)).exercise_file = path
    if cfg.textbook_pdf:
        for chapter in cfg.chapter_numbers:
            assets.setdefault(chapter, ChapterAssets(chapter=chapter, title="鏁欐潗閲嶇偣"))
    for chapter, focus_points in cfg.chapter_focus_map.items():
        entry = assets.setdefault(chapter, ChapterAssets(chapter=chapter, title="鏁欐潗閲嶇偣"))
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
            if entry.title == "鏁欐潗閲嶇偣":
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
    markers = [f"绗瑊chapter}绔?, f"绗?{chapter} 绔?]
    for label, value in CHINESE_NUMERAL.items():
        if value == chapter:
            markers.extend([f"绗瑊label}绔?, f"绗?{label} 绔?])
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
                tail = compact.split(compact_marker, 1)[-1].strip(" 锛?.-")
                if 2 <= len(tail) <= 24 and not tail.isdigit():
                    return tail
    return None


def normalize_block(text: str) -> str:
    cleaned: List[str] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            if cleaned and cleaned[-1] != "":
                cleaned.append("")
            continue
        cleaned.append(line)
    while cleaned and cleaned[-1] == "":
        cleaned.pop()
    return "\n".join(cleaned)


def alpha_label(index: int) -> str:
    return chr(ord("A") + index - 1) + "."


def format_answer_body(text: str) -> str:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return ""

    output: List[str] = []
    idx = 0
    while idx < len(lines):
        line = lines[idx]
        if re.fullmatch(r"锛圽d+锛?, line) and idx + 1 < len(lines):
            output.append(f"{line}{lines[idx + 1]}")
            idx += 2
            continue
        if re.fullmatch(r"[A-Z]\.", line) and idx + 1 < len(lines):
            output.append(f"{line}{lines[idx + 1]}")
            idx += 2
            continue
        output.append(line)
        idx += 1

    return "\n".join(output)


def is_caption_line(line: str) -> bool:
    return bool(re.match(r"^(鍥緗琛▅\[Table)", line))


def is_question_line(line: str) -> bool:
    if not line or line.startswith("鎻愰啋锛?) or is_caption_line(line) or line.startswith("|"):
        return False
    if re.match(r"^锛圽d+锛?, line):
        return False
    if line.endswith("锛?) or line.endswith("?"):
        return True
    if ("锛? in line or "?" in line) and "鈥? not in line and "鈥? not in line and "锛? not in line:
        return True
    if re.match(r"^(璇穦鎬濊€億鍒椾妇|绠€杩皘灏濊瘯|鎵撳紑|鏌ョ湅|鍘诲畼缃戜笅杞絴鏍规嵁|閫夋嫨涓€绉峾涓句緥璇存槑|闃愯堪|鍐欎笅|浠€涔堟槸|涓轰粈涔堟湁浜唡鍝簺椤圭洰|鍝簺绯荤粺|闄や簡鍙互浠巪瀹㈡埛鍦ㄦ弿杩?", line):
        return True
    if re.match(r"^涓?+(鍒涘缓|璁捐|缁樺埗|鎻忚堪|璁板綍)", line):
        return True
    if re.match(r"^(鍙傝€冭〃|鎸戦€変範棰榺鍒嗗埆浣跨敤)", line):
        return True
    if line.startswith("浣跨敤") and any(token in line for token in ("妯℃澘", "鏂规硶", "鏈珷")):
        return True
    if any(token in line for token in ("璇疯嚦灏?, "璇风畝杩?, "璇蜂粠", "璇风粯鍒?, "璇蜂妇渚?)):
        return True
    if line.startswith("鍦ㄥ") and "濡備綍" in line:
        return True
    return False


def parse_question_segments(path: Optional[Path]) -> List[QuestionSegment]:
    if path is None or not path.exists():
        return []
    lines = [line.strip() for line in path.read_text(encoding="utf-8").splitlines()]
    lines = [line for line in lines if line]
    if len(lines) <= 2:
        return []
    body_lines = lines[2:]
    questions: List[QuestionSegment] = []
    current_prompt = ""
    current_body: List[str] = []
    current_start = 0
    index = 0
    for line_idx, line in enumerate(body_lines):
        if is_question_line(line):
            if current_prompt:
                questions.append(
                    QuestionSegment(
                        index=index,
                        prompt=current_prompt,
                        body=normalize_block("\n".join(current_body)),
                        start_line=current_start,
                        end_line=line_idx - 1,
                    )
                )
            index += 1
            current_prompt = line
            current_body = []
            current_start = line_idx
            continue
        if current_prompt:
            current_body.append(line)
    if current_prompt:
        questions.append(
            QuestionSegment(
                index=index,
                prompt=current_prompt,
                body=normalize_block("\n".join(current_body)),
                start_line=current_start,
                end_line=len(body_lines) - 1,
            )
        )
    return questions


def keywords(text: str) -> List[str]:
    text = re.sub(r"[锛屻€傦紱锛氥€侊紙锛?)\[\]\"鈥溾€濃€樷€橽s]+", " ", text)
    pieces = []
    for token in text.split():
        token = re.sub(r"^(绠€杩皘鍒椾妇|璇穦灏濊瘯|鎬濊€億浣跨敤|鍋囪|鎵撳紑|鏌ョ湅|鍒涘缓|鏍规嵁|閫夋嫨涓€绉峾涓轰簡|濡傛灉|瀵逛簬|鍦ㄥ)", "", token)
        token = re.sub(r"(涔嬮棿|鏂归潰|杩涜|杩囩▼|搴旂敤绋嬪簭|绯荤粺)$", "", token)
        pieces.extend(
            part
            for part in re.split(r"(?:鍜寍涓巪鍙妡鎴東鐨剕骞秥浠巪涓瓅瀵箌鍦▅鏃?", token)
            if len(part) >= 2
        )
    tokens = set()
    for piece in pieces:
        if piece in STOP_TOKENS:
            continue
        if re.fullmatch(r"[A-Za-z0-9]{1,2}", piece):
            continue
        tokens.add(piece[:12])
    return sorted(tokens)


def focus_query_keywords(text: str) -> List[str]:
    terms = keywords(text)
    compact = re.sub(r"\s+", "", text)
    if re.search(r"[\u4e00-\u9fff]", compact):
        for size in (4, 3, 2):
            if len(compact) < size:
                continue
            for idx in range(0, len(compact) - size + 1):
                term = compact[idx : idx + size]
                if term in STOP_TOKENS or re.fullmatch(r"\d+", term):
                    continue
                terms.append(term)
    seen: List[str] = []
    for term in terms:
        if term and term not in seen:
            seen.append(term)
    return seen


def slide_score(slide_text: str, query_keywords: Sequence[str]) -> Tuple[int, int]:
    total = 0
    distinct = 0
    for keyword in query_keywords:
        count = slide_text.count(keyword)
        if count:
            distinct += 1
            total += min(count, 3)
    return total, distinct


def format_slide_excerpt(text: str) -> List[str]:
    raw_lines = [line.strip() for line in text.splitlines() if line.strip()]
    formatted: List[str] = []
    for raw in raw_lines:
        queue = [segment.strip() for segment in re.split(r"[锛?]+", raw) if segment.strip()]
        if not queue:
            continue
        pieces: List[str] = []
        for segment in queue:
            segment = re.sub(r"(?<!^)(?=(?:锛圽d+锛墊[A-D]銆亅[涓€浜屼笁鍥涗簲鍏竷鍏節鍗乚+銆亅\d+[銆?]|[A-Za-z]\.))", "\n", segment)
            pieces.extend(part.strip() for part in segment.splitlines() if part.strip())
        formatted.extend(pieces)
    return formatted


def pick_slide_matches(slides: Sequence[Tuple[int, str]], query_text: str, limit: int = 2) -> List[Tuple[int, str]]:
    query_keywords = keywords(query_text)
    if not query_keywords:
        return []
    candidates: List[Tuple[int, int, int, str]] = []
    for slide_idx, slide_text in slides:
        score, distinct = slide_score(slide_text, query_keywords)
        if distinct >= 2 or (distinct >= 1 and score >= 3):
            candidates.append((score, distinct, slide_idx, slide_text))
    candidates.sort(key=lambda item: (-item[0], -item[1], item[2]))
    return [(slide_idx, slide_text) for _, _, slide_idx, slide_text in candidates[:limit]]


def compact_textbook_line(line: str) -> str:
    line = re.sub(r"\s+", " ", line).strip()
    line = re.sub(r"^\d+\s*$", "", line).strip()
    return line


def textbook_units(path: Optional[Path], chapter: int) -> List[Tuple[int, str]]:
    units: List[Tuple[int, str]] = []
    for page_no, page_text in textbook_chapter_pages(path, chapter):
        paragraphs = re.split(r"\n\s*\n|(?<=銆?\s+", page_text)
        for paragraph in paragraphs:
            for raw in paragraph.splitlines():
                line = compact_textbook_line(raw)
                if len(line) < 6:
                    continue
                if re.fullmatch(r"绗?\s*\d+\s*椤?", line):
                    continue
                units.append((page_no, line))
    return units


def pick_textbook_matches(
    path: Optional[Path],
    chapter: int,
    query_text: str,
    limit: int = 5,
) -> List[Tuple[int, str]]:
    query_keywords = focus_query_keywords(query_text)
    cleaned_query = query_text.strip()
    if cleaned_query and cleaned_query not in query_keywords:
        query_keywords.append(cleaned_query)
    units = textbook_units(path, chapter)
    if not units:
        return []
    if not query_keywords:
        return units[:limit]
    candidates: List[Tuple[int, int, int, str]] = []
    for position, (page_no, unit) in enumerate(units):
        score, distinct = slide_score(unit, query_keywords)
        if distinct:
            candidates.append((score, distinct, position, f"p.{page_no} {unit}"))
    candidates.sort(key=lambda item: (-item[0], -item[1], item[2]))
    return [(int(re.search(r"p\.(\d+)", item[3]).group(1)), re.sub(r"^p\.\d+\s+", "", item[3])) for item in candidates[:limit]]


def render_slide_matches(matches: Sequence[Tuple[int, str]]) -> List[str]:
    if not matches:
        return []
    lines = ["> **PPT琛ュ厖锛?*"]
    for slide_idx, slide_text in matches:
        lines.append(f"> **Slide {slide_idx}**")
        for item in format_slide_excerpt(slide_text):
            lines.append(f"> - {item}")
    return lines


def render_style_slide_matches(style: StyleConfig, matches: Sequence[Tuple[int, str]]) -> List[str]:
    if not matches:
        return []
    lines = [f"> **{style.supplement_title}锛?*"]
    for slide_idx, slide_text in matches:
        lines.append(f"> **Slide {slide_idx}**")
        for item in format_slide_excerpt(slide_text):
            lines.append(f"> - {item}")
    return lines


def render_textbook_matches(matches: Sequence[Tuple[int, str]]) -> List[str]:
    if not matches:
        return ["> **鏁欐潗鏁寸悊锛?* [鏁欐潗PDF涓湭鎵惧埌楂樺害瀵瑰簲鐨勬憳褰昡"]
    lines = ["> **鏁欐潗鏁寸悊锛?*"]
    for page_no, text in matches:
        excerpt = text if len(text) <= 180 else text[:177].rstrip() + "..."
        lines.append(f"> - p.{page_no} {excerpt}")
    return lines


def is_explicit_diagram_text(text: str) -> bool:
    return any(term in text for term in DIAGRAM_TERMS)


def collect_caption_occurrences(path: Optional[Path]) -> List[Tuple[int, str]]:
    if path is None or not path.exists():
        return []
    lines = [line.strip() for line in path.read_text(encoding="utf-8").splitlines()]
    body_lines = [line for line in lines if line][2:]
    captions: List[Tuple[int, str]] = []
    for idx, line in enumerate(body_lines):
        if re.match(r"^鍥綷d+-\d+", line):
            captions.append((idx, line))
    return captions


def select_exercise_images_by_segment(
    assets: ChapterAssets,
    segment: QuestionSegment,
) -> List[Path]:
    captions = collect_caption_occurrences(assets.exercise_text_file)
    chosen: List[Path] = []
    for occ_idx, (line_idx, _caption) in enumerate(captions):
        if not (segment.start_line <= line_idx <= segment.end_line):
            continue
        if occ_idx < len(assets.exercise_image_files):
            image = assets.exercise_image_files[occ_idx]
            if image not in chosen:
                chosen.append(image)
    return chosen[:3]


def parse_slide_number(path: Path) -> Optional[int]:
    match = re.search(r"_slide(\d+)_", path.name)
    return int(match.group(1)) if match else None


def select_images(
    assets: ChapterAssets,
    segment: QuestionSegment,
    slide_matches: Sequence[Tuple[int, str]],
    explicit_diagram: bool,
) -> List[Path]:
    if not explicit_diagram:
        return []
    figure_images = select_exercise_images_by_segment(assets, segment)
    if figure_images:
        return figure_images
    slide_numbers = [slide_idx for slide_idx, _ in slide_matches]
    chosen: List[Path] = []
    if slide_numbers:
        by_slide: Dict[int, List[Path]] = {}
        for image in assets.ppt_image_files:
            slide_number = parse_slide_number(image)
            if slide_number is not None:
                by_slide.setdefault(slide_number, []).append(image)
        for slide_idx in slide_numbers:
            direct = by_slide.get(slide_idx, [])
            if direct:
                chosen.extend(direct[:2])
                continue
            nearest = sorted(
                (
                    (abs(candidate_slide - slide_idx), candidate_slide, paths)
                    for candidate_slide, paths in by_slide.items()
                ),
                key=lambda item: (item[0], item[1]),
            )
            if nearest:
                chosen.extend(nearest[0][2][:2])
        if chosen:
            seen = []
            for image in chosen:
                if image not in seen:
                    seen.append(image)
            return seen[:3]
    if assets.exercise_image_files:
        return assets.exercise_image_files[:3]
    return []


def copy_images(images: Sequence[Path], output_image_dir: Path, chapter: int, counter: List[int]) -> List[Tuple[str, str]]:
    copied: List[Tuple[str, str]] = []
    output_image_dir.mkdir(parents=True, exist_ok=True)
    for image in images:
        counter[0] += 1
        target_name = f"ch{chapter:02d}-{counter[0]:02d}{image.suffix.lower()}"
        target_path = output_image_dir / target_name
        shutil.copy2(image, target_path)
        copied.append((target_name, image.name))
    return copied


def render_images(
    style: StyleConfig,
    copied_images: Sequence[Tuple[str, str]],
    chapter: int,
) -> List[str]:
    if not copied_images:
        return []
    lines = ["", f"**{style.image_section_title}锛?*", ""]
    for idx, (filename, original_name) in enumerate(copied_images, 1):
        lines.append(f"![{style.image_caption_prefix}{chapter}-{idx}](images/{filename})")
        lines.append("")
        lines.append(f"*{style.image_caption_prefix}{chapter}-{idx} 鏉ユ簮锛歿original_name}*")
        lines.append("")
    return lines


def render_question(
    style: StyleConfig,
    question: QuestionSegment,
    assets: ChapterAssets,
    output_image_dir: Path,
    image_counter: List[int],
    include_images: bool = True,
) -> List[str]:
    slide_matches = pick_slide_matches(read_ppt_slides(assets.ppt_text_file), question.prompt)
    explicit_diagram = is_explicit_diagram_text(question.prompt) or is_explicit_diagram_text(question.body)
    selected_images = select_images(assets, question, slide_matches, include_images and explicit_diagram)
    copied = copy_images(selected_images, output_image_dir, assets.chapter, image_counter) if selected_images else []

    body = format_answer_body(question.body) or "[璇惧悗涔犻涓棰樻湭鎻愬彇鍒版鏂囧唴瀹筣"
    lines = [f"{style.question_heading} {question.index}. {question.prompt}", "", body]
    lines.extend(render_images(style, copied, assets.chapter))
    lines.append("")
    lines.extend(render_style_slide_matches(style, slide_matches))
    lines.append("")
    return lines


def render_keypoint_sections(
    style: StyleConfig,
    assets: ChapterAssets,
    output_image_dir: Path,
    image_counter: List[int],
) -> List[str]:
    slides = read_ppt_slides(assets.ppt_text_file)
    lines = [f"{style.section_heading} 閲嶇偣姒傚康", ""]
    if assets.focus_points:
        for idx, focus in enumerate(assets.focus_points, 1):
            lines.extend([f"{style.question_heading} 閲嶇偣{idx}. {focus}", ""])
            textbook_matches = pick_textbook_matches(assets.textbook_text_file, assets.chapter, focus)
            lines.extend(render_textbook_matches(textbook_matches))
            lines.append("")
            slide_matches = pick_slide_matches(slides, focus)
            if slide_matches:
                lines.extend(render_style_slide_matches(style, slide_matches))
                lines.append("")
        return lines

    used = 0
    if assets.textbook_text_file is not None and not slides:
        for page_no, text in textbook_units(assets.textbook_text_file, assets.chapter)[:8]:
            excerpt = text if len(text) <= 180 else text[:177].rstrip() + "..."
            lines.extend([f"{style.question_heading} 閲嶇偣{used + 1}. 鏁欐潗 p.{page_no}", "", excerpt, ""])
            used += 1
        if used:
            return lines

    for slide_idx, slide_text in slides:
        parts = [line.strip() for line in slide_text.splitlines() if line.strip()]
        if len(parts) < 2:
            continue
        title = parts[0]
        if title in {f"绗瑊assets.chapter}绔?{assets.title}", "鐩綍", "CONTENTS"}:
            continue
        body = "\n".join(f"- {item}" for item in format_slide_excerpt("\n".join(parts[1:])))
        if not body.strip():
            continue
        segment = QuestionSegment(index=used + 1, prompt=title, body=body)
        slide_matches = [(slide_idx, slide_text)]
        selected_images = select_images(assets, segment, slide_matches, is_explicit_diagram_text(slide_text))
        copied = copy_images(selected_images, output_image_dir, assets.chapter, image_counter) if selected_images else []
        lines.extend([f"{style.question_heading} 閲嶇偣{used + 1}. {title}", "", body])
        lines.extend(render_images(style, copied, assets.chapter))
        lines.append("")
        lines.extend(render_style_slide_matches(style, slide_matches))
        lines.append("")
        used += 1
        if used >= 6:
            break
    if used == 0:
        lines.extend(["[璇句欢涓湭鎻愬彇鍒板彲鐢ㄧ殑閲嶇偣姒傚康鍐呭]", ""])
    return lines


def match_analysis_segments(segments: Sequence[QuestionSegment], keywords_for_chapter: Sequence[str]) -> List[QuestionSegment]:
    if not keywords_for_chapter:
        return []
    matched: List[QuestionSegment] = []
    for segment in segments:
        body_lines = [line.strip() for line in segment.body.splitlines() if line.strip()]
        caption_text = "\n".join(line for line in body_lines if re.match(r"^[鍥捐〃]\d+-\d+", line))
        summary_text = "\n".join(body_lines[:5])
        text = "\n".join([segment.prompt, caption_text, summary_text])
        if any(keyword in text for keyword in keywords_for_chapter):
            matched.append(segment)
    return matched


def validate_requested_questions(
    cfg: SpecConfig,
    chapter: int,
    segments: Sequence[QuestionSegment],
) -> None:
    requested = cfg.chapter_question_map.get(chapter, [])
    total = len(segments)
    for number in requested:
        if number < 1 or number > total:
            cfg.warnings.append(
                f"Chapter {chapter}: requested question {number} is outside the extracted range 1-{total}."
            )


def build_chapter_file(
    cfg: SpecConfig,
    assets: ChapterAssets,
    output_image_dir: Path,
) -> Tuple[Path, int]:
    segments = parse_question_segments(assets.exercise_text_file)
    validate_requested_questions(cfg, assets.chapter, segments)
    image_counter = [0]
    style = cfg.style

    lines = [
        f"# 绗瑊assets.chapter}绔?{assets.title}",
        "",
        "> 鍐呭涓ユ牸鏁寸悊鑷彁渚涚殑璇句欢銆佽鍚庝範棰樸€佹暀鏉?PDF 涓庡叾瀵煎嚭鍥剧墖锛屼笉棰濆鎵╁啓璇剧▼鍐呭銆?,
        "",
    ]
    rendered_count = 0

    if cfg.question_source == "keypoints":
        keypoint_lines = render_keypoint_sections(style, assets, output_image_dir, image_counter)
        lines.extend(keypoint_lines)
        rendered_count = max(1, len(assets.focus_points))
        selected_questions: List[QuestionSegment] = []
        analysis_segments: List[QuestionSegment] = []
    else:
        selected_numbers = cfg.chapter_question_map.get(assets.chapter, [])
        selected_questions = [segment for segment in segments if segment.index in selected_numbers]
        if selected_questions:
            lines.extend([f"{style.section_heading} 闂瓟", ""])
            for segment in selected_questions:
                lines.extend(render_question(style, segment, assets, output_image_dir, image_counter, cfg.include_images))
            rendered_count += len(selected_questions)

        analysis_segments = match_analysis_segments(segments, cfg.analysis_keywords.get(assets.chapter, []))
        if analysis_segments:
            lines.extend([f"{style.section_heading} 鍒嗘瀽棰?, ""])
            for idx, segment in enumerate(analysis_segments, 1):
                slide_matches = pick_slide_matches(read_ppt_slides(assets.ppt_text_file), segment.prompt)
                selected_images = select_images(assets, segment, slide_matches, cfg.include_images)
                copied = copy_images(selected_images, output_image_dir, assets.chapter, image_counter) if selected_images else []
                body = format_answer_body(segment.body) or "[璇惧悗涔犻涓棰樻湭鎻愬彇鍒版鏂囧唴瀹筣"
                lines.extend([f"{style.question_heading} 鍒嗘瀽{idx}. {segment.prompt}", "", body])
                lines.extend(render_images(style, copied, assets.chapter))
                lines.append("")
                lines.extend(render_style_slide_matches(style, slide_matches))
                lines.append("")
            rendered_count += len(analysis_segments)

    if rendered_count == 0:
        lines.extend(
            [
                f"{style.section_heading} 璇存槑",
                "",
                "鏈珷鏈湪鑰冪偣鏄犲皠涓垪鍑洪棶绛旈鍙锋垨鍒嗘瀽棰樺叧閿瓧锛屽洜姝ゆ湭灞曞紑澶嶄範姝ｆ枃銆?,
                "",
            ]
        )

    out_path = cfg.output_dir / f"绗瑊assets.chapter}绔?{assets.title}.md"
    out_path.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")
    return out_path, rendered_count


def build_overview(cfg: SpecConfig, generated_files: Sequence[Path]) -> None:
    if not cfg.generate_overview:
        return
    lines = [
        "# 澶嶄範鎻愮翰鎬昏",
        "",
        f"- 璇存槑鏂囦欢锛歚{cfg.spec_path.name}`",
        f"- 杈撳嚭鐩綍锛歚{cfg.output_dir}`",
        "",
        "## 绔犺妭鏂囦欢",
        "",
    ]
    for file_path in generated_files:
        lines.append(f"- [{file_path.name}]({file_path.name})")
    if cfg.warnings:
        lines.extend(["", "## 棰勬涓庣敓鎴愭彁绀?, ""])
        for warning in cfg.warnings:
            lines.append(f"- {warning}")
    (cfg.output_dir / "澶嶄範鎻愮翰鎬昏.md").write_text("\n".join(lines).strip() + "\n", encoding="utf-8")


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("spec_path")
    parser.add_argument("--output-dir")
    parser.add_argument("--work-dir")
    parser.add_argument("--refresh", action="store_true")
    args = parser.parse_args(argv)

    spec_path = Path(args.spec_path).resolve()
    output_dir = Path(args.output_dir).resolve() if args.output_dir else None
    work_dir = Path(args.work_dir).resolve() if args.work_dir else spec_path.parent / "_review_outline_work"

    cfg = parse_spec(spec_path, output_dir)
    if cfg.slides_dir is None and cfg.textbook_pdf is None:
        raise FileNotFoundError("Spec parsing did not resolve slides_dir or textbook_pdf.")
    if cfg.question_source == "exercises" and cfg.exercises_dir is None:
        raise FileNotFoundError("Spec parsing did not resolve exercises_dir for exercises mode.")

    cfg.output_dir.mkdir(parents=True, exist_ok=True)
    default_reference = SCRIPT_DIR.parent / "output-examples" / "閫氱敤鍙傝€冩牸寮?md"
    cfg.style = infer_style(cfg.reference_format or default_reference)
    assets = scan_assets(cfg)
    preflight(cfg, assets)
    ensure_extracted(cfg, assets, work_dir, args.refresh)

    generated: List[Path] = []
    output_image_dir = cfg.output_dir / "images"
    for chapter in cfg.chapter_numbers:
        if chapter not in assets:
            continue
        out_path, used_count = build_chapter_file(cfg, assets[chapter], output_image_dir)
        generated.append(out_path)
        print(f"[build] {out_path.name}: {used_count} sections")

    build_overview(cfg, generated)
    if cfg.warnings:
        print("[build] warnings:")
        for warning in cfg.warnings:
            print(f"  - {warning}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

