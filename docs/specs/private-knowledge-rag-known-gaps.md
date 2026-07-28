# 私有资料库 RAG：已知缺口与后续计划

> 状态：记录（非 spec，非 plan）
> 日期：2026-07-27
> 关联文档：`docs/specs/feature-private-knowledge-rag.md`（原始规格）、
> `docs/plans/plan-private-knowledge-rag.md`（第一版实现计划，已完成且声明"无占位项"）、
> `docs/specs/feature-full-agent-upgrade.md`（后续 agent 平台规划）

## 说明

`plan-private-knowledge-rag.md` 尾部"规格覆盖自检"声明"无占位项"，
指的是**该计划承诺的范围内**没有遗留 TODO——这个声明本身仍然成立，不需要修改。
本文档记录的是**计划范围之外**、经过本次评估发现的缺口，属于新的待办事项，
不是对已完成计划的否定。

## 1. 图片/OCR 支持：范围收窄决策

**决策：暂不实现图片/OCR 解析，当前阶段仅支持 PDF。**

### 与 spec 原文的差异

`feature-private-knowledge-rag.md` 中以下条款描述了图片/OCR 能力，均**暂缓实施**：

- 非目标第 5 条："不保证低清晰度、严重遮挡或复杂排版图片的识别结果无需人工校对"
- 用户故事第 1 条："我希望上传 PDF、Markdown、图片或历史文章"
- Requirements 资料导入第 1 条："系统必须支持 PDF、Markdown、纯文本、图片截图、网页 URL..."
- Requirements 解析分块索引第 1 条："系统必须先将来源解析、OCR 和清洗为 Markdown"
- Requirements 资料导入第 9 条："低置信度 OCR 结果必须显示识别质量警告"
- AC1："上传有效 PDF、**图片**或纯文本后..."
- AC5："**低置信度 OCR 结果**必须显示警告，且未经用户确认时不能参与检索"
- 边界情况："图片分辨率过低、文字遮挡、表格或代码识别错误"

### 当前代码现状

代码已经与这个决策一致，不需要额外的"关闭开关"：

- `app/api/routes/knowledge.py:28` 的 `ALLOWED_UPLOAD_EXTENSIONS = {"md", "markdown", "txt", "pdf"}`
  本就不包含图片扩展名，上传图片会直接被 400 拒绝。
- `app/domain/knowledge.py` 的 `SourceType.IMAGE` 枚举值存在，但没有任何解析器
  （`parsers.py`）实现图片 OCR 路径，也没有任何 Service 方法引用 `SourceType.IMAGE`。

结论：**不需要写代码去"移除"图片支持——它从未被实现过**，现状与本次决策天然一致。
唯一需要的动作是文档层面记录清楚这是主动决策而非遗漏。

### 后续如果要做

如果未来要重新启用图片/OCR，需要回到 spec 阶段重新评审，至少要解决：
- OCR 引擎/服务选型（可能复用 `MinerUCloudParser` 的云端能力，MinerU 本身支持图片输入）
- 低置信度阈值定义与前端警告 UI（见下节 conversion_confidence 修复方案，两者应共用同一套置信度机制）

## 2. `conversion_confidence` 修复方案

### 问题诊断（比"硬编码 1.0"更严重一层）

`app/infrastructure/knowledge/parsers.py` 中所有 `ParsedMarkdown` 的产出确实
都硬编码 `confidence=1.0`（`MarkdownParser`、`TextParser`、`HtmlCleanerParser`、
`MinerUCloudParser` 均如此）。但更关键的问题是：**这个值从产出后就被完全丢弃**。

追踪 `app/application/knowledge/document_service.py` 的完整链路：
- `create_from_upload`（27-64 行）不接收 confidence 参数
- `save_candidate_markdown`（79-87 行）只接收 `markdown: str`，不接收 confidence
- `confirm_document`（89-104 行）不涉及 confidence
- `save_active_markdown`（106-116 行）同样不涉及 confidence

即 `ParsedMarkdown.confidence` 这个字段在 `app/api/routes/knowledge.py` 的
`upload_document`/`import_url`/`reconvert_document` 三个调用点产出后，
从未被传递给 `DocumentService` 的任何写入方法。数据库列
`knowledge_documents.conversion_confidence`（`persistence/models/knowledge.py:50`）
从未被赋值，实际值恒为 `NULL`，API 序列化输出（`knowledge.py:79`）恒为 `null`，
前端 `types.ts:25` 的类型声明因此从未有真实数据可渲染。

全代码库 `grep -rn "\.confidence\b" app/` 结果为空，进一步确认这个字段
产出后没有任何下游读取者。

### 修复方案（分两部分，可独立推进）

**第一部分：打通传递链路（无论置信度算法如何，这一步都必须做）**

1. `DocumentService.save_candidate_markdown`、`confirm_document`、
   `save_active_markdown` 增加可选参数 `confidence: float | None = None`，
   写入时同步设置 `doc.conversion_confidence = confidence`。
2. `app/api/routes/knowledge.py` 的 `upload_document`、`import_url`、
   `reconvert_document` 三处调用改为把 `ParsedMarkdown.confidence` 传给
   `save_candidate_markdown`。
3. `confirm_document` 确认候选稿转正式稿时，需要把候选稿阶段已记录的
   confidence 值原样带到正式稿（不能因为"确认"这个动作被清空或重置为 1.0）。

**第二部分：让 confidence 值本身有真实意义**

区分两类来源：

- **直接转换类型（Markdown / 纯文本 / URL 清洗）**：保持 `confidence=1.0` 是
  合理的——这些路径没有"识别"环节，原文到 Markdown 是确定性转换，不存在
  识别不确定性，不需要引入假的置信度计算。
- **PDF（MinerU）路径**：这是唯一有意义的置信度来源，因为 MinerU 涉及
  版面分析、公式/表格识别、可能夹杂扫描图片页，存在真实的识别不确定性。
  具体修复步骤：
  1. 在 `MinerUCloudParser._parse_single_chunk`（`parsers.py:104-214`）轮询拿到
     `status_json` 后，先完整记录一次该 JSON 结构到日志（当前代码只提取了
     `state`/`full_zip_url`/`md_content` 三个字段，MinerU API v4 实际响应中
     是否有 per-page 或整体质量字段需要通过真实响应确认，不能凭空假设字段名）。
  2. 若 MinerU 响应中确有可用的质量信号（如失败页数、OCR 页占比等），直接
     换算为 0~1 置信度。
  3. 若 MinerU 响应中没有可用的质量字段，采用启发式指标兜底，全部基于
     已产出的 `md_text`，不依赖任何未验证的假设字段：
     - 按页数折算的平均文本密度：`len(md_text) / total_pages`过低
       （如低于经验阈值，例如 100 字符/页）意味着该页大概率是纯图片或
       解析失败，按比例拉低整体置信度。
     - 乱码/替换字符占比：统计 `�`（Unicode 替换字符）及连续不可打印
       字符的出现比例，占比越高置信度越低。
     - 是否命中 `_parse_single_chunk` 的兜底分支（`state in ("failed", "error")`
       会直接抛异常，因此走到 `parse_pdf` 返回值这一步本身已表明所有分片都
       "成功"，但"成功"不代表"识别准确"，所以仍需要上面两个指标）。
  4. 把上述指标产出的分数写入 `ParsedMarkdown.confidence`，替换掉
     `parse_pdf`（`parsers.py:234`）里硬编码的 `1.0`。

**第三部分：前端展示（满足 AC5"警告展示"要求）**

- AC5 的"未经用户确认时不能参与检索"这一半要求已经被现有 `AWAITING_CONFIRMATION`
  候选态门禁天然满足（候选 Markdown 不会被索引，见 `document_service.py` 的
  状态机与 `indexing_service.py` 的调用条件），**不需要额外开发**。
- 缺失的只是"必须显示识别质量警告"这个 UX 环节：前端在文档详情/候选稿确认
  界面读取 `conversionConfidence` 字段，低于阈值（建议复用检索层已有的
  `KNOWLEDGE_EVIDENCE_THRESHOLD` 概念，单独定义一个
  `KNOWLEDGE_CONVERSION_CONFIDENCE_THRESHOLD`，默认 0.7）时展示警告提示，
  引导用户在确认前人工校对候选 Markdown。

### 验证方式

延续当前"测试检索面板"的验证思路（见第 3 节），不需要新增独立评测体系：
上传一份已知包含扫描页/复杂排版的 PDF，检查 `conversionConfidence` 是否
低于阈值且候选稿页面展示了警告；上传一份纯文字 PDF，检查其 confidence
接近 1.0。

## 3. 验证边界与路线图

### 当前阶段验证边界

RAG 质量保障当前只需要保留现有"检索测试面板"（`/api/knowledge/test-search`
+ 前端 RAG 测试面板，已在近期提交中完成："RAG 测试面板展示检索流程执行明细
与片段章节路径"）。

`feature-private-knowledge-rag.md` 测试策略章节提到的"建立小型标注评测集，
评估 Recall@K、引用正确率、拒答/降级准确率和回答忠实度"这一更复杂的量化
评测体系**暂缓**，不在当前阶段推进。`docs/evaluations/private-knowledge-rag.jsonl`
维持现状（占位样本，不接入自动化测试）。

### 路线图裁定

1. 优先修复本文档第 1、2 节记录的缺口（图片/OCR 范围已收窄为"暂不做"，
   conversion_confidence 按第 2 节方案打通）。
2. 待上述问题修复后，工作重心转向 agent 平台建设（对应
   `docs/specs/feature-full-agent-upgrade.md` 的规划范围）。
3. RAG 私有知识库检索最终要被**集成进 agent 平台**，而非长期作为独立的
   "检索测试面板"孤立存在——这与 `feature-private-knowledge-rag.md` 背景
   章节"本功能为现有创作 Agent 增加可持续更新的私有资料库"的原始定位一致，
   测试面板只是当前阶段的验证手段，不是终态。

### 需要同步纠正的交叉引用

`feature-full-agent-upgrade.md` 第 18-28 行"现有 Agent 基础盘点"表格中，
将"RAG 私有知识库检索"标注为 **"✅ 已上线"**，这个评价过于乐观，与本文档
记录的实际缺口（conversion_confidence 从未生效、图片/OCR 未实现、仅有检索
测试面板未接入主链路）不符。后续启动 agent 平台规划工作时，应将该行更新为
更准确的状态（例如"🟡 检索能力已验证，未集成进对话主链路，存在已知缺口"），
避免 agent 平台的规划基于过于乐观的 RAG 完成度假设。
