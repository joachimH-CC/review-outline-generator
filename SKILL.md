---
name: review-outline-generator
description: Generate Markdown-based review outlines or chapter-focused study notes from local course materials such as PPT/PPTX, Word/DOCX, and PDF files. Use when the user wants exam review notes, final-review outlines, key-point summaries, or chapter-by-chapter Markdown study material based on provided course files, exercise sets, and an optional reference format. Best fit for requests such as "复习提纲", "期末复习", "考试重点整理", "根据课件整理复习资料", or "按章节生成 Markdown 复习笔记". Do not use for generic explanations, broad "章节总结" requests without source materials, or tasks that are not grounded in local course files.
---

# Review Outline Generator

Generate structured Markdown review material from user-provided course files. This skill is a workflow skill, not a fully automated pipeline:

- Use scripts to extract text and images from course files.
- Use the extracted material, user constraints, and the template to assemble the final Markdown.
- Keep the result grounded in the provided files unless the user explicitly allows web-based supplementation.

For Chinese readers, see `SKILL.zh-CN.md`.

## Scope

Best fit:

- Review outlines for a specific course
- Final-exam study notes built from local slides, handouts, and exercises
- Chapter-by-chapter Markdown revision notes
- Key-point notes generated from slides when exercises are unavailable
- Chapter-focused notes generated from a textbook PDF when exercises are unavailable and the user provides chapter numbers plus focus points

Do not use for:

- Generic topic tutoring without source files
- Free-form "summarize this subject" requests with no materials
- Fully automated grading, coverage scoring, or source-trace auditing

## Required Inputs

At minimum, the user must provide local course material files:

- Slides or reading material: `PPT/PPTX`, `PDF`, or `DOCX`

Optional but strongly preferred:

- Exercise files when the user wants question-oriented output
- A clear exam scope or chapter range
- Chapter focus points when there are no exercises and the output should come from a textbook PDF
- A reference format file when the user wants the output to resemble an existing Markdown layout

If the request is too broad, do not improvise a final outline. Either ask for the missing materials or switch to one of the supported downgrade paths below.

## Supported Modes

### Mode A: Spec-file driven

If the user provides a filled-in spec file based on `assets/general-template.md`, treat that file as the primary control surface.

Also accept a natural-language spec file when it still clearly points to:

- the keypoints file
- the slides directory
- the exercises directory
- the textbook PDF, when the no-exercise path uses a book rather than slides
- chapter focus points, when `question_source: "keypoints"` is driven by user-provided重点
- an optional reference format file
- the requested chapter range or output expectation

Read from it:

- subject name
- chapter range
- question source
- chapter-to-question mapping
- chapter-to-focus mapping
- diagram preference
- web enrichment preference
- output directory

Before generating anything, run a preflight check:

- verify the linked files and directories exist
- verify referenced sample files exist; if not, fall back explicitly to the default output format
- verify mapped question numbers are inside the extracted question range
- record warnings instead of silently guessing

### Mode B1: Conversational, with materials and scope

If the user does not provide a spec file but clearly provides:

- local course materials
- chapter range or exam scope

then extract the materials and proceed using the same logic as Mode A.

### Mode B2: Conversational, with materials but no scope

If the user provides materials but no clear exam scope:

- inspect the materials
- if web access is allowed, optionally draft a scope/template suggestion
- label every inferred item as `[联网推断，请确认]`
- show the draft to the user and wait for confirmation before generating the final outline

Use web inference only to prepare a draft scope or weighting suggestion. Do not mix inferred web content directly into the final answer body before user confirmation.

### Mode B3: Insufficient materials

If the user provides no usable course materials:

- do not generate the final outline
- output a missing-items list
- tell the user what files or fields are needed next

## Downgrade Paths

Only support these downgrade paths:

1. Slides or textbook PDF available, exercises unavailable

- Set or recommend `question_source: "keypoints"`
- Generate chapter-focused notes, definitions, diagram explanations, and source excerpts
- If the user provides chapter numbers and重点, use `chapter_focus_map` and the textbook PDF as the main source
- Do not present the result as a question-by-question exercise outline

2. Slides and exercises available, but no exam scope

- Draft a spec or scope template first
- Use web inference only for a confirmation draft if the user allows it
- Generate the final outline only after the user confirms the scope

Do not support "exercises only, no course materials" as a first-class path.

## `question_source` Semantics

Keep the existing config field, but treat the options differently:

- `exercises`
  Use this as the primary path when exercises and question mappings are available. Output is organized by question or question group.

- `keypoints`
  Use this as the no-exercises downgrade path. Output is organized by chapter concepts, user-provided focus points, definitions, tables, and diagram explanations from slides and/or a textbook PDF.

- `custom`
  Use this only when the user gives clear structural instructions in the custom notes section. Follow the requested structure only when it can still be grounded in the provided materials.

## Dynamic Analysis Chapter Detection

When a spec file or keypoints file contains both question mappings (问答) and analysis keywords (分析题), the skill MUST distinguish between them:

- Chapters listed under "问答" in the keypoints file → format as Q&A chapters using `question_source=exercises`
- Chapters listed under "分析题" in the keypoints file → format as analysis chapters using the detailed four-part structure (see Assembly Rules)
- Chapters appearing in both lists → include both sections

When only a `chapter_focus_map` is provided (keypoints mode), all chapters use the keypoints format.

When `analysis_keywords` are present but no separate question mapping exists for a chapter, include an analysis section in that chapter's output.

## `reference_format` Semantics

Treat `reference_format` as a style reference, not as a strict schema.

Use it to imitate:

- heading depth
- grouping style
- annotation style
- image placement
- table tone

Do not promise exact format reproduction or automated schema extraction from the reference file.

## Extraction Workflow

Use the bundled scripts when native extraction is not already available:

- `scripts/extract_pptx.py <pptx_dir> <text_dir> <image_dir>`
- `scripts/extract_docx.py <docx_dir> <text_dir> <image_dir>`
- `scripts/extract_pdf.py <pdf_file_or_dir> <text_dir> <image_dir>`
- `scripts/build_review_outline.py <spec_path> [--output-dir DIR] [--work-dir DIR] [--refresh]`

Use `scripts/screenshot.py` only as a manual Windows fallback when an image must be captured from the screen and structured extraction is not enough.

`build_review_outline.py` is the preferred deterministic path when the task matches this skill closely enough. It parses the spec, performs preflight checks, runs extraction, selects questions, formats PPT supplements, and writes the final Markdown files.

The extraction-only scripts provide raw text and image assets. They do not perform final matching, chapter assembly, or validation by themselves.

If a textbook PDF is scanned and has no extractable text, treat generated page images as a fallback asset. Do not pretend the PDF was semantically read; ask for OCR-capable extraction, page ranges, or permission for manual/vision-assisted extraction before producing the final outline.

## Assembly Rules

### General Rules

When assembling output:

- keep answers and notes grounded in the extracted material
- use course slides as the main supporting context
- use the textbook PDF as the main supporting context when the user supplies chapter numbers and重点 but exercises are unavailable
- use exercises when the output is question-oriented
- if a direct match is weak, say so instead of pretending certainty
- if useful slide context exists but does not directly answer the prompt, place it in a quoted supplement block
- preserve readable structure when a slide contains enumerations or parallel items
- preserve readable structure when textbook PDF excerpts are used; label them as `教材整理`
- split `（1）（2）...`, `A、B、C、...`, and similar list markers onto separate lines instead of flattening them into one sentence

If a needed point cannot be found in the provided material:

- keep the relevant section short
- mark it clearly, for example with `[PPT中未找到对应内容]`
- do not invent missing content

### Heading Format

Use consistent heading levels:

- H1: Chapter title (`# 第X章 {Name}`)
- H4: Section grouping label (`#### 问答`, `#### 重点概念`, `#### 分析题`)
- H5: Question heading (`##### X. {full question text}`) — do NOT prefix with "问题" or similar words; use the raw question number directly
- H6: Analysis sub-heading (`###### 分析题 — {Topic}`) or keypoint heading (`###### 重点{X}. {name}`)

### Content Fidelity

Preserve original exercise text structure:

- Keep the original paragraph structure from the exercise source — do not aggressively rephrase or restructure
- Use the original wording; only trim obvious formatting artifacts (page numbers, docx metadata)
- Original bullet numbering `(1)`, `A.`, etc. should be preserved
- Definitions and supplementary explanations from PPT belong in quote blocks (`>`)
- The goal is a clean reading experience, not a full rewrite

### PPT Supplement Format

Use the consistent format:

```
> **PPT补充（Slide {number}）：**
> - {point 1}
> - {point 2}
```

When multiple slides are relevant, repeat the pattern — each slide gets its own `**PPT补充（Slide X）：**` line.

### Analysis Section Structure (for analysis chapters)

When a chapter is identified as an analysis chapter (e.g., use case diagrams, sequence diagrams, class diagrams), use a detailed four-part structure:

```
###### 分析题 — {Topic}

**一、{Concept / Basic Concepts}**
{Explanation of the modeling concept, its purpose, and context}

**二、{Core Elements}**
{List and explain each core element, one by one, with descriptions}

**三、{Advanced / Relationships}**
{Explain relationships between elements, complex concepts, conventions}

**四、{Analysis Examples}**
{Walk through concrete examples step by step, referencing exercise prompts}
```

The four-part structure IS the output for analysis chapters — do not use the standard Q&A format (`#### 问答` + `##### X.`) for these chapters.

## Diagram Handling

Treat `diagram_mode` as an output preference, but in exam-review output there is one stronger default:

- if the prompt explicitly asks for a diagram-like artifact such as `用例图`, `顺序图`, `活动图`, `状态机图`, `数据流图`, `类图`, `实体关系模型`, `组织结构图`, `角色权限矩阵`, or similar visual material, insert source images by default when available
- do not ask the user for confirmation before inserting those source images unless the source images are missing or ambiguous

**Important image relevance rule**: Only insert images that are clearly relevant and recognizable. If an extracted image is unidentifiable (e.g., blank, partial crop, unrelated decoration, garbled rendering), skip it — do not insert meaningless images just to satisfy the "include images" flag.

Then apply the mode-specific behavior:

- `export`
  Prefer existing images from the source material. Add short explanatory notes when needed.

- `mermaid`
  When the content is suitable, include Mermaid source blocks. Do not promise rendering.

- `plantuml`
  When the content is suitable, include PlantUML source blocks. Do not promise rendering.

If the diagram is AI-authored rather than extracted, label it as `[AI生成，仅供参考]`.

## Web Enrichment

`web_enrich: true` means the user allows limited explanatory supplementation.

Rules:

- keep source-grounded course content as the core
- mark supplemented content as `[联网补充]`
- do not use web content to silently replace missing course material
- keep web inference and web enrichment conceptually separate

Web inference is for drafting a scope when scope is missing. Web enrichment is for adding optional explanatory context after the main structure is already grounded.

## Output Files

Typical outputs:

- one Markdown file per chapter or chapter group
- `复习提纲总览.md` as an entry document when `generate_overview` is enabled
- `images/` for extracted images when image output is enabled

Use `output-examples/通用参考格式.md` as the default structural reference when no custom reference format is provided. For this course workspace, that default is based on `D:\文档\课程作业资料\软件需求分析\00\第一章.md`.

## Lightweight Validation

Do lightweight validation only. Do not claim automated coverage scoring.

Check:

- expected output files were produced
- image paths and obvious links are not broken
- inferred or enriched content is labeled correctly
- AI-authored diagrams are labeled correctly
- no chapter contains empty shells such as headings with no body text
- no requested chapter maps to an out-of-range question number
- explicit diagram questions actually received image output when source images were available
- keypoint-only chapters contain either user-provided focus points or clearly selected chapter concepts
- PPT supplement blocks do not collapse long enumerations into a single unreadable line

If there are obvious gaps, report them as:

- missing sections
- weakly grounded sections
- unresolved questions for the user

## Guardrails

Always enforce these rules:

1. Do not fabricate course content.
2. Do not treat inferred scope as confirmed scope.
3. Do not silently merge web content into source-grounded answers.
4. Do not present keypoint-only output as if it were exercise-mapped output.
5. If the request is underspecified, stop and ask for the missing files or confirm a draft scope first; for textbook-PDF-only generation, missing chapter numbers or重点 are blocking.
6. Do not use `$grill-me` for routine diagram insertion or formatting choices; reserve it for blocking ambiguities such as invalid chapter mappings, missing source files, or conflicting instructions.
