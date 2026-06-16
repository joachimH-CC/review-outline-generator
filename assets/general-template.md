# 通用复习提纲生成说明

> 本文件为复习提纲生成器的配置入口。填写以下信息后，AI 将据此生成复习提纲。
> 如果资料不完整，AI 可以先输出待确认草案，而不是直接生成正式提纲。
> 也支持自然语言说明文件，但自然语言说明中仍应明确给出考点文件、课件目录、习题目录以及输出要求。

---

## 一、基本信息

```yaml
subject_name: ""          # 科目名称，如 "软件需求分析"
chapter_range: ""         # 章节范围，如 "2-14" 或 "第1章,第3章,第5-8章"
output_dir: ""            # 输出目录路径（相对于当前工作目录）
```

## 二、考点范围

```yaml
# 题型与分值
exam_structure:
  填空题: { count: 0, score: 0 }
  选择题: { count: 0, score: 0 }
  问答:   { count: 0, score: 0 }
  分析题: { count: 0, score: 0 }

# 题目来源
question_source: "exercises"    # "exercises"(按习题/题号组织，需习题资料) / "keypoints"(按课件或教材PDF提取章节重点) / "custom"(按自定义说明组织，要求清晰)

# 各章节题号映射（question_source=exercises 时必填）
# 格式：第X章: [题号列表]
chapter_question_map:
  第一章: []
  # 第二章: [2,3,5,7]
  # ...

# 各章节复习重点（question_source=keypoints 且没有课后习题时使用）
# 格式：第X章: [重点1, 重点2, 重点3]
chapter_focus_map:
  # 第一章: [软件需求层次, 业务需求与用户需求, 需求开发]
  # 第二章: [需求获取, 需求分析方法]

# 分析题要求（按章节列出分析题类型）
analysis_questions:
  # 第六章: "用例图+用例表"
  # 第八章: "顺序图"
```

## 三、资料来源

```yaml
# 课件目录（PPT/PPTX）；如果只根据教材PDF整理，可留空
slides_dir: ""            # 如 "ppt/" 或 "课件/"

# 教材 PDF（可选；无课后习题时可配合 chapter_focus_map 使用）
textbook_pdf: ""          # 如 "软件需求分析.pdf"

# 课后习题目录（Word 或 PDF）
exercises_dir: ""         # question_source=exercises 时建议提供；keypoints 模式可留空

# 参考格式文件（可选，不填则用内置通用模板）
reference_format: ""      # 仅作为输出风格参考；本课程可填 "D:\文档\课程作业资料\软件需求分析\00\第一章.md"
```

## 四、输出控制

```yaml
# 分析题图表处理方式
# "export"    - 优先使用文档中已有图片 + 少量说明（默认）
# "mermaid"   - 在适合时附带 Mermaid 源码块
# "plantuml"  - 在适合时附带 PlantUML 源码块
# 对于题目中明确要求的顺序图/用例图/类图等可视化内容，默认直接插入源图片，不再额外确认
diagram_mode: "export"

# 是否允许联网补充知识点（默认关闭）
# 开启后，可在主内容落地后补充解释性内容，标注 "[联网补充]"
# 它不表示可以用联网内容替代课件，也不表示可以跳过用户确认直接推断考试范围
web_enrich: false

# 是否提取并嵌入文档中的图片
# 显式要求图示的题目只要源图存在，就应自动插入
include_images: true

# 是否生成总复习提纲说明（索引入口文件）
generate_overview: true
```

## 五、自定义说明

<!-- 在此补充任何特殊要求，如：
- 某章节需要特别详细/简略
- 特定术语需要解释
- 忽略某类内容
- question_source=custom 时，请在这里明确输出结构
- 没有课后习题时，请给出具体章节序号和 chapter_focus_map 中的重点
- ...
-->


---

> **使用方式**：填写以上内容后，运行 skill：`/review-outline-generator` 或直接说"根据生成说明帮我完成复习提纲"。

